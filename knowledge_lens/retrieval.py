"""A transparent BM25 baseline with character offsets and stable chunk IDs."""
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
import re
import sqlite3


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9_]+", text.lower())
    for span in re.findall(r"[\u4e00-\u9fff]+", text):
        words.extend(span[i:i + 2] for i in range(len(span) - 1))
        if len(span) == 1:
            words.append(span)
    return words


@dataclass(frozen=True)
class Chunk:
    id: str
    source: str
    start: int
    end: int
    text: str


def chunk_text(source: str, text: str, size: int = 500, overlap: int = 80) -> list[Chunk]:
    if size < 50 or not 0 <= overlap < size:
        raise ValueError("Chunk size must be >= 50 and 0 <= overlap < size")
    result = []
    for start in range(0, len(text), size - overlap):
        end = min(start + size, len(text))
        part = text[start:end]
        if part.strip():
            digest = hashlib.sha256(f"{source}\0{start}\0{part}".encode()).hexdigest()[:16]
            result.append(Chunk(digest, source, start, end, part))
        if end == len(text):
            break
    return result


# A new unit starts at a Markdown heading or at a statute article such as “第十九条”.
UNIT_START = re.compile(r"^(#{1,6}\s|第[一二三四五六七八九十百零〇两\d]+条)", re.MULTILINE)


def chunk_articles(source: str, text: str, size: int = 500) -> list[Chunk]:
    """Structure-aware chunking: keep each heading/article whole and pack neighbours up to `size` characters.

    An article longer than `size` falls back to fixed windows so no chunk grows without bound.
    """
    if size < 50:
        raise ValueError("Chunk size must be >= 50")
    starts = sorted({0, *(m.start() for m in UNIT_START.finditer(text))})
    units = [(a, b) for a, b in zip(starts, starts[1:] + [len(text)]) if text[a:b].strip()]
    spans, current = [], None
    for a, b in units:
        if b - a > size:
            if current:
                spans.append(current)
                current = None
            spans.extend((c.start + a, c.end + a) for c in chunk_text(source, text[a:b], size, 0))
        elif current and b - current[0] <= size:
            current = (current[0], b)
        else:
            if current:
                spans.append(current)
            current = (a, b)
    if current:
        spans.append(current)
    result = []
    for a, b in spans:
        part = text[a:b]
        digest = hashlib.sha256(f"{source}\0{a}\0{part}".encode()).hexdigest()[:16]
        result.append(Chunk(digest, source, a, b, part))
    return result


def split_document(source: str, text: str, size: int = 500, overlap: int = 80, strategy: str = "fixed") -> list[Chunk]:
    if strategy == "fixed":
        return chunk_text(source, text, size, overlap)
    if strategy == "article":
        return chunk_articles(source, text, size)
    raise ValueError("strategy must be 'fixed' or 'article'")


class Index:
    def __init__(self, path: str | Path):
        self.path = str(path)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS chunks (id TEXT PRIMARY KEY, source TEXT, start INTEGER, end INTEGER, text TEXT)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def ingest(self, directory: Path, size: int = 500, overlap: int = 80, strategy: str = "fixed") -> dict:
        directory = directory.resolve()
        if not directory.is_dir():
            raise ValueError("Document directory does not exist")
        chunks = []
        sources = []
        for file in sorted(directory.rglob("*")):
            if file.is_file() and not file.is_symlink() and file.suffix.lower() in {".md", ".txt"}:
                if file.stat().st_size > 1_000_000:
                    raise ValueError(f"Document exceeds 1 MB: {file.name}")
                source = file.relative_to(directory).as_posix()
                sources.append(source)
                chunks.extend(split_document(source, file.read_text(encoding="utf-8"), size, overlap, strategy))
        if not chunks:
            raise ValueError("No non-empty UTF-8 Markdown or text documents found")
        # Rebuild atomically: stale chunks disappear; failed reads preserve the old index.
        with self.connect() as db:
            db.execute("DELETE FROM chunks")
            db.executemany("INSERT INTO chunks VALUES (:id,:source,:start,:end,:text)", [asdict(c) for c in chunks])
        return {"documents": len(sources), "chunks": len(chunks), "sources": sources}

    def chunks(self) -> list[Chunk]:
        with self.connect() as db:
            return [Chunk(**dict(row)) for row in db.execute("SELECT * FROM chunks ORDER BY source,start")]

    def search(self, query: str, k: int = 3, min_score_ratio: float = 0.15) -> list[dict]:
        if not 1 <= k <= 10:
            raise ValueError("k must be between 1 and 10")
        if not 0 <= min_score_ratio <= 1:
            raise ValueError("min_score_ratio must be between 0 and 1")
        terms = set(tokenize(query))
        chunks = self.chunks()
        if not terms or not chunks:
            return []
        counters = [Counter(tokenize(c.text)) for c in chunks]
        avg_length = sum(sum(c.values()) for c in counters) / len(counters) or 1
        frequencies = Counter(term for c in counters for term in c)
        ranked = []
        for chunk, counts in zip(chunks, counters):
            score = 0.0
            length = sum(counts.values())
            for term in terms:
                tf = counts[term]
                if tf:
                    idf = math.log(1 + (len(chunks) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
                    score += idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * length / avg_length))
            if score > 0:
                ranked.append({**asdict(chunk), "score": round(score, 5)})
        ranked.sort(key=lambda x: (-x["score"], x["source"], x["start"]))
        # A corpus-dependent heuristic, not a calibrated confidence probability.
        cutoff = ranked[0]["score"] * min_score_ratio if ranked else 0
        return [hit for hit in ranked if hit["score"] >= cutoff][:k]
