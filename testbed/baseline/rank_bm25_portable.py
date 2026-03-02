"""
Portable BM25 Implementation

A lightweight BM25 implementation included to avoid external dependency issues
when rank-bm25 is not available. This implements the same algorithm as BM25Okapi
from the rank-bm25 library.
"""

from typing import List
import math
import numpy as np


class BM25OkapiPortable:
    """
    Portable implementation of BM25 ranking algorithm.

    This follows the standard BM25 formulation:
    score(D, Q) = Σ IDF(qi) * (f(qi, D) * (k1 + 1)) / (f(qi, D) + k1 * (1 - b + b * |D| / avgdl))

    Where:
    - f(qi, D) is the term frequency of query term qi in document D
    - |D| is the document length
    - avgdl is the average document length in the corpus
    - k1 controls term frequency saturation (default 1.5)
    - b controls length normalization (default 0.75)
    """

    def __init__(
        self,
        corpus: List[List[str]],
        k1: float = 1.5,
        b: float = 0.75,
        epsilon: float = 0.25
    ):
        """
        Initialize BM25 with a tokenized corpus.

        Args:
            corpus: List of tokenized documents (each document is a list of tokens)
            k1: Term frequency saturation parameter
            b: Length normalization parameter
            epsilon: IDF floor parameter to prevent division by zero
        """
        self.k1 = k1
        self.b = b
        self.epsilon = epsilon
        self.corpus = corpus

        # Calculate document lengths
        self.doc_lens = [len(doc) for doc in corpus]

        # Calculate average document length
        self.avgdl = sum(self.doc_lens) / len(self.doc_lens) if self.doc_lens else 0

        # Build vocabulary and document frequency
        self.vocab = set()
        self.df = {}  # document frequency
        self.idf = {}  # inverse document frequency

        for doc in corpus:
            tokens = set(doc)
            for token in tokens:
                self.vocab.add(token)
                self.df[token] = self.df.get(token, 0) + 1

        # Calculate IDF with epsilon smoothing
        # IDF(qi) = log((N - df(qi) + 0.5) / (df(qi) + 0.5)) + 1
        # With epsilon floor: IDF = max(IDF, epsilon)
        N = len(corpus)
        for token in self.vocab:
            df = self.df[token]
            # Add 1 to avoid log of negative number when df > N
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
            self.idf[token] = max(idf, epsilon)

    def get_scores(self, query: List[str]) -> np.ndarray:
        """
        Calculate BM25 scores for a query against all documents.

        Args:
            query: Tokenized query (list of tokens)

        Returns:
            NumPy array of scores for each document
        """
        scores = np.zeros(len(self.corpus))

        for token in query:
            if token not in self.vocab:
                continue

            # Get IDF for this token
            idf = self.idf.get(token, 0)

            # Calculate score contribution for each document
            for i, doc in enumerate(self.corpus):
                # Count term frequency in this document
                tf = doc.count(token)

                if tf > 0:
                    # BM25 formula for this term
                    doc_len = self.doc_lens[i]
                    numerator = tf * (self.k1 + 1)
                    denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
                    scores[i] += idf * (numerator / denominator)

        return scores

    def get_batch_scores(self, queries: List[List[str]]) -> np.ndarray:
        """
        Calculate BM25 scores for multiple queries.

        Args:
            queries: List of tokenized queries

        Returns:
            2D NumPy array of shape (n_queries, n_docs)
        """
        return np.array([self.get_scores(query) for query in queries])

    def get_top_n(self, query: List[str], documents: List[str], n: int = 5) -> List[tuple]:
        """
        Get top-n documents for a query.

        Args:
            query: Tokenized query
            documents: Original document strings (for return values)
            n: Number of results to return

        Returns:
            List of (doc_index, score) tuples
        """
        scores = self.get_scores(query)
        top_indices = np.argsort(scores)[::-1][:n]
        return [(int(idx), float(scores[idx])) for idx in top_indices if scores[idx] > 0]
