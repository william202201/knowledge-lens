import json
from pathlib import Path
import tempfile
import unittest
from knowledge_lens.evaluate import evaluate
from knowledge_lens.retrieval import Index, chunk_articles, chunk_text, split_document, tokenize
from knowledge_lens.service import ask
from knowledge_lens.provider import ProviderError


class FakeProvider:
    def __init__(self, answer):
        self.answer = answer
        self.payload = None

    def create(self, **payload):
        self.payload = payload
        return {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(self.answer)}]}], "usage": {"total_tokens": 12}}


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.docs = root / "docs"
        self.docs.mkdir()
        (self.docs / "api.md").write_text("API retry backoff jitter 429. 密钥不能提交到代码仓库。", encoding="utf-8")
        (self.docs / "leave.md").write_text("Annual leave requires manager approval. 年假需要审批。", encoding="utf-8")
        self.index = Index(root / "index.sqlite3")
        self.index.ingest(self.docs)

    def test_offsets_overlap_and_stability(self):
        text = "测试字符位置" * 100
        chunks = chunk_text("x.md", text, 80, 20)
        self.assertEqual(chunks, chunk_text("x.md", text, 80, 20))
        self.assertEqual(chunks[1].start, 60)
        for chunk in chunks:
            self.assertEqual(text[chunk.start:chunk.end], chunk.text)
        self.assertEqual(chunks[-1].end, len(text))

    def test_chunk_validation(self):
        for size, overlap in [(0, 0), (100, 100), (100, -1)]:
            with self.assertRaises(ValueError):
                chunk_text("x.md", "hello", size, overlap)

    def test_chinese_and_english_retrieval(self):
        self.assertIn("密钥", tokenize("密钥保存"))
        self.assertEqual(self.index.search("retry 429")[0]["source"], "api.md")
        self.assertEqual(self.index.search("年假审批")[0]["source"], "leave.md")
        self.assertEqual(self.index.search("quantum penguin"), [])

    def test_rebuild_removes_stale_and_failed_ingest_preserves_index(self):
        (self.docs / "api.md").unlink()
        self.index.ingest(self.docs)
        self.assertEqual({c.source for c in self.index.chunks()}, {"leave.md"})
        (self.docs / "bad.md").write_bytes(b"\xff")
        with self.assertRaises(UnicodeError):
            self.index.ingest(self.docs)
        self.assertEqual({c.source for c in self.index.chunks()}, {"leave.md"})

    def test_offline_and_no_evidence(self):
        answer = ask(self.index, "API retry")
        self.assertEqual(answer["mode"], "offline")
        self.assertTrue(answer["citation_ids"])
        self.assertFalse(ask(self.index, "quantum penguin")["answerable"])

    def test_unknown_or_missing_citation_fails_closed(self):
        for ids in [["invented"], []]:
            with self.assertRaises(ProviderError):
                ask(self.index, "API retry", FakeProvider({"answer": "Retry", "answerable": True, "citation_ids": ids}))

    def test_live_contract_uses_evidence_and_strict_schema(self):
        hit = self.index.search("API retry")[0]
        provider = FakeProvider({"answer": "Use backoff", "answerable": True, "citation_ids": [hit["id"]]})
        result = ask(self.index, "API retry", provider)
        self.assertEqual(result["usage"]["total_tokens"], 12)
        self.assertTrue(provider.payload["text"]["format"]["strict"])
        self.assertIn(hit["id"], provider.payload["input"])

    def test_refusal_and_malformed_answer(self):
        result = ask(self.index, "API retry", FakeProvider({"answer": "Insufficient evidence", "answerable": False, "citation_ids": []}))
        self.assertFalse(result["answerable"])
        with self.assertRaises(ProviderError):
            ask(self.index, "API retry", FakeProvider({"answer": "x", "answerable": "yes", "citation_ids": []}))

    def test_invalid_questions(self):
        for question in [None, "", " " * 3, "a" * 2001]:
            with self.assertRaises(ValueError):
                ask(self.index, question)

    def test_article_chunks_keep_statutes_whole_and_offsets_exact(self):
        text = "# 劳动合同法\n\n## 第一章\n\n" + "".join(f"第{n}条 条文内容{'字' * 40}。\n\n" for n in "一二三四五六") + "第七条 " + "长" * 300 + "\n"
        chunks = chunk_articles("law.md", text, 120)
        self.assertEqual(chunks, chunk_articles("law.md", text, 120))
        for chunk in chunks:
            self.assertEqual(text[chunk.start:chunk.end], chunk.text)
            self.assertLessEqual(len(chunk.text), 120)
        # Short articles are never split mid-way; only the oversized article falls back to windows.
        for n in "一二三四五六":
            self.assertEqual(sum(f"第{n}条" in c.text for c in chunks), 1)
            holder = next(c for c in chunks if f"第{n}条" in c.text)
            self.assertIn("字" * 40 + "。", holder.text)
        self.assertEqual("".join(c.text for c in chunks).replace("\n", ""), text.replace("\n", ""))
        with self.assertRaises(ValueError):
            split_document("law.md", text, 120, 0, "semantic")

    def test_evidence_hit_requires_clause_in_retrieved_chunk(self):
        root = Path(self.temp.name)
        law = root / "law"
        law.mkdir()
        (law / "contract.md").write_text("第十九条 劳动合同期限三年以上的，试用期不得超过六个月。\n\n第二十条 试用期工资另行约定。\n", encoding="utf-8")
        index = Index(root / "law.sqlite3")
        index.ingest(law, 50, 0, "article")
        cases = root / "law.jsonl"
        cases.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in [
            {"question": "试用期最长多久", "sources": ["contract.md"], "evidence": ["试用期不得超过六个月"]},
            {"question": "试用期工资", "sources": ["contract.md"], "evidence": ["不存在的条文"]}]), encoding="utf-8")
        result = evaluate(index, cases, 1)
        self.assertEqual(result["recall_at_k"], 1)
        self.assertEqual(result["evidence_hit_at_k"], 0.5)
        self.assertEqual(result["rows"][0]["evidence_rank"], 1)

    def test_evaluation_document_dedup_and_metrics(self):
        cases = Path(self.temp.name) / "eval.jsonl"
        cases.write_text('\n'.join(json.dumps(c) for c in [
            {"question": "API retry", "sources": ["api.md"]},
            {"question": "quantum penguin", "sources": []}]))
        result = evaluate(self.index, cases)
        self.assertEqual(result["recall_at_k"], 1)
        self.assertEqual(result["empty_query_accuracy"], 1)


if __name__ == "__main__":
    unittest.main()
