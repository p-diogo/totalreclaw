/** Search: find facts matching any of the given blind index trapdoors */
export const SEARCH_BY_BLIND_INDEX = `
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

/** Fetch all active facts for an owner (bulk download / recovery) */
export const FETCH_ALL_FACTS = `
  query FetchAllFacts($owner: Bytes!, $first: Int!, $skip: Int!) {
    facts(
      where: { owner: $owner, isActive: true }
      orderBy: sequenceId
      orderDirection: asc
      first: $first
      skip: $skip
    ) {
      id
      encryptedBlob
      encryptedEmbedding
      decayScore
      isActive
      contentFp
      sequenceId
      blockNumber
      timestamp
      version
    }
  }
`;

/** Delta sync: facts since a given block number */
export const DELTA_SYNC_FACTS = `
  query DeltaSyncFacts($owner: Bytes!, $sinceBlock: BigInt!, $first: Int!, $skip: Int!) {
    facts(
      where: { owner: $owner, blockNumber_gt: $sinceBlock }
      orderBy: blockNumber
      orderDirection: asc
      first: $first
      skip: $skip
    ) {
      id
      encryptedBlob
      encryptedEmbedding
      decayScore
      isActive
      contentFp
      sequenceId
      blockNumber
      timestamp
      version
    }
  }
`;

/** Count facts for an owner (for dynamic pool sizing) */
export const COUNT_FACTS = `
  query CountFacts($owner: Bytes!) {
    facts(where: { owner: $owner, isActive: true }, first: 1000) {
      id
    }
  }
`;
