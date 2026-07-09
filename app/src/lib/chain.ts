/**
 * Minimal Gnosis chain-read client (write path only).
 *
 * ERC-4337 needs two node reads the Pimlico bundler does NOT serve — the relay
 * `/v1/bundler` proxy forwards to Pimlico, which rejects `eth_call` /
 * `eth_getCode` with -32601. The plugin (Node) falls back to a public RPC; the
 * browser can't reach the default public Gnosis RPC (no CORS header), so we use
 * a small failover list of CORS-enabled public endpoints for these two
 * read-only calls (nonce + deployment check). No auth, no secrets, reads only.
 */

/** EntryPoint.getNonce(address,uint192) selector. */
const GET_NONCE_SELECTOR = "35567e1a";

// CORS-enabled public Gnosis (chain 100) RPCs, tried in order. All verified to
// send `access-control-allow-origin: *`. Reads only (eth_call / eth_getCode).
const GNOSIS_RPCS = [
  "https://gnosis-rpc.publicnode.com",
  "https://gnosis.drpc.org",
  "https://rpc.gnosis.gateway.fm",
  "https://1rpc.io/gnosis",
];

async function chainRpc<T>(method: string, params: unknown[]): Promise<T> {
  let lastErr: unknown;
  for (const url of GNOSIS_RPCS) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
      });
      if (!res.ok) {
        lastErr = new Error(`${url} → ${res.status}`);
        continue;
      }
      const json = (await res.json()) as { result?: T; error?: { message?: string } };
      if (json.error) {
        lastErr = new Error(`${method}: ${json.error.message ?? JSON.stringify(json.error)}`);
        continue;
      }
      return json.result as T;
    } catch (e) {
      lastErr = e;
    }
  }
  throw new Error(
    `Gnosis RPC ${method} failed on all endpoints: ${
      lastErr instanceof Error ? lastErr.message : String(lastErr)
    }`,
  );
}

/** Read the EntryPoint nonce for `sender` (key = 0). */
export async function getNonce(entryPoint: string, sender: string): Promise<string> {
  const senderPadded = sender.slice(2).toLowerCase().padStart(64, "0");
  const calldata = `0x${GET_NONCE_SELECTOR}${senderPadded}${"0".repeat(64)}`;
  const result = await chainRpc<string>("eth_call", [{ to: entryPoint, data: calldata }, "latest"]);
  return result || "0x0";
}

/** Bytecode at `address` — `0x` / `0x0` means the Smart Account is undeployed. */
export function getCode(address: string): Promise<string> {
  return chainRpc<string>("eth_getCode", [address, "latest"]);
}
