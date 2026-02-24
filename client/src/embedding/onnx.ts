/**
 * ONNX Embedding Model
 *
 * Uses ONNX Runtime to run the all-MiniLM-L6-v2 model for text embeddings.
 * Produces 384-dimensional vectors suitable for semantic search.
 */

import * as ort from 'onnxruntime-node';
import * as path from 'path';
import * as fs from 'fs';
import { OpenMemoryError, OpenMemoryErrorCode } from '../types';

/** Expected embedding dimension for all-MiniLM-L6-v2 */
const EMBEDDING_DIM = 384;

/** Default model filename */
const DEFAULT_MODEL_FILENAME = 'all-MiniLM-L6-v2.onnx';

/** Default model directory */
const DEFAULT_MODEL_DIR = 'models';

/**
 * Embedding model using ONNX Runtime
 */
export class EmbeddingModel {
  private session: ort.InferenceSession | null = null;
  private modelPath: string | null = null;
  private isLoaded: boolean = false;

  /**
   * Load the ONNX model
   *
   * @param modelPath - Path to ONNX model file (optional, uses default if not provided)
   */
  async load(modelPath?: string): Promise<void> {
    // Resolve model path
    if (modelPath) {
      this.modelPath = modelPath;
    } else {
      // Try to find default model location
      const possiblePaths = [
        path.join(process.cwd(), DEFAULT_MODEL_DIR, DEFAULT_MODEL_FILENAME),
        path.join(__dirname, '..', '..', DEFAULT_MODEL_DIR, DEFAULT_MODEL_FILENAME),
        path.join(__dirname, '..', '..', '..', DEFAULT_MODEL_DIR, DEFAULT_MODEL_FILENAME),
      ];

      for (const p of possiblePaths) {
        if (fs.existsSync(p)) {
          this.modelPath = p;
          break;
        }
      }

      if (!this.modelPath) {
        throw new OpenMemoryError(
          OpenMemoryErrorCode.MODEL_LOAD_FAILED,
          `Model not found. Please download all-MiniLM-L6-v2.onnx and place it in the models/ directory, or provide the path explicitly.`
        );
      }
    }

    try {
      // Create ONNX inference session
      this.session = await ort.InferenceSession.create(this.modelPath, {
        executionProviders: ['cpu'],
        graphOptimizationLevel: 'all',
      });

      this.isLoaded = true;
    } catch (error) {
      throw new OpenMemoryError(
        OpenMemoryErrorCode.MODEL_LOAD_FAILED,
        `Failed to load ONNX model: ${error instanceof Error ? error.message : 'Unknown error'}`
      );
    }
  }

  /**
   * Check if the model is loaded
   */
  isReady(): boolean {
    return this.isLoaded && this.session !== null;
  }

  /**
   * Get the embedding dimension
   */
  getDimension(): number {
    return EMBEDDING_DIM;
  }

  /**
   * Simple tokenizer for all-MiniLM-L6-v2
   *
   * This is a basic whitespace and punctuation tokenizer.
   * For production use, consider using a proper BERT tokenizer.
   *
   * @param text - Text to tokenize
   * @returns Array of tokens
   */
  private tokenize(text: string): string[] {
    // Basic tokenization - lowercase and split on whitespace/punctuation
    return text
      .toLowerCase()
      .replace(/[^\w\s]/g, ' ')
      .split(/\s+/)
      .filter((t) => t.length > 0);
  }

  /**
   * Convert tokens to input IDs (simple hash-based mapping)
   *
   * Note: This is a simplified implementation. For best results,
   * use the actual WordPiece/BPE tokenizer from the model.
   *
   * @param tokens - Tokens to convert
   * @param maxLength - Maximum sequence length
   * @returns Input IDs and attention mask
   */
  private tokensToIds(
    tokens: string[],
    maxLength: number = 128
  ): { inputIds: number[]; attentionMask: number[] } {
    // This is a placeholder - in production, use the actual tokenizer vocabulary
    // For now, we'll use a hash-based approach that works for testing
    const inputIds: number[] = [];
    const attentionMask: number[] = [];

    // Add [CLS] token (typically ID 101 for BERT-like models)
    inputIds.push(101);
    attentionMask.push(1);

    // Convert tokens to IDs using simple hash
    for (let i = 0; i < Math.min(tokens.length, maxLength - 2); i++) {
      // Hash token to a reasonable ID range (vocab size is typically ~30K)
      const hash = this.simpleHash(tokens[i]);
      const tokenId = (hash % 30000) + 1000; // Avoid special tokens
      inputIds.push(tokenId);
      attentionMask.push(1);
    }

    // Add [SEP] token (typically ID 102 for BERT-like models)
    inputIds.push(102);
    attentionMask.push(1);

    // Pad to maxLength
    while (inputIds.length < maxLength) {
      inputIds.push(0); // Padding token
      attentionMask.push(0);
    }

    return { inputIds, attentionMask };
  }

  /**
   * Simple string hash function
   */
  private simpleHash(str: string): number {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    return Math.abs(hash);
  }

  /**
   * Embed a single text
   *
   * @param text - Text to embed
   * @returns 384-dimensional embedding vector
   */
  async embed(text: string): Promise<number[]> {
    if (!this.isReady()) {
      throw new OpenMemoryError(
        OpenMemoryErrorCode.EMBEDDING_FAILED,
        'Model not loaded. Call load() first.'
      );
    }

    try {
      // Tokenize
      const tokens = this.tokenize(text);
      const { inputIds, attentionMask } = this.tokensToIds(tokens);

      // Create input tensors
      const inputIdsTensor = new ort.Tensor(
        'int64',
        BigInt64Array.from(inputIds.map(BigInt)),
        [1, inputIds.length]
      );

      const attentionMaskTensor = new ort.Tensor(
        'int64',
        BigInt64Array.from(attentionMask.map(BigInt)),
        [1, attentionMask.length]
      );

      // Run inference
      const feeds: Record<string, ort.Tensor> = {
        input_ids: inputIdsTensor,
        attention_mask: attentionMaskTensor,
      };

      // Some models also need token_type_ids
      if (this.session!.inputNames.includes('token_type_ids')) {
        const tokenTypeIds = new ort.Tensor(
          'int64',
          new BigInt64Array(inputIds.length).fill(0n),
          [1, inputIds.length]
        );
        feeds.token_type_ids = tokenTypeIds;
      }

      const results = await this.session!.run(feeds);

      // Get the output (usually last_hidden_state or sentence_embedding)
      const outputName = this.session!.outputNames[0];
      const output = results[outputName];

      // Mean pooling over sequence dimension (take [CLS] token or average)
      // For all-MiniLM-L6-v2, output shape is [1, seq_len, 384]
      const data = output.data as Float32Array;
      const seqLen = inputIds.length;
      const embedding: number[] = [];

      // Use CLS token embedding (first token)
      for (let i = 0; i < EMBEDDING_DIM; i++) {
        embedding.push(data[i]);
      }

      // Normalize the embedding
      return this.normalizeVector(embedding);
    } catch (error) {
      throw new OpenMemoryError(
        OpenMemoryErrorCode.EMBEDDING_FAILED,
        `Embedding failed: ${error instanceof Error ? error.message : 'Unknown error'}`
      );
    }
  }

  /**
   * Embed multiple texts in batch
   *
   * @param texts - Texts to embed
   * @returns Array of 384-dimensional embedding vectors
   */
  async embedBatch(texts: string[]): Promise<number[][]> {
    // Process in batches for memory efficiency
    const embeddings: number[][] = [];

    for (const text of texts) {
      const embedding = await this.embed(text);
      embeddings.push(embedding);
    }

    return embeddings;
  }

  /**
   * Normalize a vector to unit length
   */
  private normalizeVector(vector: number[]): number[] {
    let norm = 0;
    for (const val of vector) {
      norm += val * val;
    }
    norm = Math.sqrt(norm);

    if (norm === 0) {
      return vector;
    }

    return vector.map((val) => val / norm);
  }

  /**
   * Dispose of the ONNX session
   */
  async dispose(): Promise<void> {
    if (this.session) {
      await this.session.release();
      this.session = null;
      this.isLoaded = false;
    }
  }
}

/**
 * Create a dummy embedding for testing
 *
 * Useful when ONNX model is not available.
 *
 * @param seed - Seed for reproducible random embeddings
 * @returns 384-dimensional random embedding
 */
export function createDummyEmbedding(seed?: number): number[] {
  const dim = EMBEDDING_DIM;
  const embedding: number[] = [];
  let s = seed ?? Date.now();

  // Simple seeded random
  const random = () => {
    s = (s * 1103515245 + 12345) & 0x7fffffff;
    return s / 0x7fffffff;
  };

  // Generate random values
  for (let i = 0; i < dim; i++) {
    // Gaussian distribution via Box-Muller
    const u1 = random();
    const u2 = random();
    const z = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
    embedding.push(z);
  }

  // Normalize
  let norm = 0;
  for (const val of embedding) {
    norm += val * val;
  }
  norm = Math.sqrt(norm);

  return embedding.map((val) => val / norm);
}

/**
 * Create deterministic embedding from text hash
 *
 * This creates a consistent (but not semantically meaningful) embedding
 * based on the text content. Useful for testing without ONNX model.
 *
 * @param text - Text to create embedding for
 * @returns 384-dimensional deterministic embedding
 */
export function createHashBasedEmbedding(text: string): number[] {
  const crypto = require('crypto');
  const embedding: number[] = [];

  // Generate embedding dimensions from text hash
  for (let i = 0; i < EMBEDDING_DIM; i++) {
    const hash = crypto
      .createHash('sha256')
      .update(`${text}:${i}`)
      .digest();
    // Convert first 4 bytes to float in range [-1, 1]
    const value = hash.readInt32LE(0) / 2147483648.0;
    embedding.push(value);
  }

  // Normalize
  let norm = 0;
  for (const val of embedding) {
    norm += val * val;
  }
  norm = Math.sqrt(norm);

  return embedding.map((val) => val / norm);
}
