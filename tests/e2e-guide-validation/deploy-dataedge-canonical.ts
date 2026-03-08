/**
 * Deploy EventfulDataEdge to canonical Chiado chain via Smart Account + Pimlico.
 *
 * Uses the CREATE2 deterministic deployer (0x4e59b44847b379578588920cA78FbF26c0B4956C)
 * so the Smart Account (gas-sponsored by Pimlico) can deploy without needing xDAI.
 *
 * Usage: npx tsx deploy-dataedge-canonical.ts
 */

import { createPublicClient, http, encodePacked, type Hex, type Address } from 'viem';
import { entryPoint07Address } from 'viem/account-abstraction';
import { mnemonicToAccount } from 'viem/accounts';
import { gnosisChiado } from 'viem/chains';
import { createSmartAccountClient } from 'permissionless';
import { toSimpleSmartAccount } from 'permissionless/accounts';
import { createPimlicoClient } from 'permissionless/clients/pimlico';
import * as fs from 'fs';
import * as path from 'path';
import * as crypto from 'crypto';

// Canonical Chiado RPC (NOT the forked rpc.chiadochain.net, NOT stale publicnode)
const CANONICAL_RPC = 'https://rpc.chiado.gnosis.gateway.fm';

// Arachnid's deterministic CREATE2 deployer (exists on all EVM chains)
const CREATE2_FACTORY = '0x4e59b44847b379578588920cA78FbF26c0B4956C' as Address;

// Relay server for Pimlico bundler proxy
const RELAY_URL = process.env.TOTALRECLAW_SERVER_URL || 'https://api.totalreclaw.xyz';

// Test mnemonic (same as docker-compose)
const MNEMONIC = 'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about';

async function main() {
  // Load compiled bytecode
  const artifactPath = path.join(__dirname, '../../contracts/artifacts/contracts/EventfulDataEdge.sol/EventfulDataEdge.json');
  const artifact = JSON.parse(fs.readFileSync(artifactPath, 'utf-8'));
  const creationBytecode = artifact.bytecode as Hex;

  console.log('=== Deploy EventfulDataEdge to Canonical Chiado ===');
  console.log(`RPC: ${CANONICAL_RPC}`);
  console.log(`Relay: ${RELAY_URL}`);

  // 1. Derive accounts
  const ownerAccount = mnemonicToAccount(MNEMONIC);
  console.log(`EOA: ${ownerAccount.address}`);

  // 2. Create public client pointing to CANONICAL chain
  const publicClient = createPublicClient({
    chain: gnosisChiado,
    transport: http(CANONICAL_RPC),
  });

  const chainHead = await publicClient.getBlockNumber();
  console.log(`Chain head: ${chainHead}`);

  // 3. Derive HKDF auth key from mnemonic (same derivation as plugin crypto.ts)
  const bundlerUrl = `${RELAY_URL}/v1/bundler`;

  // BIP-39: mnemonic -> 512-bit seed via PBKDF2
  const { mnemonicToSeedSync } = await import('@scure/bip39');
  const seed = mnemonicToSeedSync(MNEMONIC.trim());
  const hkdfSalt = Buffer.from(seed.slice(0, 32));
  const seedBuf = Buffer.from(seed);

  // HKDF-SHA256 to derive auth key
  const hkdfKey = crypto.hkdfSync('sha256', seedBuf, hkdfSalt, 'totalreclaw-auth-key-v1', 32);
  const authKeyHex = Buffer.from(hkdfKey).toString('hex');
  console.log(`Auth key derived (first 8): ${authKeyHex.slice(0, 8)}...`);

  const transportOptions = { fetchOptions: { headers: { Authorization: `Bearer ${authKeyHex}` } } };

  const authTransport = http(bundlerUrl, transportOptions);

  // 4. Create Pimlico client
  const pimlicoClient = createPimlicoClient({
    chain: gnosisChiado,
    transport: authTransport,
    entryPoint: {
      address: entryPoint07Address,
      version: '0.7',
    },
  });

  // 5. Create Smart Account
  const smartAccount = await toSimpleSmartAccount({
    client: publicClient,
    owner: ownerAccount,
    entryPoint: {
      address: entryPoint07Address,
      version: '0.7',
    },
  });

  console.log(`Smart Account: ${smartAccount.address}`);

  // 6. Create smart account client
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

  // 7. No constructor args — contract is permissionless
  const initCode = creationBytecode;

  // 8. CREATE2 salt (use a deterministic salt)
  const salt = '0x0000000000000000000000000000000000000000000000000000000000000001' as Hex;

  // 9. Calculate expected address
  const { getContractAddress } = await import('viem');
  const expectedAddress = getContractAddress({
    bytecode: initCode,
    from: CREATE2_FACTORY,
    opcode: 'CREATE2',
    salt,
  });
  console.log(`Expected DataEdge address: ${expectedAddress}`);

  // Check if already deployed
  const existingCode = await publicClient.getCode({ address: expectedAddress });
  if (existingCode && existingCode !== '0x') {
    console.log('Contract already deployed at this address!');
    return;
  }

  // 10. Deploy via CREATE2 factory
  // The factory expects: salt (32 bytes) + initCode
  const factoryCalldata = (salt + initCode.slice(2)) as Hex;

  console.log('\nSending deployment UserOp...');
  const userOpHash = await smartAccountClient.sendUserOperation({
    calls: [
      {
        to: CREATE2_FACTORY,
        value: 0n,
        data: factoryCalldata,
      },
    ],
  });

  console.log(`UserOp hash: ${userOpHash}`);

  // 11. Wait for receipt
  console.log('Waiting for transaction...');
  const receipt = await pimlicoClient.waitForUserOperationReceipt({
    hash: userOpHash,
  });

  console.log(`TX hash: ${receipt.receipt.transactionHash}`);
  console.log(`Success: ${receipt.success}`);
  console.log(`Block: ${receipt.receipt.blockNumber}`);

  // 12. Verify deployment
  const deployedCode = await publicClient.getCode({ address: expectedAddress });
  if (deployedCode && deployedCode !== '0x') {
    console.log(`\nDataEdge deployed at: ${expectedAddress}`);
    console.log(`Code length: ${deployedCode.length} chars`);

    const ownerValue = await publicClient.readContract({
      address: expectedAddress,
      abi: artifact.abi,
      functionName: 'owner',
    });
    console.log(`owner set to: ${ownerValue}`);
  } else {
    console.error('Deployment failed - no code at expected address');
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
