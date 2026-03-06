/**
 * Journey 1: Core Memory Operations
 *
 * Tests the fundamental register -> store -> search -> decrypt -> export -> delete flow.
 * 12 assertions.
 */

import {
  IntegrationTestRunner,
  generateTestKeys,
  encryptFact,
  decryptFact,
  computeBlindIndices,
  computeContentFingerprint,
  buildFact,
} from '../test-helpers.js';

export default async function journey1Core(runner: IntegrationTestRunner): Promise<void> {
  runner.startJourney('Journey 1: Core Memory Operations');

  const keys = generateTestKeys();

  // ---- 1. Register user ----
  const regResp = await runner.register(keys.authKeyHash, keys.salt);
  runner.assertStatusCode(regResp, 200, 'Register returns 200');
  const regBody = (await regResp.json()) as { success: boolean; user_id?: string };
  runner.assert(!!regBody.user_id, 'Register response has user_id');
  const userId = regBody.user_id!;

  // ---- 2. Store 3 encrypted facts ----
  const plaintexts = [
    'Alice prefers dark roast coffee every morning',
    'Bob works at the downtown library on weekends',
    'Charlie runs five miles every Tuesday and Thursday',
  ];
  const facts = plaintexts.map((text) =>
    buildFact(text, keys.encryptionKey, keys.dedupKey, { withFingerprint: true }),
  );

  const storeResp = await runner.store(keys.authKeyHex, userId, facts);
  runner.assertStatusCode(storeResp, 200, 'Store returns 200');
  const storeBody = (await storeResp.json()) as { success: boolean; ids?: string[] };
  runner.assertEqual(storeBody.ids?.length, 3, 'Store returns 3 fact IDs');

  // ---- 3. Search by blind trapdoors matching one fact ----
  // Compute trapdoors for words from the first plaintext
  const searchTrapdoors = computeBlindIndices('alice coffee morning', keys.dedupKey);
  const searchResp = await runner.search(keys.authKeyHex, userId, searchTrapdoors);
  runner.assertStatusCode(searchResp, 200, 'Search returns 200');
  const searchBody = (await searchResp.json()) as {
    success: boolean;
    results?: Array<{ fact_id: string; encrypted_blob: string }>;
  };
  runner.assertGreaterThan(searchBody.results?.length ?? 0, 0, 'Search returns at least 1 result');

  // ---- 4. Decrypt a search result ----
  const firstResult = searchBody.results![0];
  const decrypted = decryptFact(firstResult.encrypted_blob, keys.encryptionKey);
  runner.assert(
    plaintexts.includes(decrypted),
    'Decrypted result matches one of the original facts',
  );

  // ---- 5. Export all facts ----
  const exportResp = await runner.exportFacts(keys.authKeyHex);
  runner.assertStatusCode(exportResp, 200, 'Export returns 200');
  const exportBody = (await exportResp.json()) as {
    success: boolean;
    facts?: Array<{ id: string }>;
    total_count?: number;
  };
  runner.assertEqual(exportBody.facts?.length, 3, 'Export returns 3 facts');

  // ---- 6. Delete one fact ----
  const factToDelete = facts[0].id;
  const deleteResp = await runner.deleteFact(keys.authKeyHex, factToDelete);
  runner.assertStatusCode(deleteResp, 200, 'Delete returns 200');
  const deleteBody = (await deleteResp.json()) as { success: boolean };
  runner.assert(deleteBody.success, 'Delete response indicates success');

  // ---- 7. Export again — verify 2 facts remain ----
  const exportResp2 = await runner.exportFacts(keys.authKeyHex);
  const exportBody2 = (await exportResp2.json()) as {
    success: boolean;
    facts?: Array<{ id: string }>;
  };
  runner.assertEqual(exportBody2.facts?.length, 2, 'Export after delete returns 2 facts');
  runner.assert(
    !exportBody2.facts!.some((f) => f.id === factToDelete),
    'Deleted fact is not present in export',
  );
}
