"""Compare chunking strategies and top-k on the public labor-law corpus.

Usage:
    python scripts/sweep_labor_law.py

Writes docs/labor-law-sweep.json and prints a Markdown table. Retrieval only; no model calls.
"""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge_lens.evaluate import evaluate  # noqa: E402
from knowledge_lens.retrieval import Index  # noqa: E402

DOCS = ROOT / "examples" / "labor-law"
CASES = ROOT / "examples" / "labor-law-eval.jsonl"
CONFIGS = [
    ("fixed", 500, 80),   # project default
    ("fixed", 200, 0),
    ("fixed", 300, 0),
    ("fixed", 300, 80),
    ("fixed", 800, 80),
    ("article", 300, 0),
    ("article", 500, 0),
    ("article", 800, 0),
]
TOP_K = [3, 5]


def main():
    results = []
    with TemporaryDirectory() as temp:
        for n, (strategy, size, overlap) in enumerate(CONFIGS):
            index = Index(Path(temp) / f"sweep{n}.sqlite3")
            info = index.ingest(DOCS, size, overlap, strategy)
            for k in TOP_K:
                start = perf_counter()
                r = evaluate(index, CASES, k)
                results.append({"strategy": strategy, "chunk_size": size, "overlap": overlap, "k": k,
                                "documents": info["documents"], "chunks": info["chunks"],
                                "evidence_hit_at_k": r["evidence_hit_at_k"], "evidence_mrr": r["evidence_mrr"],
                                "recall_at_k": r["recall_at_k"], "mrr": r["mrr"],
                                "empty_query_accuracy": r["empty_query_accuracy"],
                                "seconds": round(perf_counter() - start, 2),
                                "misses": [row["question"] for row in r["rows"] if row["sources"] and row.get("evidence_rank") is None]})
    out = ROOT / "docs" / "labor-law-sweep.json"
    out.write_text(json.dumps({"cases": str(CASES.relative_to(ROOT)), "docs": str(DOCS.relative_to(ROOT)),
                               "results": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("| 切块方式 | 块大小 | 重叠 | 片段数 | Top-k | 条文命中率 | 条文 MRR | 文档召回率 |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in results:
        name = "按条文" if r["strategy"] == "article" else "固定长度"
        print(f"| {name} | {r['chunk_size']} | {r['overlap']} | {r['chunks']} | {r['k']} | "
              f"{r['evidence_hit_at_k']:.0%} | {r['evidence_mrr']:.2f} | {r['recall_at_k']:.0%} |")
    print(f"\nWrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
