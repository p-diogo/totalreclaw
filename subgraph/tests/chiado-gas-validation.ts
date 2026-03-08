/**
 * Chiado Testnet Gas Validation Script for TotalReclaw
 *
 * Sends real transactions to the EventfulDataEdge contract on Gnosis Chiado
 * testnet and measures actual gas costs. Generates a JSON results file and
 * a markdown report with cost projections.
 *
 * Prerequisites:
 *   1. .env file at repo root with DEPLOYER_PRIVATE_KEY and CHIADO_RPC_URL
 *   2. Contract deployed at 0xA84c5433110Ccc93e57ec387e630E86Bad86c36f
 *   3. Deployer wallet has xDAI for gas
 *
 * Usage (from subgraph/):
 *   npx tsx --tsconfig tsconfig.node.json tests/chiado-gas-validation.ts
 */

import { ethers } from "ethers";
import * as dotenv from "dotenv";
import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

dotenv.config({ path: path.resolve(__dirname, "../../.env") });

const CHIADO_RPC = process.env.CHIADO_RPC_URL || "https://rpc.chiadochain.net";
const PRIVATE_KEY = process.env.DEPLOYER_PRIVATE_KEY;
const CONTRACT_ADDRESS = "0xA84c5433110Ccc93e57ec387e630E86Bad86c36f";

// xDAI is a stablecoin pegged to $1.00
const XDAI_PRICE_USD = 1.0;

if (!PRIVATE_KEY) {
  console.error("ERROR: DEPLOYER_PRIVATE_KEY not found in .env");
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FactPayload {
  id: string;
  timestamp: string;
  owner: string;
  encryptedBlob: string;
  blindIndices: string[];
  decayScore: number;
  source: string;
  contentFp: string;
  agentId: string;
  encryptedEmbedding?: string;
}

interface TestCase {
  label: string;
  description: string;
  wordCount: number;
  blindIndexCount: number;
  hasEmbedding: boolean;
}

interface TxResult {
  label: string;
  description: string;
  wordCount: number;
  blindIndexCount: number;
  hasEmbedding: boolean;
  calldataBytes: number;
  gasUsed: number;
  gasPrice: string;         // in wei
  gasPriceGwei: number;
  actualCostWei: string;
  actualCostXdai: number;
  actualCostUsd: number;
  gasPerByte: number;
  waitTimeMs: number;
  txHash: string;
  blockNumber: number;
  status: "success" | "failed";
  error?: string;
}

// ---------------------------------------------------------------------------
// Protobuf encoder (copied from gas-measurement.ts)
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

function encodeFactProtobuf(fact: FactPayload): Buffer {
  const parts: Buffer[] = [];

  const writeString = (fieldNumber: number, value: string) => {
    if (!value) return;
    const data = Buffer.from(value, "utf-8");
    const key = (fieldNumber << 3) | 2;
    parts.push(encodeVarint(key));
    parts.push(encodeVarint(data.length));
    parts.push(data);
  };

  const writeBytes = (fieldNumber: number, value: Buffer) => {
    const key = (fieldNumber << 3) | 2;
    parts.push(encodeVarint(key));
    parts.push(encodeVarint(value.length));
    parts.push(value);
  };

  const writeDouble = (fieldNumber: number, value: number) => {
    const key = (fieldNumber << 3) | 1;
    parts.push(encodeVarint(key));
    const buf = Buffer.alloc(8);
    buf.writeDoubleLE(value);
    parts.push(buf);
  };

  const writeVarintField = (fieldNumber: number, value: number) => {
    const key = (fieldNumber << 3) | 0;
    parts.push(encodeVarint(key));
    parts.push(encodeVarint(value));
  };

  writeString(1, fact.id);
  writeString(2, fact.timestamp);
  writeString(3, fact.owner);
  writeBytes(4, Buffer.from(fact.encryptedBlob, "hex"));

  for (const index of fact.blindIndices) {
    writeString(5, index);
  }

  writeDouble(6, fact.decayScore);
  writeVarintField(7, 1); // is_active = true
  writeVarintField(8, 2); // version = 2
  writeString(9, fact.source);
  writeString(10, fact.contentFp);
  writeString(11, fact.agentId);
  // Field 12 (sequence_id) assigned by subgraph mapping
  if (fact.encryptedEmbedding) {
    writeString(13, fact.encryptedEmbedding);
  }

  return Buffer.concat(parts);
}

// ---------------------------------------------------------------------------
// Synthetic payload generators (copied from gas-measurement.ts)
// ---------------------------------------------------------------------------

function randomHex(byteCount: number): string {
  return crypto.randomBytes(byteCount).toString("hex");
}

function randomSha256(): string {
  return crypto.createHash("sha256").update(crypto.randomBytes(32)).digest("hex");
}

function randomUuid(): string {
  return crypto.randomUUID();
}

/**
 * Generate synthetic encrypted blob.
 * Average English word = ~5 chars + 1 space = 6 bytes.
 * AES-GCM adds 12-byte IV + 16-byte auth tag = 28 bytes overhead.
 */
function generateEncryptedBlob(wordCount: number): string {
  const plaintextSize = wordCount * 6;
  const ciphertextSize = plaintextSize + 28;
  return randomHex(ciphertextSize);
}

/** Generate synthetic blind indices (SHA-256 hashes). */
function generateBlindIndices(count: number): string[] {
  const indices: string[] = [];
  for (let i = 0; i < count; i++) {
    indices.push(randomSha256());
  }
  return indices;
}

/**
 * Generate synthetic encrypted embedding.
 * 384-dim float32 = 384 * 4 = 1,536 bytes.
 * After AES-GCM: 1,536 + 28 = 1,564 bytes.
 */
function generateEncryptedEmbedding(): string {
  const embeddingBytes = 384 * 4;
  const ciphertextSize = embeddingBytes + 28;
  return randomHex(ciphertextSize);
}

/** Create a fact payload with specified parameters. */
function createFactPayload(
  wordCount: number,
  blindIndexCount: number,
  includeEmbedding: boolean,
): FactPayload {
  const payload: FactPayload = {
    id: randomUuid(),
    timestamp: new Date().toISOString(),
    owner: "0x" + randomHex(20),
    encryptedBlob: generateEncryptedBlob(wordCount),
    blindIndices: generateBlindIndices(blindIndexCount),
    decayScore: 0.95,
    source: "chiado-gas-validation",
    contentFp: randomSha256(),
    agentId: "benchmark-agent-001",
  };

  if (includeEmbedding) {
    payload.encryptedEmbedding = generateEncryptedEmbedding();
  }

  return payload;
}

// ---------------------------------------------------------------------------
// Test cases (as specified in the task)
// ---------------------------------------------------------------------------

const TEST_CASES: TestCase[] = [
  {
    label: "#1 Quick note",
    description: "remember my wifi password is X",
    wordCount: 10,
    blindIndexCount: 15,
    hasEmbedding: false,
  },
  {
    label: "#2 Short fact",
    description: "I prefer dark mode in all apps",
    wordCount: 20,
    blindIndexCount: 30,
    hasEmbedding: false,
  },
  {
    label: "#3 Short fact + embedding",
    description: "Same as #2 with semantic search",
    wordCount: 20,
    blindIndexCount: 30,
    hasEmbedding: true,
  },
  {
    label: "#4 Medium fact",
    description: "Meeting notes from standup",
    wordCount: 50,
    blindIndexCount: 60,
    hasEmbedding: false,
  },
  {
    label: "#5 Typical fact + embedding",
    description: "Most common OpenClaw usage",
    wordCount: 50,
    blindIndexCount: 60,
    hasEmbedding: true,
  },
  {
    label: "#6 Long conversation extract",
    description: "Full meeting summary",
    wordCount: 100,
    blindIndexCount: 90,
    hasEmbedding: true,
  },
  {
    label: "#7 Heavy indices",
    description: "Many unique keywords",
    wordCount: 30,
    blindIndexCount: 150,
    hasEmbedding: true,
  },
  {
    label: "#8 Minimal",
    description: "Tiny preference",
    wordCount: 5,
    blindIndexCount: 8,
    hasEmbedding: false,
  },
  {
    label: "#9 Large extract",
    description: "Long document summary",
    wordCount: 200,
    blindIndexCount: 120,
    hasEmbedding: true,
  },
  {
    label: "#10 Repeat of #5 (consistency)",
    description: "Verify consistent gas",
    wordCount: 50,
    blindIndexCount: 60,
    hasEmbedding: true,
  },
];

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function formatNumber(n: number): string {
  return n.toLocaleString("en-US");
}

function formatUsd(n: number, decimals?: number): string {
  if (n < 0.000001) return `$${n.toExponential(2)}`;
  if (n < 0.01) return `$${n.toFixed(decimals ?? 6)}`;
  if (n < 1) return `$${n.toFixed(decimals ?? 4)}`;
  return `$${n.toFixed(decimals ?? 2)}`;
}

function formatXdai(n: number): string {
  if (n < 0.000001) return `${n.toExponential(2)} xDAI`;
  if (n < 0.01) return `${n.toFixed(6)} xDAI`;
  return `${n.toFixed(4)} xDAI`;
}

// ---------------------------------------------------------------------------
// Transaction sending
// ---------------------------------------------------------------------------

async function sendFactTransaction(
  wallet: ethers.Wallet,
  contractAddress: string,
  testCase: TestCase,
): Promise<TxResult> {
  const fact = createFactPayload(
    testCase.wordCount,
    testCase.blindIndexCount,
    testCase.hasEmbedding,
  );

  const protobuf = encodeFactProtobuf(fact);
  const startTime = Date.now();

  try {
    // Send raw data to the fallback function
    const tx = await wallet.sendTransaction({
      to: contractAddress,
      data: ethers.hexlify(protobuf),
    });

    // Wait for confirmation
    const receipt = await tx.wait();
    const endTime = Date.now();

    if (!receipt) {
      throw new Error("Transaction receipt is null");
    }

    const gasUsed = Number(receipt.gasUsed);
    const gasPrice = receipt.gasPrice;
    const gasPriceNum = Number(gasPrice);
    const actualCostWei = BigInt(gasUsed) * gasPrice;
    const actualCostXdai = Number(ethers.formatEther(actualCostWei));

    return {
      label: testCase.label,
      description: testCase.description,
      wordCount: testCase.wordCount,
      blindIndexCount: testCase.blindIndexCount,
      hasEmbedding: testCase.hasEmbedding,
      calldataBytes: protobuf.length,
      gasUsed,
      gasPrice: gasPrice.toString(),
      gasPriceGwei: parseFloat(ethers.formatUnits(gasPrice, "gwei")),
      actualCostWei: actualCostWei.toString(),
      actualCostXdai,
      actualCostUsd: actualCostXdai * XDAI_PRICE_USD,
      gasPerByte: gasUsed / protobuf.length,
      waitTimeMs: endTime - startTime,
      txHash: receipt.hash,
      blockNumber: receipt.blockNumber,
      status: "success",
    };
  } catch (err: any) {
    const endTime = Date.now();
    return {
      label: testCase.label,
      description: testCase.description,
      wordCount: testCase.wordCount,
      blindIndexCount: testCase.blindIndexCount,
      hasEmbedding: testCase.hasEmbedding,
      calldataBytes: protobuf.length,
      gasUsed: 0,
      gasPrice: "0",
      gasPriceGwei: 0,
      actualCostWei: "0",
      actualCostXdai: 0,
      actualCostUsd: 0,
      gasPerByte: 0,
      waitTimeMs: endTime - startTime,
      txHash: "",
      blockNumber: 0,
      status: "failed",
      error: err.message,
    };
  }
}

// ---------------------------------------------------------------------------
// Report generation
// ---------------------------------------------------------------------------

function generateReport(
  results: TxResult[],
  walletAddress: string,
  startBalance: string,
  endBalance: string,
  networkInfo: { chainId: bigint; name: string },
): string {
  const lines: string[] = [];
  const successful = results.filter((r) => r.status === "success");
  const failed = results.filter((r) => r.status === "failed");

  // Header
  lines.push("# TotalReclaw Chiado Testnet Gas Validation Report");
  lines.push("");
  lines.push(`**Generated:** ${new Date().toISOString()}`);
  lines.push(`**Network:** Gnosis Chiado Testnet (chainId=${networkInfo.chainId})`);
  lines.push(`**RPC:** ${CHIADO_RPC}`);
  lines.push(`**Contract:** \`${CONTRACT_ADDRESS}\` (EventfulDataEdge)`);
  lines.push(`**Wallet:** \`${walletAddress}\``);
  lines.push(`**Balance before:** ${startBalance} xDAI`);
  lines.push(`**Balance after:** ${endBalance} xDAI`);
  lines.push(`**Total spent:** ${(parseFloat(startBalance) - parseFloat(endBalance)).toFixed(6)} xDAI`);
  lines.push(`**Transactions:** ${successful.length} succeeded, ${failed.length} failed, ${results.length} total`);
  lines.push("");

  if (failed.length > 0) {
    lines.push("## Failed Transactions");
    lines.push("");
    for (const f of failed) {
      lines.push(`- **${f.label}**: ${f.error}`);
    }
    lines.push("");
  }

  // Per-transaction results table
  lines.push("## Per-Transaction Results");
  lines.push("");
  lines.push("| # | Description | Words | Indices | Emb | Calldata (B) | Gas Used | Gas Price (Gwei) | Cost (xDAI) | Cost (USD) | Gas/Byte | Wait (s) |");
  lines.push("|---|-------------|-------|---------|-----|-------------|----------|-----------------|-------------|------------|----------|----------|");

  for (const r of successful) {
    lines.push(
      `| ${r.label} | ${r.description} | ${r.wordCount} | ${r.blindIndexCount} | ${r.hasEmbedding ? "Y" : "N"} | ${formatNumber(r.calldataBytes)} | ${formatNumber(r.gasUsed)} | ${r.gasPriceGwei.toFixed(2)} | ${formatXdai(r.actualCostXdai)} | ${formatUsd(r.actualCostUsd)} | ${r.gasPerByte.toFixed(1)} | ${(r.waitTimeMs / 1000).toFixed(1)} |`
    );
  }
  lines.push("");

  if (successful.length === 0) {
    lines.push("> **All transactions failed.** No cost analysis possible.");
    return lines.join("\n");
  }

  // Gas statistics
  const gasValues = successful.map((r) => r.gasUsed);
  const avgGas = gasValues.reduce((a, b) => a + b, 0) / gasValues.length;
  const minGas = Math.min(...gasValues);
  const maxGas = Math.max(...gasValues);

  const costValues = successful.map((r) => r.actualCostXdai);
  const avgCost = costValues.reduce((a, b) => a + b, 0) / costValues.length;
  const minCost = Math.min(...costValues);
  const maxCost = Math.max(...costValues);

  const gasPrices = successful.map((r) => r.gasPriceGwei);
  const avgGasPrice = gasPrices.reduce((a, b) => a + b, 0) / gasPrices.length;
  const minGasPrice = Math.min(...gasPrices);
  const maxGasPrice = Math.max(...gasPrices);

  const gasPerByteValues = successful.map((r) => r.gasPerByte);
  const avgGasPerByte = gasPerByteValues.reduce((a, b) => a + b, 0) / gasPerByteValues.length;

  const waitTimes = successful.map((r) => r.waitTimeMs / 1000);
  const avgWait = waitTimes.reduce((a, b) => a + b, 0) / waitTimes.length;

  lines.push("## Summary Statistics");
  lines.push("");
  lines.push("| Metric | Min | Avg | Max |");
  lines.push("|--------|-----|-----|-----|");
  lines.push(`| Gas Used | ${formatNumber(minGas)} | ${formatNumber(Math.round(avgGas))} | ${formatNumber(maxGas)} |`);
  lines.push(`| Cost (xDAI) | ${formatXdai(minCost)} | ${formatXdai(avgCost)} | ${formatXdai(maxCost)} |`);
  lines.push(`| Cost (USD) | ${formatUsd(minCost)} | ${formatUsd(avgCost)} | ${formatUsd(maxCost)} |`);
  lines.push(`| Gas Price (Gwei) | ${minGasPrice.toFixed(2)} | ${avgGasPrice.toFixed(2)} | ${maxGasPrice.toFixed(2)} |`);
  lines.push(`| Gas/Byte | ${Math.min(...gasPerByteValues).toFixed(1)} | ${avgGasPerByte.toFixed(1)} | ${Math.max(...gasPerByteValues).toFixed(1)} |`);
  lines.push(`| Confirmation Time (s) | ${Math.min(...waitTimes).toFixed(1)} | ${avgWait.toFixed(1)} | ${Math.max(...waitTimes).toFixed(1)} |`);
  lines.push("");

  // Consistency check: compare #5 and #10
  const tx5 = successful.find((r) => r.label.startsWith("#5"));
  const tx10 = successful.find((r) => r.label.startsWith("#10"));
  if (tx5 && tx10) {
    const gasDiff = Math.abs(tx5.gasUsed - tx10.gasUsed);
    const gasDiffPct = ((gasDiff / tx5.gasUsed) * 100).toFixed(1);
    const costDiff = Math.abs(tx5.actualCostXdai - tx10.actualCostXdai);
    lines.push("## Consistency Check (#5 vs #10 -- identical payload specs)");
    lines.push("");
    lines.push(`| Metric | #5 | #10 | Difference |`);
    lines.push(`|--------|-----|------|-----------|`);
    lines.push(`| Gas Used | ${formatNumber(tx5.gasUsed)} | ${formatNumber(tx10.gasUsed)} | ${formatNumber(gasDiff)} (${gasDiffPct}%) |`);
    lines.push(`| Cost (xDAI) | ${formatXdai(tx5.actualCostXdai)} | ${formatXdai(tx10.actualCostXdai)} | ${formatXdai(costDiff)} |`);
    lines.push(`| Calldata (B) | ${formatNumber(tx5.calldataBytes)} | ${formatNumber(tx10.calldataBytes)} | ${formatNumber(Math.abs(tx5.calldataBytes - tx10.calldataBytes))} |`);
    lines.push("");
    lines.push(`> Gas difference of ${gasDiffPct}% is expected due to random payload content (different zero/non-zero byte ratios in calldata).`);
    lines.push("");
  }

  // Embedding cost impact
  const withEmb = successful.filter((r) => r.hasEmbedding);
  const withoutEmb = successful.filter((r) => !r.hasEmbedding);
  if (withEmb.length > 0 && withoutEmb.length > 0) {
    lines.push("## Embedding Cost Impact");
    lines.push("");
    lines.push("| Word Count | Gas (no emb) | Gas (with emb) | Calldata (no emb) | Calldata (with emb) | Gas Overhead | Cost Overhead |");
    lines.push("|------------|-------------|----------------|-------------------|--------------------|--------------|--------------| ");

    const wordCounts = [...new Set(successful.map((r) => r.wordCount))];
    for (const wc of wordCounts.sort((a, b) => a - b)) {
      const we = successful.find((r) => r.wordCount === wc && r.hasEmbedding);
      const woe = successful.find((r) => r.wordCount === wc && !r.hasEmbedding);
      if (we && woe) {
        const gasOverhead = we.gasUsed - woe.gasUsed;
        const gasPct = ((gasOverhead / woe.gasUsed) * 100).toFixed(1);
        const costOverhead = we.actualCostXdai - woe.actualCostXdai;
        lines.push(
          `| ${wc} | ${formatNumber(woe.gasUsed)} | ${formatNumber(we.gasUsed)} | ${formatNumber(woe.calldataBytes)} | ${formatNumber(we.calldataBytes)} | +${formatNumber(gasOverhead)} (+${gasPct}%) | +${formatXdai(costOverhead)} |`
        );
      }
    }
    lines.push("");
  }

  // Cost projections
  lines.push("## Cost Projections");
  lines.push("");

  // Use "typical fact + embedding" (#5) as the representative
  const representative = tx5 || successful.find((r) => r.hasEmbedding) || successful[0];
  lines.push(`**Representative fact:** ${representative.label} (${representative.description})`);
  lines.push(`- Calldata: ${formatNumber(representative.calldataBytes)} bytes`);
  lines.push(`- Gas: ${formatNumber(representative.gasUsed)}`);
  lines.push(`- Cost: ${formatXdai(representative.actualCostXdai)} (${formatUsd(representative.actualCostUsd)})`);
  lines.push(`- Gas price: ${representative.gasPriceGwei.toFixed(2)} Gwei`);
  lines.push("");

  // Per-user monthly costs
  const factsPerDayScenarios = [10, 50, 100];
  lines.push("### Monthly Cost Per User");
  lines.push("");
  lines.push("| Usage | Facts/Day | Facts/Month | Monthly Cost (xDAI) | Monthly Cost (USD) |");
  lines.push("|-------|-----------|-------------|--------------------|--------------------|");

  for (const fpd of factsPerDayScenarios) {
    const fpm = fpd * 30;
    const monthlyCost = representative.actualCostXdai * fpm;
    lines.push(
      `| ${fpd === 10 ? "Casual" : fpd === 50 ? "Active" : "Power user"} | ${fpd} | ${formatNumber(fpm)} | ${formatXdai(monthlyCost)} | ${formatUsd(monthlyCost * XDAI_PRICE_USD)} |`
    );
  }
  lines.push("");

  // Platform-level costs
  const userCounts = [100, 1000, 10000];
  const factsPerUserPerDay = 10; // casual user
  lines.push(`### Platform Monthly Cost (${factsPerUserPerDay} facts/user/day)`);
  lines.push("");
  lines.push("| Users | Facts/Month | Monthly Gas Cost (xDAI) | Monthly Gas Cost (USD) | Per-User Cost |");
  lines.push("|-------|-------------|------------------------|----------------------|---------------|");

  for (const uc of userCounts) {
    const totalFacts = uc * factsPerUserPerDay * 30;
    const totalCost = representative.actualCostXdai * totalFacts;
    const perUser = totalCost / uc;
    lines.push(
      `| ${formatNumber(uc)} | ${formatNumber(totalFacts)} | ${formatXdai(totalCost)} | ${formatUsd(totalCost * XDAI_PRICE_USD)} | ${formatUsd(perUser * XDAI_PRICE_USD)} |`
    );
  }
  lines.push("");

  // Power user scenario
  const factsPerPowerUser = 50;
  lines.push(`### Platform Monthly Cost (${factsPerPowerUser} facts/user/day -- power users)`);
  lines.push("");
  lines.push("| Users | Facts/Month | Monthly Gas Cost (xDAI) | Monthly Gas Cost (USD) | Per-User Cost |");
  lines.push("|-------|-------------|------------------------|----------------------|---------------|");

  for (const uc of userCounts) {
    const totalFacts = uc * factsPerPowerUser * 30;
    const totalCost = representative.actualCostXdai * totalFacts;
    const perUser = totalCost / uc;
    lines.push(
      `| ${formatNumber(uc)} | ${formatNumber(totalFacts)} | ${formatXdai(totalCost)} | ${formatUsd(totalCost * XDAI_PRICE_USD)} | ${formatUsd(perUser * XDAI_PRICE_USD)} |`
    );
  }
  lines.push("");

  // Comparison with theoretical estimate
  const theoreticalCostPerFact = 0.00076; // from comprehensive-report.md
  lines.push("## Comparison with Theoretical Estimate");
  lines.push("");
  lines.push("The comprehensive report estimated $0.00076/fact on Gnosis Chain based on:");
  lines.push("- 379,650 gas/fact (Hardhat measurement)");
  lines.push("- 2 Gwei gas price assumption");
  lines.push("");
  lines.push("| Metric | Theoretical | Actual (Chiado) | Difference |");
  lines.push("|--------|-------------|----------------|------------|");
  lines.push(
    `| Gas per typical fact | 379,650 | ${formatNumber(representative.gasUsed)} | ${representative.gasUsed > 379650 ? "+" : ""}${formatNumber(representative.gasUsed - 379650)} (${(((representative.gasUsed - 379650) / 379650) * 100).toFixed(1)}%) |`
  );
  lines.push(
    `| Gas price | 2.00 Gwei | ${representative.gasPriceGwei.toFixed(2)} Gwei | ${representative.gasPriceGwei > 2 ? "+" : ""}${(representative.gasPriceGwei - 2).toFixed(2)} Gwei |`
  );
  lines.push(
    `| Cost per fact | ${formatUsd(theoreticalCostPerFact)} | ${formatUsd(representative.actualCostUsd)} | ${representative.actualCostUsd > theoreticalCostPerFact ? "+" : ""}${formatUsd(representative.actualCostUsd - theoreticalCostPerFact)} |`
  );

  const ratio = representative.actualCostUsd / theoreticalCostPerFact;
  lines.push("");
  if (ratio > 1) {
    lines.push(`> Actual cost is **${ratio.toFixed(1)}x higher** than theoretical. This is likely due to ${representative.gasPriceGwei > 2 ? "higher gas prices on Chiado testnet" : "differences in calldata zero/non-zero byte ratios"}.`);
  } else if (ratio < 1) {
    lines.push(`> Actual cost is **${(1 / ratio).toFixed(1)}x lower** than theoretical. This is likely due to ${representative.gasPriceGwei < 2 ? "lower gas prices on Chiado testnet" : "favorable calldata byte ratios"}.`);
  } else {
    lines.push(`> Actual cost matches theoretical estimate closely.`);
  }
  lines.push("");

  // Gnosis mainnet projection
  lines.push("## Gnosis Mainnet Projection");
  lines.push("");
  lines.push("Gnosis mainnet typically has lower gas prices than Chiado testnet.");
  lines.push("Using conservative estimates:");
  lines.push("");

  const mainnetGasPrices = [1.0, 2.0, 5.0]; // Gwei
  lines.push("| Gas Price (Gwei) | Cost/Fact (xDAI) | Cost/Fact (USD) | Monthly (10 facts/day) | Monthly (50 facts/day) |");
  lines.push("|-----------------|-----------------|----------------|----------------------|----------------------|");

  for (const gp of mainnetGasPrices) {
    const costPerFact = (representative.gasUsed * gp * 1e-9);
    const monthly10 = costPerFact * 10 * 30;
    const monthly50 = costPerFact * 50 * 30;
    lines.push(
      `| ${gp.toFixed(1)} | ${formatXdai(costPerFact)} | ${formatUsd(costPerFact * XDAI_PRICE_USD)} | ${formatUsd(monthly10 * XDAI_PRICE_USD)} | ${formatUsd(monthly50 * XDAI_PRICE_USD)} |`
    );
  }
  lines.push("");

  // Transaction hashes for verification
  lines.push("## Transaction Hashes (Chiado Explorer)");
  lines.push("");
  for (const r of successful) {
    lines.push(`- **${r.label}**: [\`${r.txHash}\`](https://gnosis-chiado.blockscout.com/tx/${r.txHash})`);
  }
  lines.push("");

  // Key takeaways
  lines.push("## Key Takeaways");
  lines.push("");
  lines.push(`1. **Actual cost per typical fact:** ${formatUsd(representative.actualCostUsd)} on Chiado testnet`);
  lines.push(`2. **Gas price observed:** ${avgGasPrice.toFixed(2)} Gwei (avg across ${successful.length} transactions)`);
  lines.push(`3. **Confirmation time:** ${avgWait.toFixed(1)}s average (Chiado has ~5s block times)`);
  lines.push(`4. **Embedding overhead:** adds ~3,128 bytes of calldata per fact`);
  lines.push(`5. **Blind indices scale linearly:** each index adds ~66 bytes (64 hex chars + protobuf overhead)`);
  lines.push(`6. **Gnosis Chain remains extremely cheap** for on-chain memory storage`);
  lines.push("");

  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  console.log("=== TotalReclaw Chiado Testnet Gas Validation ===\n");

  // Connect to Chiado
  const provider = new ethers.JsonRpcProvider(CHIADO_RPC);
  let networkInfo: { chainId: bigint; name: string };

  try {
    const network = await provider.getNetwork();
    networkInfo = { chainId: network.chainId, name: network.name };
    console.log(`Connected to network: chainId=${network.chainId}, name=${network.name}`);
  } catch (err: any) {
    console.error("ERROR: Cannot connect to Chiado RPC at", CHIADO_RPC);
    console.error("Error:", err.message);
    process.exit(1);
  }

  // Create wallet
  const wallet = new ethers.Wallet(PRIVATE_KEY!, provider);
  const walletAddress = await wallet.getAddress();
  console.log(`Wallet: ${walletAddress}`);

  // Check balance
  const startBalanceWei = await provider.getBalance(walletAddress);
  const startBalance = ethers.formatEther(startBalanceWei);
  console.log(`Balance: ${startBalance} xDAI`);

  if (startBalanceWei === 0n) {
    console.error("ERROR: Wallet has 0 xDAI. Get testnet xDAI from https://faucet.chiadochain.net/");
    process.exit(1);
  }

  // Verify contract exists
  const code = await provider.getCode(CONTRACT_ADDRESS);
  if (code === "0x") {
    console.error("ERROR: No contract at", CONTRACT_ADDRESS);
    process.exit(1);
  }
  console.log(`Contract verified at ${CONTRACT_ADDRESS} (${code.length / 2 - 1} bytes)`);

  // Check entryPoint — the fallback requires msg.sender == entryPoint
  const contract = new ethers.Contract(
    CONTRACT_ADDRESS,
    ["function entryPoint() view returns (address)", "function owner() view returns (address)"],
    provider,
  );

  const entryPoint = await contract.entryPoint();
  const owner = await contract.owner();
  console.log(`Contract entryPoint: ${entryPoint}`);
  console.log(`Contract owner: ${owner}`);

  if (entryPoint.toLowerCase() !== walletAddress.toLowerCase()) {
    console.log(`\nWARNING: Wallet (${walletAddress}) != entryPoint (${entryPoint})`);
    console.log("The fallback function requires msg.sender == entryPoint.");

    // Check if we are the owner and can update
    if (owner.toLowerCase() === walletAddress.toLowerCase()) {
      console.log("We are the owner -- updating entryPoint to our wallet address...");
      const contractWithSigner = new ethers.Contract(
        CONTRACT_ADDRESS,
        ["function setEntryPoint(address _newEntryPoint) external"],
        wallet,
      );
      const tx = await contractWithSigner.setEntryPoint(walletAddress);
      console.log(`setEntryPoint tx sent: ${tx.hash}`);
      await tx.wait();
      console.log("entryPoint updated successfully.");
    } else {
      console.error("ERROR: We are NOT the owner. Cannot update entryPoint.");
      console.error("Transactions will fail with 'Not EntryPoint' revert.");
      console.error("Deploy a new contract or get the owner to call setEntryPoint().");
      process.exit(1);
    }
  }

  console.log(`\nSending ${TEST_CASES.length} test transactions...\n`);

  // Send transactions sequentially (Chiado has ~5s block times)
  const results: TxResult[] = [];

  for (let i = 0; i < TEST_CASES.length; i++) {
    const tc = TEST_CASES[i];
    process.stdout.write(`  [${i + 1}/${TEST_CASES.length}] ${tc.label} (${tc.wordCount}w, ${tc.blindIndexCount}idx, ${tc.hasEmbedding ? "emb" : "no-emb"}) ... `);

    const result = await sendFactTransaction(wallet, CONTRACT_ADDRESS, tc);

    if (result.status === "success") {
      console.log(
        `${formatNumber(result.gasUsed)} gas, ${formatXdai(result.actualCostXdai)}, ${(result.waitTimeMs / 1000).toFixed(1)}s`
      );
    } else {
      console.log(`FAILED: ${result.error}`);
    }

    results.push(result);
  }

  const successCount = results.filter((r) => r.status === "success").length;
  const failCount = results.filter((r) => r.status === "failed").length;
  console.log(`\n${successCount}/${results.length} transactions succeeded${failCount > 0 ? `, ${failCount} failed` : ""}.\n`);

  // Get final balance
  const endBalanceWei = await provider.getBalance(walletAddress);
  const endBalance = ethers.formatEther(endBalanceWei);
  const spent = parseFloat(startBalance) - parseFloat(endBalance);
  console.log(`Balance after: ${endBalance} xDAI (spent: ${spent.toFixed(6)} xDAI)`);

  // Save JSON results
  const jsonPath = path.resolve(__dirname, "chiado-gas-results.json");
  const jsonOutput = {
    generated: new Date().toISOString(),
    network: {
      name: "Gnosis Chiado Testnet",
      chainId: Number(networkInfo.chainId),
      rpc: CHIADO_RPC,
    },
    contract: CONTRACT_ADDRESS,
    wallet: walletAddress,
    balanceBefore: startBalance,
    balanceAfter: endBalance,
    totalSpent: spent.toFixed(6),
    results,
  };
  fs.writeFileSync(jsonPath, JSON.stringify(jsonOutput, null, 2));
  console.log(`\nJSON results saved to ${jsonPath}`);

  // Generate markdown report
  const report = generateReport(results, walletAddress, startBalance, endBalance, networkInfo);
  const reportPath = path.resolve(__dirname, "chiado-gas-report.md");
  fs.writeFileSync(reportPath, report);
  console.log(`Markdown report saved to ${reportPath}`);

  // Quick summary
  console.log("\n--- Quick Summary ---");
  const successful = results.filter((r) => r.status === "success");
  for (const r of successful) {
    console.log(
      `  ${r.label.padEnd(40)} ${String(r.gasUsed).padStart(8)} gas  ${String(r.calldataBytes).padStart(7)} B  ${r.gasPriceGwei.toFixed(2)} Gwei  ${formatXdai(r.actualCostXdai).padStart(16)}  ${formatUsd(r.actualCostUsd).padStart(12)}`
    );
  }

  if (successful.length > 0) {
    const avgCost = successful.reduce((a, r) => a + r.actualCostXdai, 0) / successful.length;
    console.log(`\n  Average cost per fact: ${formatXdai(avgCost)} (${formatUsd(avgCost * XDAI_PRICE_USD)})`);
  }
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
