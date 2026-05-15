/**
 * Semantic similarity scoring using @huggingface/transformers (runs in-browser).
 *
 * Model: Xenova/all-MiniLM-L6-v2  (~23 MB, loaded once and cached by the browser)
 * Task:  sentence similarity — cosine similarity between two embedded sentences
 *
 * Returns a score 0–100 where 100 = identical meaning.
 * The model handles paraphrases well: "PM resigns" ≈ "Prime Minister steps down" → high score.
 */

// Dynamically imported so the ~1.3 MB transformers library stays out of the main bundle.
// It is only fetched when the user opens the quiz for the first time.
type TransformersModule = typeof import('@huggingface/transformers');
type FeatureExtractionPipeline = Awaited<ReturnType<TransformersModule['pipeline']>>;

let extractor: FeatureExtractionPipeline | null = null;

async function getExtractor(): Promise<FeatureExtractionPipeline> {
  if (!extractor) {
    const { pipeline, env } = await import('@huggingface/transformers') as TransformersModule;
    env.allowLocalModels = false;
    extractor = await pipeline(
      'feature-extraction',
      'Xenova/all-MiniLM-L6-v2',
      { dtype: 'fp32' }
    );
  }
  return extractor;
}

function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot   += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  const denom = Math.sqrt(normA) * Math.sqrt(normB);
  return denom === 0 ? 0 : dot / denom;
}

function flattenTensor(tensor: { data: Float32Array | number[] }): number[] {
  return Array.from(tensor.data as Float32Array);
}

/**
 * Compute a similarity score (0–100) between the user's translation attempt
 * and the reference (canonical) translation.
 */
export async function computeScore(userText: string, referenceText: string): Promise<number> {
  if (!userText.trim()) return 0;

  const ext = await getExtractor();

  const [outputA, outputB] = await Promise.all([
    ext(userText,      { pooling: 'mean', normalize: true }),
    ext(referenceText, { pooling: 'mean', normalize: true }),
  ]);

  // The pipeline returns a Tensor; flatten to a plain number array
  const vecA = flattenTensor(outputA as { data: Float32Array });
  const vecB = flattenTensor(outputB as { data: Float32Array });

  const sim = cosineSimilarity(vecA, vecB);
  // Cosine similarity for sentence-transformers is typically 0.0–1.0 for positive pairs
  return Math.round(Math.max(0, Math.min(1, sim)) * 100);
}

/**
 * Warm up the model in the background (optional call).
 * Prevents the first quiz submission from feeling slow.
 */
export function warmUpModel(): void {
  getExtractor().catch(() => {
    // Silently ignore — scoring will retry when the user submits
  });
}
