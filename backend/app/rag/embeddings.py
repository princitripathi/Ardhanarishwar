import re
import math
from typing import List, Dict, Tuple
from collections import Counter, defaultdict

# Lightweight local embeddings: TF-IDF with pure Python (no model download)
# Compatible with prototype and test environments without external APIs
# Falls back gracefully if sklearn unavailable (we use pure python anyway)

_TOKEN_PATTERN = re.compile(r"\b\w+\b")


def tokenize(text: str) -> List[str]:
    """Lowercase alphanumeric tokenization."""
    if not text or not isinstance(text, str):
        return []
    return _TOKEN_PATTERN.findall(text.lower())


class TfidfEmbedder:
    """Simple TF-IDF embedder built from local corpus.

    - fit() on chunks builds vocab + idf
    - vectorize() returns L2-normalized sparse dict {term: weight}
    - cosine similarity via dot product of normalized vectors
    """

    def __init__(self):
        self.vocab: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.num_docs: int = 0
        self._fitted: bool = False

    def fit(self, documents: List[str]) -> None:
        """Fit on list of chunk texts."""
        if not documents:
            self.vocab = {}
            self.idf = {}
            self.num_docs = 0
            self._fitted = True
            return

        # Document frequency
        df = Counter()
        self.num_docs = len(documents)
        for doc in documents:
            tokens = set(tokenize(doc))
            for t in tokens:
                df[t] += 1

        # Build vocab sorted for determinism
        self.vocab = {term: idx for idx, term in enumerate(sorted(df.keys()))}
        # idf = log(N / (df +1)) +1 smoothed
        self.idf = {}
        for term, freq in df.items():
            self.idf[term] = math.log(self.num_docs / (freq)) + 1.0 if freq else 1.0
        self._fitted = True

    def vectorize(self, text: str) -> Dict[str, float]:
        """Return L2-normalized TF-IDF dict."""
        if not self._fitted:
            # If not fitted, treat idf as 1.0
            tokens = tokenize(text)
            if not tokens:
                return {}
            tf = Counter(tokens)
            vec = {}
            norm_sq = 0.0
            for term, count in tf.items():
                w = (count / len(tokens)) * 1.0
                vec[term] = w
                norm_sq += w * w
            norm = math.sqrt(norm_sq) if norm_sq else 1.0
            return {k: v / norm for k, v in vec.items()}

        tokens = tokenize(text)
        if not tokens:
            return {}
        tf = Counter(tokens)
        total = len(tokens)
        vec: Dict[str, float] = {}
        norm_sq = 0.0
        for term, count in tf.items():
            if term not in self.vocab:
                continue  # OOV terms ignored (keeps vectors sparse and comparable)
            tf_val = count / total
            w = tf_val * self.idf.get(term, 1.0)
            vec[term] = w
            norm_sq += w * w

        # Handle OOV-only case: if vec empty but tokens exist, use 0 similarity (return empty)
        if not vec:
            return {}

        norm = math.sqrt(norm_sq) if norm_sq else 1.0
        return {k: v / norm for k, v in vec.items()}

    def vectorize_with_oov(self, text: str) -> Dict[str, float]:
        """Vectorize including OOV terms with idf=1.0 (for query where new terms appear)."""
        tokens = tokenize(text)
        if not tokens:
            return {}
        tf = Counter(tokens)
        total = len(tokens)
        vec: Dict[str, float] = {}
        norm_sq = 0.0
        for term, count in tf.items():
            tf_val = count / total
            idf = self.idf.get(term, 1.0)  # OOV gets 1.0
            w = tf_val * idf
            vec[term] = w
            norm_sq += w * w
        norm = math.sqrt(norm_sq) if norm_sq else 1.0
        return {k: v / norm for k, v in vec.items()}

    def cosine(self, vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
        """Cosine similarity for L2-normalized sparse dicts = dot product."""
        if not vec_a or not vec_b:
            return 0.0
        # Iterate over smaller
        if len(vec_a) > len(vec_b):
            vec_a, vec_b = vec_b, vec_a
        dot = 0.0
        for term, w in vec_a.items():
            if term in vec_b:
                dot += w * vec_b[term]
        # Vectors already normalized, dot is cosine
        # Clamp due to floating errors
        return max(0.0, min(1.0, dot))

    def is_fitted(self) -> bool:
        return self._fitted


# Singleton helpers for store
def build_tfidf_vectors(chunks: List[str], embedder: TfidfEmbedder = None) -> Tuple[List[Dict[str, float]], TfidfEmbedder]:
    """Build vectors for all chunks, fitting embedder if needed."""
    if embedder is None or not embedder.is_fitted():
        embedder = TfidfEmbedder()
        embedder.fit(chunks)
    vectors = [embedder.vectorize(c) for c in chunks]
    return vectors, embedder
