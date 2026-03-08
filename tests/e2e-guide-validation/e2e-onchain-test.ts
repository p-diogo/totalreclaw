/**
 * E2E On-Chain Test: Write fact via UserOp → verify subgraph indexes it.
 *
 * Tests the full pipeline:
 *   1. Derive keys from test mnemonic
 *   2. Encode a fact as protobuf
 *   3. Submit UserOp to DataEdge via relay/Pimlico
 *   4. Wait for tx confirmation
 *   5. Poll subgraph until the fact appears
 *
 * Usage: npx tsx e2e-onchain-test.ts
 */

import { createPublicClient, http, type Hex, type Address } from 'viem';
import { entryPoint07Address } from 'viem/account-abstraction';
import { mnemonicToAccount } from 'viem/accounts';
import { gnosisChiado } from 'viem/chains';
import { createSmartAccountClient } from 'permissionless';
import { toSimpleSmartAccount } from 'permissionless/accounts';
import { createPimlicoClient } from 'permissionless/clients/pimlico';
import { mnemonicToSeedSync } from '@scure/bip39';
import * as crypto from 'crypto';

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const MNEMONIC = 'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about';
const DATA_EDGE = '0xA84c5433110Ccc93e57ec387e630E86Bad86c36f' as Address;
const RELAY_URL = process.env.TOTALRECLAW_SERVER_URL || 'https://api.totalreclaw.xyz';
const SUBGRAPH_URL = 'https://api.studio.thegraph.com/query/41768/total-reclaw-chiado/v0.4.0';
const CANONICAL_RPC = 'https://rpc.chiado.gnosis.gateway.fm';

// ---------------------------------------------------------------------------
// Protobuf encoding (minimal, matches subgraph mapping)
// ---------------------------------------------------------------------------

function encodeVarint(value: number): Buffer {
  const bytes: number[] = [];
  let v = value >>> 0;
  while (v > 0x7f) {
    bytes.push((v & 0x7f) | 0x80);
    v >>>= 7;
  }
  bytes.push(v & 0x7f);
  return Buffer.from(bytes);
}

function writeString(parts: Buffer[], fieldNumber: number, value: string) {
  if (!value) return;
  const data = Buffer.from(value, 'utf-8');
  const key = (fieldNumber << 3) | 2;
  parts.push(encodeVarint(key));
  parts.push(encodeVarint(data.length));
  parts.push(data);
}

function writeBytes(parts: Buffer[], fieldNumber: number, value: Buffer) {
  const key = (fieldNumber << 3) | 2;
  parts.push(encodeVarint(key));
  parts.push(encodeVarint(value.length));
  parts.push(value);
}

function writeDouble(parts: Buffer[], fieldNumber: number, value: number) {
  const key = (fieldNumber << 3) | 1;
  parts.push(encodeVarint(key));
  const buf = Buffer.alloc(8);
  buf.writeDoubleLE(value);
  parts.push(buf);
}

function writeVarintField(parts: Buffer[], fieldNumber: number, value: number) {
  const key = (fieldNumber << 3) | 0;
  parts.push(encodeVarint(key));
  parts.push(encodeVarint(value));
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  console.log('=== E2E On-Chain Test ===\n');

  // 1. Derive auth key
  const seed = mnemonicToSeedSync(MNEMONIC.trim());
  const hkdfSalt = Buffer.from(seed.slice(0, 32));
  const seedBuf = Buffer.from(seed);
  const hkdfKey = crypto.hkdfSync('sha256', seedBuf, hkdfSalt, 'totalreclaw-auth-key-v1', 32);
  const authKeyHex = Buffer.from(hkdfKey).toString('hex');

  // 2. Build a test fact
  const factId = `e2e-test-${Date.now()}`;
  const owner = '0x2c0cf74b2b76110708ca431796367779e3738250'; // Smart Account
  const timestamp = new Date().toISOString();
  const encryptedBlob = crypto.randomBytes(64).toString('hex');
  const blindIndex1 = crypto.createHash('sha256').update('pedro').digest('hex');
  const blindIndex2 = crypto.createHash('sha256').update('lisbon').digest('hex');

  // 3. Encode as protobuf
  const parts: Buffer[] = [];
  writeString(parts, 1, factId);
  writeString(parts, 2, timestamp);
  writeString(parts, 3, owner);
  writeBytes(parts, 4, Buffer.from(encryptedBlob, 'hex'));
  writeString(parts, 5, blindIndex1);
  writeString(parts, 5, blindIndex2);
  writeDouble(parts, 6, 1.0); // decay_score
  writeVarintField(parts, 7, 1); // is_active
  writeVarintField(parts, 8, 2); // version
  writeString(parts, 9, 'e2e-test');
  writeString(parts, 10, crypto.createHash('sha256').update(factId).digest('hex'));
  writeString(parts, 11, 'test-agent');

  const protobuf = Buffer.concat(parts);
  console.log(`Fact ID: ${factId}`);
  console.log(`Protobuf size: ${protobuf.length} bytes`);

  // 4. Create Smart Account + send UserOp
  const ownerAccount = mnemonicToAccount(MNEMONIC);
  const bundlerUrl = `${RELAY_URL}/v1/bundler`;

  const authTransport = http(bundlerUrl, {
    fetchOptions: { headers: { Authorization: `Bearer ${authKeyHex}` } },
  });

  const publicClient = createPublicClient({
    chain: gnosisChiado,
    transport: http(CANONICAL_RPC),
  });

  const pimlicoClient = createPimlicoClient({
    chain: gnosisChiado,
    transport: authTransport,
    entryPoint: { address: entryPoint07Address, version: '0.7' },
  });

  const smartAccount = await toSimpleSmartAccount({
    client: publicClient,
    owner: ownerAccount,
    entryPoint: { address: entryPoint07Address, version: '0.7' },
  });

  console.log(`Smart Account: ${smartAccount.address}`);

  const smartAccountClient = createSmartAccountClient({
    account: smartAccount,
    chain: gnosisChiado,
    bundlerTransport: authTransport,
    paymaster: pimlicoClient,
    userOperation: {
      estimateFeesPerGas: async () => {
        return (await pimlicoClient.getUserOperationGasPrice()).fast;
      },
    },
  });

  // 5. Send UserOp
  const calldata = `0x${protobuf.toString('hex')}` as Hex;
  console.log('\nSending UserOp...');
  const userOpHash = await smartAccountClient.sendUserOperation({
    calls: [{ to: DATA_EDGE, value: 0n, data: calldata }],
  });
  console.log(`UserOp hash: ${userOpHash}`);

  // 6. Wait for receipt
  console.log('Waiting for transaction...');
  const receipt = await pimlicoClient.waitForUserOperationReceipt({
    hash: userOpHash,
  });
  console.log(`TX hash: ${receipt.receipt.transactionHash}`);
  console.log(`Success: ${receipt.success}`);
  console.log(`Block: ${receipt.receipt.blockNumber}`);

  if (!receipt.success) {
    console.error('FAIL: UserOp reverted');
    process.exit(1);
  }

  // 7. Poll subgraph for the fact
  console.log('\nPolling subgraph for indexed fact...');
  const maxRetries = 30;
  const pollInterval = 10_000; // 10s

  for (let i = 0; i < maxRetries; i++) {
    const query = `{
      facts(where: { id: "${factId}" }) {
        id
        owner
        blockNumber
        timestamp
        source
        agentId
        isActive
        version
        sequenceId
        blindIndices { hash }
      }
    }`;

    const res = await fetch(SUBGRAPH_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });

    const json = await res.json() as any;
    const facts = json?.data?.facts || [];

    if (facts.length > 0) {
      console.log(`\n✅ PASS: Fact indexed after ${(i + 1) * 10}s`);
      console.log(JSON.stringify(facts[0], null, 2));

      // Verify fields
      const fact = facts[0];
      const checks = [
        ['id', fact.id === factId],
        ['owner', fact.owner === owner],
        ['source', fact.source === 'e2e-test'],
        ['agentId', fact.agentId === 'test-agent'],
        ['isActive', fact.isActive === true],
        ['version', fact.version === 2],
        ['blindIndices', fact.blindIndices?.length === 2],
        ['sequenceId', fact.sequenceId > 0],
      ] as const;

      let allPass = true;
      for (const [name, ok] of checks) {
        console.log(`  ${ok ? '✅' : '❌'} ${name}`);
        if (!ok) allPass = false;
      }

      if (allPass) {
        console.log('\n✅ ALL CHECKS PASSED — Full pipeline verified!');
      } else {
        console.log('\n⚠️  Some checks failed — see above');
        process.exit(1);
      }
      return;
    }

    // Check subgraph sync status
    const metaRes = await fetch(SUBGRAPH_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: '{ _meta { block { number } hasIndexingErrors } }' }),
    });
    const meta = await metaRes.json() as any;
    const syncedBlock = meta?.data?._meta?.block?.number || '?';
    const txBlock = Number(receipt.receipt.blockNumber);
    const hasErrors = meta?.data?._meta?.hasIndexingErrors;

    console.log(`  Attempt ${i + 1}/${maxRetries}: subgraph at block ${syncedBlock}, tx at ${txBlock}${hasErrors ? ' [INDEXING ERRORS]' : ''}`);

    if (hasErrors) {
      console.error('FAIL: Subgraph has indexing errors');
      process.exit(1);
    }

    await new Promise(r => setTimeout(r, pollInterval));
  }

  console.error(`\nFAIL: Fact not indexed after ${maxRetries * 10}s`);
  process.exit(1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
