import { sha256 } from '@noble/hashes/sha2.js';

const SUBGRAPH = 'http://localhost:8000/subgraphs/name/totalreclaw';

async function main() {
  // Generate a blind index for the word 'user' (same as E2E test)
  const token = 'user';
  const hash = Buffer.from(sha256(Buffer.from(token, 'utf8'))).toString('hex');
  console.log('Hash for "user":', hash);

  const owner = '0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266';

  // Test 1: Simple inline query (known to work from curl)
  console.log('\n--- Test 1: Inline query ---');
  const r1 = await fetch(SUBGRAPH, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: `{ blindIndexes(where: { hash_in: ["${hash}"], owner: "${owner}" }, first: 5) { fact { id } } }`,
    }),
  });
  console.log('Result:', JSON.stringify(await r1.json()));

  // Test 2: Parameterized query (same as E2E test uses)
  console.log('\n--- Test 2: Parameterized query ---');
  const r2 = await fetch(SUBGRAPH, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: `query SearchByBlindIndex($trapdoors: [String!]!, $owner: Bytes!, $first: Int!) {
        blindIndexes(
          where: { hash_in: $trapdoors, owner: $owner }
          first: $first
        ) {
          fact {
            id
            encryptedBlob
            encryptedEmbedding
            decayScore
            isActive
          }
        }
      }`,
      variables: {
        trapdoors: [hash],
        owner,
        first: 10,
      },
    }),
  });
  const data2 = await r2.json();
  console.log('Result:', JSON.stringify(data2).substring(0, 500));
  console.log('Matched:', data2?.data?.blindIndexes?.length ?? 'NONE');
}

main().catch(console.error);
