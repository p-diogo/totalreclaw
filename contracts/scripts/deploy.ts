import { ethers, network } from "hardhat";
import * as fs from "fs";
import * as path from "path";

/**
 * Deploy EventfulDataEdge and TotalReclawPaymaster to the target network.
 *
 * Usage:
 *   npx hardhat run scripts/deploy.ts --network baseSepolia
 *   npx hardhat run scripts/deploy.ts --network hardhat  (local test)
 *
 * Prerequisites:
 *   - DEPLOYER_PRIVATE_KEY set in ../.env
 *   - Deployer has Base Sepolia ETH (get from faucet)
 *
 * The ERC-4337 EntryPoint v0.7 address on Base Sepolia is:
 *   0x0000000071727De22E5E9d8BAf0edAc6f37da032
 * (same address on all EVM chains — deterministic CREATE2 deployment)
 */

// ERC-4337 EntryPoint v0.7 — canonical address on all chains
const ENTRYPOINT_V07 = "0x0000000071727De22E5E9d8BAf0edAc6f37da032";

// Paymaster config
const MAX_OPS_PER_HOUR = 100;
const RATE_LIMIT_WINDOW = 3600; // 1 hour

interface DeployedAddresses {
  network: string;
  chainId: number;
  entryPoint: string;
  eventfulDataEdge: string;
  openMemoryPaymaster: string;
  deployedAt: string;
  deployer: string;
  blockNumber: number;
}

async function main() {
  const [deployer] = await ethers.getSigners();
  const balance = await ethers.provider.getBalance(deployer.address);

  console.log("=== TotalReclaw Contract Deployment ===");
  console.log(`Network:  ${network.name}`);
  console.log(`Deployer: ${deployer.address}`);
  console.log(`Balance:  ${ethers.formatEther(balance)} ETH`);
  console.log("");

  if (balance === 0n) {
    throw new Error("Deployer has no ETH. Fund from faucet first.");
  }

  // Use canonical EntryPoint for live networks, deployer for local testing
  const entryPointAddr = network.name === "hardhat"
    ? deployer.address
    : ENTRYPOINT_V07;

  console.log(`EntryPoint: ${entryPointAddr}`);
  console.log("");

  // 1. Deploy EventfulDataEdge
  console.log("Deploying EventfulDataEdge...");
  const EdgeFactory = await ethers.getContractFactory("EventfulDataEdge");
  const edge = await EdgeFactory.deploy(entryPointAddr);
  await edge.waitForDeployment();
  const edgeAddr = await edge.getAddress();
  const edgeTx = edge.deploymentTransaction();
  console.log(`  Address: ${edgeAddr}`);
  console.log(`  Tx:      ${edgeTx?.hash}`);
  console.log("");

  // 2. Deploy TotalReclawPaymaster
  console.log("Deploying TotalReclawPaymaster...");
  const PaymasterFactory = await ethers.getContractFactory("TotalReclawPaymaster");
  const paymaster = await PaymasterFactory.deploy(
    entryPointAddr,
    edgeAddr,
    MAX_OPS_PER_HOUR,
    RATE_LIMIT_WINDOW
  );
  await paymaster.waitForDeployment();
  const paymasterAddr = await paymaster.getAddress();
  const paymasterTx = paymaster.deploymentTransaction();
  console.log(`  Address: ${paymasterAddr}`);
  console.log(`  Tx:      ${paymasterTx?.hash}`);
  console.log("");

  // 3. Save deployed addresses
  const chainId = (await ethers.provider.getNetwork()).chainId;
  const blockNumber = await ethers.provider.getBlockNumber();

  const addresses: DeployedAddresses = {
    network: network.name,
    chainId: Number(chainId),
    entryPoint: entryPointAddr,
    eventfulDataEdge: edgeAddr,
    openMemoryPaymaster: paymasterAddr,
    deployedAt: new Date().toISOString(),
    deployer: deployer.address,
    blockNumber,
  };

  const outPath = path.join(__dirname, "..", "deployed-addresses.json");
  fs.writeFileSync(outPath, JSON.stringify(addresses, null, 2));
  console.log(`Addresses saved to ${outPath}`);

  // 4. Copy ABI to subgraph
  const abiSrcDir = path.join(__dirname, "..", "artifacts", "contracts", "EventfulDataEdge.sol");
  const abiDstDir = path.join(__dirname, "..", "..", "subgraph", "abis");
  if (!fs.existsSync(abiDstDir)) fs.mkdirSync(abiDstDir, { recursive: true });
  fs.copyFileSync(
    path.join(abiSrcDir, "EventfulDataEdge.json"),
    path.join(abiDstDir, "EventfulDataEdge.json")
  );
  console.log("ABI copied to subgraph/abis/");

  console.log("");
  console.log("=== Deployment Complete ===");
  console.log(`Next steps:`);
  console.log(`  1. Fund paymaster: npx hardhat run scripts/fund-paymaster.ts --network ${network.name}`);
  console.log(`  2. Verify contracts: npx hardhat run scripts/verify.ts --network ${network.name}`);
  console.log(`  3. Update subgraph/subgraph.yaml with address: ${edgeAddr}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
