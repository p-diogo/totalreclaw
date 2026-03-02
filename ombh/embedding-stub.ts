/**
 * TotalReclaw Plugin - Embedding Stub (v1 / No-Embedding Mode)
 *
 * Drop-in replacement for embedding.ts that always throws, forcing the
 * plugin to fall back to word-only blind indices (BM25 search).
 *
 * Used by the TotalReclaw v1 benchmark instance which deliberately excludes
 * @huggingface/transformers to measure word-only retrieval quality.
 */

const EMBEDDING_DIM = 384;

export async function generateEmbedding(_text: string): Promise<number[]> {
  throw new Error('Embeddings disabled (v1 mode — word-only blind indices)');
}

export function getEmbeddingDims(): number {
  return EMBEDDING_DIM;
}
