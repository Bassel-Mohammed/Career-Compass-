"""
CareerCompass — Skill Embeddings and Vector Index

The retrieval half of the RAG taxonomy stage: turn every canonical skill
into a vector once, then answer "which ten taxonomy entries look most like
this syllabus phrase?" in a single matrix product.

Two backends, one interface:

    lexical   character and word n-grams hashed into a fixed vector, with
              IDF weighting learned from the taxonomy itself. No model
              download, no GPU, deterministic, runs anywhere. Strong on
              spelling variants ("GazeboSim" / "Gazebo Sim") and weak on
              pure synonyms ("motor" / "actuator").

    bge       BAAI/bge-m3 through sentence-transformers. Multilingual
              (English and Arabic in one space) and genuinely semantic.
              Needs torch and roughly 2GB of model weights.

The lexical backend is the default so the pipeline works out of the box;
set CC_EMBEDDING_BACKEND=bge once the dependency is installed. Vectors are
never mixed: the index records which backend built it and refuses to be
loaded by the other one.

Usage:
    from careercompass.skills.embeddings import get_embedder, VectorIndex

    embedder = get_embedder(corpus=[skill_text(s) for s in taxonomy.skills])
    index = VectorIndex.build(taxonomy, embedder)
    hits = index.search(embedder.encode(["ROS 2 node development"])[0], top_k=10)
"""

import os
import re
import json
import math
import zlib
import logging
from pathlib import Path

import numpy as np

from careercompass.config import VECTOR_INDEX_PATH
from careercompass.skills.taxonomy import normalize, skill_text

logger = logging.getLogger("careercompass.embeddings")

INDEX_PATH = VECTOR_INDEX_PATH

DEFAULT_DIM = 4096
DEFAULT_BGE_MODEL = "BAAI/bge-m3"

WORD_RE = re.compile(r"\w+", re.UNICODE)


# ── Lexical Backend ────────────────────────────────────────────
class LexicalEmbedder:
    """
    Hashed n-gram embedder with IDF weighting.

    Each text becomes a bag of word unigrams, word bigrams and character
    3-to-5-grams; every feature is hashed to a fixed slot with CRC32 —
    Python's built-in hash is salted per process and would produce a
    different index on every run — weighted by its inverse document
    frequency over the taxonomy, and L2-normalised so a dot product is a
    cosine similarity.
    """

    name = "lexical-ngram-v1"

    def __init__(self, dim: int = DEFAULT_DIM, idf=None):
        self.dim = dim
        # Uniform weights until fit() has seen a corpus.
        self.idf = np.ones(dim, dtype=np.float32) if idf is None else idf

    # -- features --
    @staticmethod
    def _features(text: str) -> list:
        """Word and character n-grams for one text."""
        norm = normalize(text)
        if not norm:
            return []

        words = WORD_RE.findall(norm)
        features = [f"w:{w}" for w in words]
        features.extend(f"b:{a}_{b}" for a, b in zip(words, words[1:]))

        # Character grams over a space-padded form, so word boundaries are
        # part of the signal and short tokens still produce features.
        padded = f" {norm} "
        for size in (3, 4, 5):
            if len(padded) >= size:
                features.extend(
                    f"c:{padded[i:i + size]}" for i in range(len(padded) - size + 1)
                )
        return features

    def _slots(self, text: str) -> dict:
        """Feature slots and their raw counts for one text."""
        counts = {}
        for feature in self._features(text):
            slot = zlib.crc32(feature.encode("utf-8")) % self.dim
            counts[slot] = counts.get(slot, 0) + 1
        return counts

    # -- training --
    def fit(self, corpus: list) -> "LexicalEmbedder":
        """Learn IDF weights from the taxonomy texts."""
        document_frequency = np.zeros(self.dim, dtype=np.float32)
        total = 0
        for text in corpus:
            slots = self._slots(text)
            if not slots:
                continue
            total += 1
            for slot in slots:
                document_frequency[slot] += 1.0

        if total == 0:
            self.idf = np.ones(self.dim, dtype=np.float32)
            return self

        self.idf = (np.log((total + 1.0) / (document_frequency + 1.0)) + 1.0).astype(np.float32)
        return self

    # -- inference --
    def encode(self, texts: list) -> np.ndarray:
        """Embed a list of texts as L2-normalised row vectors."""
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for slot, count in self._slots(text).items():
                # Sublinear term frequency: a phrase repeating a trigram
                # five times is not five times more about it.
                matrix[row, slot] = (1.0 + math.log(count)) * self.idf[slot]
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        np.divide(matrix, norms, out=matrix, where=norms > 0)
        return matrix

    # -- persistence --
    def state(self) -> dict:
        """Arrays to store alongside the index."""
        return {"idf": self.idf}

    @classmethod
    def restore(cls, dim: int, state: dict) -> "LexicalEmbedder":
        """Rebuild a fitted embedder from stored arrays."""
        return cls(dim=dim, idf=state["idf"])


# ── Neural Backend ─────────────────────────────────────────────
class SentenceTransformerEmbedder:
    """
    sentence-transformers wrapper, defaulting to BAAI/bge-m3.

    bge-m3 is the reason this backend exists: it embeds English and Arabic
    into the same space, which the lexical backend cannot do at all — an
    Arabic ESCO label and an English syllabus phrase share no n-grams.
    """

    def __init__(self, model_name: str = DEFAULT_BGE_MODEL):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on install
            raise ImportError(
                "sentence-transformers is not installed. Either "
                "`pip install sentence-transformers` or set "
                "CC_EMBEDDING_BACKEND=lexical."
            ) from exc

        self.model_name = model_name
        self.name = f"st:{model_name}"
        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def fit(self, corpus: list) -> "SentenceTransformerEmbedder":
        """No-op; the model is already trained."""
        return self

    def encode(self, texts: list) -> np.ndarray:
        vectors = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    def state(self) -> dict:
        return {}

    @classmethod
    def restore(cls, dim: int, state: dict, model_name: str = DEFAULT_BGE_MODEL):
        return cls(model_name=model_name)


def get_embedder(backend: str = "", corpus=None, dim: int = DEFAULT_DIM):
    """
    Build the embedding backend to use.

    Args:
        backend: "lexical", "bge", or "" / "auto" to read
            CC_EMBEDDING_BACKEND and fall back to lexical.
        corpus: Taxonomy texts, used to fit the lexical IDF weights.
        dim: Vector width for the lexical backend.

    Returns:
        A fitted embedder exposing name, dim, encode(), state().
    """
    backend = (backend or os.getenv("CC_EMBEDDING_BACKEND", "auto")).lower()

    if backend in ("bge", "st", "sentence-transformers"):
        return SentenceTransformerEmbedder(
            os.getenv("CC_EMBEDDING_MODEL", DEFAULT_BGE_MODEL)
        )

    if backend == "auto":
        try:
            embedder = SentenceTransformerEmbedder(
                os.getenv("CC_EMBEDDING_MODEL", DEFAULT_BGE_MODEL)
            )
            logger.info("Using %s for embeddings", embedder.name)
            return embedder
        except ImportError:
            logger.info("sentence-transformers unavailable; using lexical embeddings")

    embedder = LexicalEmbedder(dim=dim)
    return embedder.fit(corpus or [])


# ── Vector Index ───────────────────────────────────────────────
class VectorIndex:
    """
    Dense vectors for every canonical skill, plus cosine search over them.

    The taxonomy is small enough (tens of thousands of rows) that an exact
    matrix product beats an approximate index on both simplicity and
    accuracy, and it keeps the whole stage dependency-free. Swapping in
    pgvector later only means replacing search().
    """

    def __init__(self, ids: list, vectors: np.ndarray, backend: str,
                 fingerprint: str, embedder=None):
        self.ids = ids
        self.vectors = vectors
        self.backend = backend
        self.fingerprint = fingerprint
        self.embedder = embedder

    def __len__(self) -> int:
        return len(self.ids)

    @classmethod
    def build(cls, taxonomy, embedder) -> "VectorIndex":
        """Embed every skill in a taxonomy."""
        texts = [skill_text(skill) for skill in taxonomy.skills]
        vectors = embedder.encode(texts)
        return cls(
            ids=[skill["id"] for skill in taxonomy.skills],
            vectors=vectors,
            backend=embedder.name,
            fingerprint=taxonomy.fingerprint,
            embedder=embedder,
        )

    def search(self, query: np.ndarray, top_k: int = 10) -> list:
        """
        Return the top_k (skill_id, similarity) pairs for a query vector.

        Both sides are L2-normalised, so the dot product is the cosine.
        """
        top_k = min(top_k, len(self.ids))
        if top_k <= 0:
            return []
        scores = self.vectors @ query
        # argpartition finds the top k without sorting the whole array.
        top = np.argpartition(-scores, top_k - 1)[:top_k]
        top = top[np.argsort(-scores[top])]
        return [(self.ids[i], float(scores[i])) for i in top]

    # -- persistence --
    def save(self, path=INDEX_PATH) -> None:
        """Write vectors, ids and the backend fingerprint to one file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {
            "vectors": self.vectors,
            "meta": np.array(json.dumps({
                "ids": self.ids,
                "backend": self.backend,
                "fingerprint": self.fingerprint,
                "dim": int(self.vectors.shape[1]) if self.vectors.size else 0,
            }, ensure_ascii=False)),
        }
        if self.embedder is not None:
            for key, value in self.embedder.state().items():
                arrays[f"state_{key}"] = value
        np.savez_compressed(path, **arrays)

    @classmethod
    def load(cls, path=INDEX_PATH, fingerprint: str = "", backend: str = ""):
        """
        Load a stored index, or None when it cannot be trusted.

        Returns None rather than raising when the taxonomy has changed or
        a different backend built the vectors: the caller's response in
        both cases is to rebuild, and a stale index would otherwise return
        confident matches for skills that no longer exist.
        """
        path = Path(path)
        if not path.exists():
            return None

        with np.load(path, allow_pickle=False) as stored:
            meta = json.loads(str(stored["meta"]))
            if fingerprint and meta.get("fingerprint") != fingerprint:
                logger.info("Vector index is stale (taxonomy changed); rebuilding")
                return None
            if backend and meta.get("backend") != backend:
                logger.info("Vector index was built by %s, not %s; rebuilding",
                            meta.get("backend"), backend)
                return None

            vectors = stored["vectors"]
            state = {
                key[len("state_"):]: stored[key]
                for key in stored.files if key.startswith("state_")
            }

        embedder = None
        stored_backend = meta.get("backend", "")
        if stored_backend == LexicalEmbedder.name and "idf" in state:
            embedder = LexicalEmbedder.restore(meta.get("dim", DEFAULT_DIM), state)

        return cls(
            ids=meta["ids"],
            vectors=vectors,
            backend=stored_backend,
            fingerprint=meta.get("fingerprint", ""),
            embedder=embedder,
        )


def load_or_build_index(taxonomy, backend: str = "", path=INDEX_PATH,
                        rebuild: bool = False) -> VectorIndex:
    """
    Get a usable index for a taxonomy, rebuilding only when necessary.

    Rebuilding is the expensive step under the neural backend, so a stored
    index whose fingerprint still matches is reused as-is.
    """
    requested = (backend or os.getenv("CC_EMBEDDING_BACKEND", "auto")).lower()

    if not rebuild:
        index = VectorIndex.load(path, fingerprint=taxonomy.fingerprint)
        if index is not None:
            # An index built by a backend the caller did not ask for is
            # still valid; only an explicit request forces the rebuild.
            wanted_lexical = requested == "lexical"
            is_lexical = index.backend == LexicalEmbedder.name
            if wanted_lexical == is_lexical or requested == "auto":
                if index.embedder is None:
                    index.embedder = get_embedder(
                        "bge" if not is_lexical else "lexical",
                        corpus=[skill_text(s) for s in taxonomy.skills],
                    )
                return index

    embedder = get_embedder(backend, corpus=[skill_text(s) for s in taxonomy.skills])
    index = VectorIndex.build(taxonomy, embedder)
    index.save(path)
    return index
