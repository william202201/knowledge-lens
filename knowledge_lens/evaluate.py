"""Evaluate document retrieval, not LLM answer quality."""
import json
from pathlib import Path
from .retrieval import Index


def evaluate(index: Index, cases: Path, k: int = 3) -> dict:
    rows = []
    for line in cases.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        # Deduplicate document sources so one long file cannot inflate Recall@k.
        sources = list(dict.fromkeys(hit["source"] for hit in index.search(case["question"], k)))
        expected = set(case["sources"])
        ranks = [sources.index(s) + 1 for s in expected if s in sources]
        rows.append({**case, "retrieved": sources, "recall": len(set(sources) & expected) / len(expected) if expected else None,
                     "rr": 1 / min(ranks) if ranks else 0, "correct_empty": not sources if not expected else None})
    answerable = [r for r in rows if r["sources"]]
    empty = [r for r in rows if not r["sources"]]
    if not answerable:
        raise ValueError("Evaluation requires at least one answerable case")
    return {"k": k, "cases": len(rows), "recall_at_k": round(sum(r["recall"] for r in answerable) / len(answerable), 4),
            "mrr": round(sum(r["rr"] for r in answerable) / len(answerable), 4),
            "empty_query_accuracy": sum(r["correct_empty"] for r in empty) / len(empty) if empty else None,
            "scope": "Small synthetic retrieval fixture; not a real-world benchmark or generation quality score", "rows": rows}
