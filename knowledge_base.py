"""Local retrieval-augmented knowledge layer for CatalogIQ.

Procurement guidance lives as Markdown files in ./knowledge. Each "## " section
becomes one chunk. Chunks are embedded as TF-IDF vectors and retrieved by cosine
similarity, so the agents receive the most relevant guidance for the buyer's
question instead of a fixed list. The index is rebuilt in memory at startup and
needs no external service or API key.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
GENERAL = "general"

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from",
    "how", "i", "if", "in", "is", "it", "its", "of", "on", "or", "should", "so", "than",
    "that", "the", "their", "this", "to", "what", "when", "which", "while", "with", "my",
    "we", "our", "us", "not", "even", "same", "across", "vendors", "vendor", "compare",
}


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    category: str
    heading: str
    text: str


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", text.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


def load_chunks(directory: Path = KNOWLEDGE_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        match = re.search(r"^category:\s*(.+)$", raw, flags=re.MULTILINE)
        category = match.group(1).strip().lower() if match else GENERAL
        body = re.sub(r"^---.*?---\s*", "", raw, flags=re.DOTALL)
        for index, section in enumerate(re.split(r"^## ", body, flags=re.MULTILINE)):
            section = section.strip()
            if not section:
                continue
            heading, _, text = section.partition("\n")
            text = " ".join(line.strip() for line in text.splitlines() if line.strip())
            chunks.append(Chunk(f"{path.stem}#{index}", category, heading.strip(), text))
    return chunks


class KnowledgeBase:
    """Small TF-IDF vector index with cosine-similarity retrieval."""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        docs = [tokenize(f"{c.heading} {c.text} {c.category}") for c in chunks]
        df = Counter(term for doc in docs for term in set(doc))
        n = len(docs)
        self.idf = {term: math.log((1 + n) / (1 + freq)) + 1 for term, freq in df.items()}
        self.vectors = [self._vectorize(doc) for doc in docs]

    def _vectorize(self, tokens: list[str]) -> dict[str, float]:
        counts = Counter(tokens)
        vec = {t: c * self.idf.get(t, 0.0) for t, c in counts.items() if t in self.idf}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def search(self, query: str, category: str | None = None, top_k: int = 3) -> list[dict]:
        qvec = self._vectorize(tokenize(query))
        scored = []
        for chunk, vec in zip(self.chunks, self.vectors):
            if category and chunk.category not in (category, GENERAL):
                continue
            score = sum(weight * vec.get(term, 0.0) for term, weight in qvec.items())
            if chunk.category == category:
                score += 0.05  # small boost so category guidance outranks general guidance on ties
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "chunk_id": chunk.chunk_id,
                "category": chunk.category,
                "heading": chunk.heading,
                "text": chunk.text,
                "score": round(score, 3),
            }
            for score, chunk in scored[:top_k]
            if score > 0
        ]

    def categories(self) -> set[str]:
        return {c.category for c in self.chunks if c.category != GENERAL}


KNOWLEDGE_BASE = KnowledgeBase(load_chunks())
