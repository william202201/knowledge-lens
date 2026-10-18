"""Evaluate document retrieval, not LLM answer quality."""
import json
from pathlib import Path
import re
from .retrieval import Index


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def evaluate(index: Index, cases: Path, k: int = 3, min_score_ratio: float = 0.15) -> dict:
    rows = []
    for line in cases.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        hits = index.search(case["question"], k, min_score_ratio)
        # Deduplicate document sources so one long file cannot inflate Recall@k.
        sources = list(dict.fromkeys(hit["source"] for hit in hits))
        expected = set(case["sources"])
        ranks = [sources.index(s) + 1 for s in expected if s in sources]
        row = {**case, "retrieved": sources, "recall": len(set(sources) & expected) / len(expected) if expected else None,
               "rr": 1 / min(ranks) if ranks else 0, "correct_empty": not sources if not expected else None}
        evidence = [_squash(e) for e in case.get("evidence", [])]
        if evidence:
            # Evidence hit: a retrieved chunk from an expected document contains the quoted clause.
            # Stricter than document recall: a chunk boundary that cuts the clause counts as a miss.
            evidence_ranks = [i + 1 for i, hit in enumerate(hits)
                              if hit["source"] in expected and any(e in _squash(hit["text"]) for e in evidence)]
            row["evidence_rank"] = evidence_ranks[0] if evidence_ranks else None
        rows.append(row)
    answerable = [r for r in rows if r["sources"]]
    empty = [r for r in rows if not r["sources"]]
    with_evidence = [r for r in answerable if r.get("evidence")]
    if not answerable:
        raise ValueError("Evaluation requires at least one answerable case")
    result = {"k": k, "min_score_ratio": min_score_ratio, "cases": len(rows),
              "recall_at_k": round(sum(r["recall"] for r in answerable) / len(answerable), 4),
              "mrr": round(sum(r["rr"] for r in answerable) / len(answerable), 4),
              "empty_query_accuracy": sum(r["correct_empty"] for r in empty) / len(empty) if empty else None}
    if with_evidence:
        result["evidence_hit_at_k"] = round(sum(r["evidence_rank"] is not None for r in with_evidence) / len(with_evidence), 4)
        result["evidence_mrr"] = round(sum(1 / r["evidence_rank"] for r in with_evidence if r["evidence_rank"]) / len(with_evidence), 4)
    result["scope"] = "Retrieval metrics only; not a measure of LLM answer quality"
    result["rows"] = rows
    return result
