/**
 * Journey 2: Content Deduplication
 *
 * Tests content fingerprint-based dedup: storing the same fact twice should
 * not create a duplicate; storing a different fact should succeed.
 * 6 assertions.
 */

import {
  IntegrationTestRunner,
  generateTestKeys,
  buildFact,
} from '../test-helpers.js';

export default async function journey2Dedup(runner: IntegrationTestRunner): Promise<void> {
  runner.startJourney('Journey 2: Content Deduplication');

  const keys = generateTestKeys();

  // ---- 1. Register fresh user ----
  const regResp = await runner.register(keys.authKeyHash, keys.salt);
  runner.assertStatusCode(regResp, 200, 'Register returns 200');
  const regBody = (await regResp.json()) as { success: boolean; user_id?: string };
  const userId = regBody.user_id!;

  // ---- 2. Store fact A with a content fingerprint ----
  const factA = buildFact(
    'Alice loves hiking in the mountains on sunny days',
    keys.encryptionKey,
    keys.dedupKey,
    { withFingerprint: true },
  );
  const storeResp1 = await runner.store(keys.authKeyHex, userId, [factA]);
  runner.assertStatusCode(storeResp1, 200, 'First store returns 200');
  const storeBody1 = (await storeResp1.json()) as {
    success: boolean;
    ids?: string[];
    duplicate_ids?: string[] | null;
  };
  runner.assertEqual(storeBody1.ids?.length, 1, 'First store creates 1 fact');

  // ---- 3. Store same fact A again with same content_fp ----
  // Rebuild with same text to get same content_fp, but new id
  const factADup = buildFact(
    'Alice loves hiking in the mountains on sunny days',
    keys.encryptionKey,
    keys.dedupKey,
    { withFingerprint: true },
  );
  const storeResp2 = await runner.store(keys.authKeyHex, userId, [factADup]);
  const storeBody2 = (await storeResp2.json()) as {
    success: boolean;
    ids?: string[];
    duplicate_ids?: string[] | null;
  };
  // The server skips the duplicate — ids should be empty and duplicate_ids should have the original
  runner.assert(
    (storeBody2.ids?.length ?? 0) === 0 || (storeBody2.duplicate_ids?.length ?? 0) > 0,
    'Duplicate store detected — either ids empty or duplicate_ids populated',
  );

  // ---- 4. Store different fact B ----
  const factB = buildFact(
    'Bob enjoys reading science fiction novels before bed',
    keys.encryptionKey,
    keys.dedupKey,
    { withFingerprint: true },
  );
  const storeResp3 = await runner.store(keys.authKeyHex, userId, [factB]);
  const storeBody3 = (await storeResp3.json()) as {
    success: boolean;
    ids?: string[];
  };
  runner.assertEqual(storeBody3.ids?.length, 1, 'Different fact stores successfully');

  // ---- 5. Export all — verify exactly 2 unique facts ----
  const exportResp = await runner.exportFacts(keys.authKeyHex);
  const exportBody = (await exportResp.json()) as {
    success: boolean;
    facts?: Array<{ id: string }>;
    total_count?: number;
  };
  runner.assertEqual(exportBody.facts?.length, 2, 'Export returns exactly 2 facts (dedup worked)');
}
