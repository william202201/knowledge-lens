import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
from .evaluate import evaluate
from .http import serve
from .provider import ResponsesProvider
from .retrieval import Index
from .service import ask


def main():
    parser = argparse.ArgumentParser(description="Knowledge Lens — inspectable local RAG")
    parser.add_argument("--db", default="knowledge.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("directory", type=Path)
    query = sub.add_parser("ask")
    query.add_argument("question")
    query.add_argument("--live", action="store_true")
    evaluation = sub.add_parser("evaluate")
    evaluation.add_argument("--cases", type=Path, default=Path("examples/eval.jsonl"))
    server = sub.add_parser("serve")
    server.add_argument("--port", type=int, default=8011)
    server.add_argument("--live", action="store_true")
    args = parser.parse_args()
    index = Index(args.db)
    provider = ResponsesProvider() if getattr(args, "live", False) else None
    if args.command == "ingest":
        result = index.ingest(args.directory)
    elif args.command == "ask":
        result = ask(index, args.question, provider)
    elif args.command == "evaluate":
        result = evaluate(index, args.cases)
    else:
        if not index.chunks():
            examples = Path("examples/docs")
            if not examples.is_dir():
                parser.error("Index is empty. Run ingest with a document directory first.")
            index.ingest(examples)

        def dispatch(method, path, data):
            path = urlparse(path).path
            if method == "GET" and path == "/api/status":
                chunks = index.chunks()
                return {"mode": "live" if provider else "offline", "documents": len({c.source for c in chunks}), "chunks": len(chunks)}
            if method == "POST" and path == "/api/ask":
                return ask(index, data.get("question"), provider)
            raise LookupError()

        serve(args.port, dispatch)
        return
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
