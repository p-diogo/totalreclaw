/**
 * JSON-RPC client for the relay's `/v1/bundler` proxy (ERC-4337).
 *
 * The relay proxies these calls to the Pimlico bundler/paymaster with its own
 * API key — clients never hold a Pimlico key. Auth is the same Bearer + wallet
 * headers the read path already sends.
 *
 * Scope: ONLY the methods Pimlico actually serves (gas price, sponsor, estimate,
 * send, receipt). The two node reads ERC-4337 also needs — `eth_call` for the
 * nonce and `eth_getCode` for the deployment check — are rejected by Pimlico
 * (-32601), so they live in `chain.ts` against a CORS-enabled public Gnosis RPC.
 *
 * This is a WRITE-path module — reached only via the lazy `userop.ts` chunk.
 */
import { SessionKeys } from "./types";
import { getServerUrl } from "./api";

export interface GasPriceTier {
  maxFeePerGas: string;
  maxPriorityFeePerGas: string;
}
export interface GasPriceResult {
  slow: GasPriceTier;
  standard: GasPriceTier;
  fast: GasPriceTier;
}

/** Fields the paymaster fills in during sponsorship. */
export interface SponsorResult {
  paymaster?: string;
  paymasterData?: string;
  paymasterVerificationGasLimit?: string;
  paymasterPostOpGasLimit?: string;
  callGasLimit?: string;
  verificationGasLimit?: string;
  preVerificationGas?: string;
  [k: string]: unknown;
}

export interface GasEstimateResult {
  callGasLimit?: string;
  verificationGasLimit?: string;
  preVerificationGas?: string;
  [k: string]: unknown;
}

export interface UserOperationReceipt {
  success: boolean;
  receipt?: { transactionHash?: string; [k: string]: unknown };
  [k: string]: unknown;
}

function bundlerHeaders(keys: SessionKeys): HeadersInit {
  return {
    "Content-Type": "application/json",
    Accept: "application/json",
    Authorization: `Bearer ${keys.authKeyHex}`,
    "X-Wallet-Address": keys.walletAddress,
    "X-TotalReclaw-Client": "ts-spa-vault",
  };
}

/** Raw JSON-RPC call to the relay bundler proxy. Throws on HTTP or RPC error. */
export async function bundlerRpc<T>(
  keys: SessionKeys,
  method: string,
  params: unknown[],
): Promise<T> {
  const res = await fetch(`${getServerUrl()}/v1/bundler`, {
    method: "POST",
    headers: bundlerHeaders(keys),
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`bundler ${method} → ${res.status}: ${body}`);
  }
  const json = (await res.json()) as { result?: T; error?: { message?: string } };
  if (json.error) {
    throw new Error(`bundler ${method}: ${json.error.message ?? JSON.stringify(json.error)}`);
  }
  return json.result as T;
}

export function getUserOperationGasPrice(keys: SessionKeys): Promise<GasPriceResult> {
  return bundlerRpc<GasPriceResult>(keys, "pimlico_getUserOperationGasPrice", []);
}

export function estimateUserOperationGas(
  keys: SessionKeys,
  unsignedOp: Record<string, unknown>,
  entryPoint: string,
): Promise<GasEstimateResult> {
  return bundlerRpc<GasEstimateResult>(keys, "eth_estimateUserOperationGas", [
    unsignedOp,
    entryPoint,
  ]);
}

export function sponsorUserOperation(
  keys: SessionKeys,
  unsignedOp: Record<string, unknown>,
  entryPoint: string,
): Promise<SponsorResult> {
  return bundlerRpc<SponsorResult>(keys, "pm_sponsorUserOperation", [unsignedOp, entryPoint]);
}

export function sendUserOperation(
  keys: SessionKeys,
  signedOp: Record<string, unknown>,
  entryPoint: string,
): Promise<string> {
  return bundlerRpc<string>(keys, "eth_sendUserOperation", [signedOp, entryPoint]);
}

export function getUserOperationReceipt(
  keys: SessionKeys,
  userOpHash: string,
): Promise<UserOperationReceipt | null> {
  return bundlerRpc<UserOperationReceipt | null>(keys, "eth_getUserOperationReceipt", [userOpHash]);
}
