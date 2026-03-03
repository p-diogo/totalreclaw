/**
 * Subgraph search path — queries facts via GraphQL hash_in.
 *
 * Used when TOTALRECLAW_SUBGRAPH_MODE=true. Replaces the HTTP POST
 * to /v1/search with a GraphQL query to the subgraph.
 *
 * Improvements (v3):
 *   A1: blindIndices → blindIndexes (Graph Node pluralization)
 *   A2: Small parallel batches (5 trapdoors each) for recall
 *   A3: orderBy: id, orderDirection: desc (recency proxy)
 *   A4: Cursor-based pagination for saturated batches
 *   C4: globalStates for lightweight fact count
 */

import { getSubgraphConfig } from './subgraph-store.js';

export interface SubgraphSearchFact {
  id: string;
  encryptedBlob: string;
  encryptedEmbedding: string | null;
  decayScore: string;
  timestamp: string;
  isActive: boolean;
}

/** Small batches so rare trapdoor matches aren't drowned by common ones. */
const TRAPDOOR_BATCH_SIZE = parseInt(process.env.TOTALRECLAW_TRAPDOOR_BATCH_SIZE ?? '5', 10);
const PAGE_SIZE = 1000;

/**
 * Execute a single GraphQL query against the subgraph endpoint.
 * Returns null on any network or HTTP error (never throws).
 */
async function gqlQuery<T>(
  endpoint: string,
  query: string,
  variables: Record<string, unknown>,
): Promise<T | null> {
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, variables }),
    });
    if (!response.ok) return null;
    const json = await response.json() as { data?: T };
    return json.data ?? null;
  } catch {
    return null;
  }
}

/** GraphQL query for blind index lookup — uses Graph Node's `blindIndexes` pluralization. */
const SEARCH_QUERY = `
  query SearchByBlindIndex($trapdoors: [String!]!, $owner: Bytes!, $first: Int!) {
    blindIndexes(
      where: { hash_in: $trapdoors, owner: $owner }
      first: $first
      orderBy: id
      orderDirection: desc
    ) {
      id
      fact {
        id
        encryptedBlob
        encryptedEmbedding
        decayScore
        timestamp
        isActive
        contentFp
        sequenceId
        version
      }
    }
  }
`;

/** Pagination query — cursor-based using id_gt, ascending for deterministic walk. */
const PAGINATE_QUERY = `
  query PaginateBlindIndex($trapdoors: [String!]!, $owner: Bytes!, $first: Int!, $lastId: String!) {
    blindIndexes(
      where: { hash_in: $trapdoors, owner: $owner, id_gt: $lastId }
      first: $first
      orderBy: id
      orderDirection: asc
    ) {
      id
      fact {
        id
        encryptedBlob
        encryptedEmbedding
        timestamp
        decayScore
        isActive
        contentFp
        sequenceId
        version
      }
    }
  }
`;

interface BlindIndexEntry {
  id: string;
  fact: SubgraphSearchFact;
}

interface SearchResponse {
  blindIndexes?: BlindIndexEntry[];
}

/**
 * Search the subgraph for facts matching the given trapdoors.
 *
 * Strategy:
 *   1. Split trapdoors into small chunks (TRAPDOOR_BATCH_SIZE=5).
 *   2. Fire all chunks in parallel via Promise.all.
 *   3. If any chunk returns exactly PAGE_SIZE results (saturated),
 *      paginate that chunk using id_gt cursor until exhausted or
 *      maxCandidates reached.
 *   4. Dedup across all chunks by fact id.
 */
export async function searchSubgraph(
  owner: string,
  trapdoors: string[],
  maxCandidates: number,
): Promise<SubgraphSearchFact[]> {
  const config = getSubgraphConfig();
  const allResults = new Map<string, SubgraphSearchFact>();

  // Split trapdoors into small chunks for parallel dispatch.
  const chunks: string[][] = [];
  for (let i = 0; i < trapdoors.length; i += TRAPDOOR_BATCH_SIZE) {
    chunks.push(trapdoors.slice(i, i + TRAPDOOR_BATCH_SIZE));
  }

  // Phase 1: Parallel initial queries (one per chunk).
  const initialResults = await Promise.all(
    chunks.map(async (chunk) => {
      const data = await gqlQuery<SearchResponse>(
        config.subgraphEndpoint,
        SEARCH_QUERY,
        { trapdoors: chunk, owner, first: PAGE_SIZE },
      );
      return { chunk, entries: data?.blindIndexes ?? [] };
    }),
  );

  // Collect initial results and identify saturated batches.
  const saturatedChunks: string[][] = [];
  for (const { chunk, entries } of initialResults) {
    for (const entry of entries) {
      if (entry.fact && !allResults.has(entry.fact.id)) {
        allResults.set(entry.fact.id, entry.fact);
      }
    }
    if (entries.length >= PAGE_SIZE) {
      saturatedChunks.push(chunk);
    }
  }

  // Phase 2: Cursor-based pagination for saturated batches.
  // Only paginate if we haven't yet reached maxCandidates.
  for (const chunk of saturatedChunks) {
    if (allResults.size >= maxCandidates) break;

    // Find the last blind-index id from the initial results for this chunk.
    // We need to re-query with ascending order for deterministic cursor walk.
    let lastId = '';

    while (allResults.size < maxCandidates) {
      const data = await gqlQuery<SearchResponse>(
        config.subgraphEndpoint,
        PAGINATE_QUERY,
        { trapdoors: chunk, owner, first: PAGE_SIZE, lastId },
      );

      const entries = data?.blindIndexes ?? [];
      if (entries.length === 0) break;

      for (const entry of entries) {
        if (entry.fact && !allResults.has(entry.fact.id)) {
          allResults.set(entry.fact.id, entry.fact);
        }
      }

      // If we got fewer than PAGE_SIZE, this chunk is exhausted.
      if (entries.length < PAGE_SIZE) break;

      lastId = entries[entries.length - 1].id;
    }
  }

  return Array.from(allResults.values());
}

/**
 * Get fact count from the subgraph for dynamic pool sizing.
 * Uses the globalStates entity for a lightweight single-row lookup
 * instead of fetching and counting individual fact IDs.
 */
export async function getSubgraphFactCount(owner: string): Promise<number> {
  const config = getSubgraphConfig();

  // globalStates is a singleton entity (id: "global") with aggregate counters.
  // It is NOT per-owner — it tracks totals across the entire subgraph.
  const query = `
    query FactCount {
      globalStates(first: 1) {
        totalFacts
      }
    }
  `;

  const data = await gqlQuery<{ globalStates?: Array<{ totalFacts: string }> }>(
    config.subgraphEndpoint,
    query,
    {},
  );

  if (data?.globalStates && data.globalStates.length > 0) {
    const count = parseInt(data.globalStates[0].totalFacts, 10);
    return isNaN(count) ? 0 : count;
  }

  return 0;
}
