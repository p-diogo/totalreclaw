/**
 * Subgraph search path — queries facts via GraphQL hash_in.
 *
 * Used when TOTALRECLAW_SUBGRAPH_MODE=true. Replaces the HTTP POST
 * to /v1/search with a GraphQL query to the subgraph.
 */

import { getSubgraphConfig } from './subgraph-store.js';

export interface SubgraphSearchFact {
  id: string;
  encryptedBlob: string;
  encryptedEmbedding: string | null;
  decayScore: string;
  isActive: boolean;
}

const TRAPDOOR_BATCH_SIZE = 500;
const PAGE_SIZE = 1000;

/**
 * Search the subgraph for facts matching the given trapdoors.
 * Uses GraphQL hash_in query on BlindIndex entities.
 */
export async function searchSubgraph(
  owner: string,
  trapdoors: string[],
  maxCandidates: number,
): Promise<SubgraphSearchFact[]> {
  const config = getSubgraphConfig();
  const allResults = new Map<string, SubgraphSearchFact>();

  for (let i = 0; i < trapdoors.length; i += TRAPDOOR_BATCH_SIZE) {
    const batch = trapdoors.slice(i, i + TRAPDOOR_BATCH_SIZE);

    const query = `
      query SearchByBlindIndex($trapdoors: [String!]!, $owner: Bytes!, $first: Int!) {
        blindIndices(
          where: { hash_in: $trapdoors, owner: $owner }
          first: $first
        ) {
          fact {
            id
            encryptedBlob
            encryptedEmbedding
            decayScore
            isActive
            contentFp
            sequenceId
            version
          }
        }
      }
    `;

    try {
      const response = await fetch(config.subgraphEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          variables: {
            trapdoors: batch,
            owner,
            first: Math.min(maxCandidates, PAGE_SIZE),
          },
        }),
      });

      if (!response.ok) continue;

      const json = await response.json() as {
        data?: { blindIndices?: Array<{ fact: SubgraphSearchFact }> };
      };

      if (json.data?.blindIndices) {
        for (const entry of json.data.blindIndices) {
          if (entry.fact && !allResults.has(entry.fact.id)) {
            allResults.set(entry.fact.id, entry.fact);
          }
        }
      }
    } catch {
      // Network error on this batch — continue with remaining batches.
      continue;
    }

    if (allResults.size >= maxCandidates) break;
  }

  return Array.from(allResults.values());
}

/**
 * Get fact count from the subgraph for dynamic pool sizing.
 */
export async function getSubgraphFactCount(owner: string): Promise<number> {
  const config = getSubgraphConfig();

  const query = `
    query CountFacts($owner: Bytes!) {
      facts(where: { owner: $owner, isActive: true }, first: 1000) {
        id
      }
    }
  `;

  try {
    const response = await fetch(config.subgraphEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, variables: { owner } }),
    });

    if (!response.ok) return 0;

    const json = await response.json() as { data?: { facts?: Array<{ id: string }> } };
    return json.data?.facts?.length || 0;
  } catch {
    return 0;
  }
}
