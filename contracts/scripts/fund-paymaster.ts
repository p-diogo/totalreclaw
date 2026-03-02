import { ethers } from "hardhat";
import * as fs from "fs";
import * as path from "path";

/**
 * Fund the paymaster with ETH so it can sponsor UserOperations.
 *
 * Usage:
 *   npx hardhat run scripts/fund-paymaster.ts --network baseSepolia
 *
 * Default: 0.1 ETH (enough for ~200-500 sponsored operations on Base L2).
 */

const FUND_AMOUNT = ethers.parseEther("0.1"); // 0.1 ETH

async function main() {
  const addrPath = path.join(__dirname, "..", "deployed-addresses.json");
  if (!fs.existsSync(addrPath)) {
    throw new Error("deployed-addresses.json not found. Run deploy.ts first.");
  }

  const addresses = JSON.parse(fs.readFileSync(addrPath, "utf-8"));
  const [deployer] = await ethers.getSigners();

  const before = await ethers.provider.getBalance(addresses.openMemoryPaymaster);
  console.log(`Paymaster balance before: ${ethers.formatEther(before)} ETH`);

  console.log(`Sending ${ethers.formatEther(FUND_AMOUNT)} ETH to paymaster...`);
  const tx = await deployer.sendTransaction({
    to: addresses.openMemoryPaymaster,
    value: FUND_AMOUNT,
  });
  await tx.wait();

  const after = await ethers.provider.getBalance(addresses.openMemoryPaymaster);
  console.log(`Paymaster balance after:  ${ethers.formatEther(after)} ETH`);
  console.log(`Tx: ${tx.hash}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
