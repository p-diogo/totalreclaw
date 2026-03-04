import { run } from "hardhat";
import * as fs from "fs";
import * as path from "path";

/**
 * Verify deployed contracts on the block explorer (Blockscout / Etherscan).
 *
 * Usage:
 *   npx hardhat run scripts/verify.ts --network chiado      (Gnosis Chiado — Blockscout, no API key needed)
 *   npx hardhat run scripts/verify.ts --network gnosis       (Gnosis Chain — Gnosisscan)
 *   npx hardhat run scripts/verify.ts --network baseSepolia  (Base Sepolia — Basescan)
 *
 * Prerequisites:
 *   - Contracts deployed (deploy.ts run first)
 *   - API key set in ../.env (not required for Blockscout on Chiado)
 */

const ENTRYPOINT_V07 = "0x0000000071727De22E5E9d8BAf0edAc6f37da032";
const MAX_OPS_PER_HOUR = 100;
const RATE_LIMIT_WINDOW = 3600;

async function main() {
  const addrPath = path.join(__dirname, "..", "deployed-addresses.json");
  if (!fs.existsSync(addrPath)) {
    throw new Error("deployed-addresses.json not found. Run deploy.ts first.");
  }

  const addresses = JSON.parse(fs.readFileSync(addrPath, "utf-8"));
  console.log(`Verifying contracts on ${addresses.network} block explorer...`);

  // Verify EventfulDataEdge
  console.log(`\nVerifying EventfulDataEdge at ${addresses.eventfulDataEdge}...`);
  try {
    await run("verify:verify", {
      address: addresses.eventfulDataEdge,
      constructorArguments: [ENTRYPOINT_V07],
    });
    console.log("  EventfulDataEdge verified.");
  } catch (e: any) {
    if (e.message.includes("Already Verified")) {
      console.log("  Already verified.");
    } else {
      console.error("  Verification failed:", e.message);
    }
  }

  // Verify TotalReclawPaymaster
  console.log(`\nVerifying TotalReclawPaymaster at ${addresses.openMemoryPaymaster}...`);
  try {
    await run("verify:verify", {
      address: addresses.openMemoryPaymaster,
      constructorArguments: [
        ENTRYPOINT_V07,
        addresses.eventfulDataEdge,
        MAX_OPS_PER_HOUR,
        RATE_LIMIT_WINDOW,
      ],
    });
    console.log("  TotalReclawPaymaster verified.");
  } catch (e: any) {
    if (e.message.includes("Already Verified")) {
      console.log("  Already verified.");
    } else {
      console.error("  Verification failed:", e.message);
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
