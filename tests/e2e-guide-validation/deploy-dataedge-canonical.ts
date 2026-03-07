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

// Canonical Chiado RPC (NOT the forked rpc.chiadochain.net)
const CANONICAL_RPC = 'https://gnosis-chiado-rpc.publicnode.com';

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

  // 3. First, we need auth key for relay. Derive it the same way the plugin does.
  // For this script, we'll try without auth first (relay might allow unauthenticated bundler access)
  const bundlerUrl = `${RELAY_URL}/v1/bundler`;

  // Try to get auth key from the plugin's credential derivation
  // For now, pass auth key if available
  const authKeyHex = process.env.AUTH_KEY_HEX;
  const transportOptions = authKeyHex
    ? { fetchOptions: { headers: { Authorization: `Bearer ${authKeyHex}` } } }
    : {};

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

  // 7. Encode constructor args: _entryPoint = Smart Account address
  // In ERC-4337 flow: EntryPoint -> Smart Account -> DataEdge
  // So msg.sender in DataEdge fallback is the Smart Account
  const constructorArg = smartAccount.address;
  console.log(`Constructor arg (_entryPoint): ${constructorArg}`);

  // ABI-encode constructor argument (address is padded to 32 bytes)
  const encodedConstructorArg = encodePacked(
    ['bytes32'],
    [('0x' + constructorArg.slice(2).padStart(64, '0')) as Hex]
  );

  // Full init code = creation bytecode + ABI-encoded constructor args
  const initCode = (creationBytecode + constructorArg.slice(2).padStart(64, '0')) as Hex;

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

    // Read back the entryPoint to verify
    const entryPointValue = await publicClient.readContract({
      address: expectedAddress,
      abi: artifact.abi,
      functionName: 'entryPoint',
    });
    console.log(`entryPoint set to: ${entryPointValue}`);

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
