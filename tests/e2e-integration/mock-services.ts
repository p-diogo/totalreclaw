/**
 * Mock Services for E2E Integration Tests
 *
 * Provides mock endpoints for:
 * - Pimlico bundler (JSON-RPC)
 * - Subgraph (GraphQL)
 * - Control plane (configure mock behavior, inspect requests)
 */

import http from "node:http";

// ============ Types ============

interface RequestLog {
  path: string;
  method: string;
  body: unknown;
  timestamp: string;
}

interface MockConfig {
  bundler: {
    error: boolean;
  };
  subgraph: {
    timeout: boolean;
    response: unknown | null;
  };
}

// ============ State ============

const requestLog: RequestLog[] = [];

let config: MockConfig = {
  bundler: { error: false },
  subgraph: { timeout: false, response: null },
};

function resetState(): void {
  requestLog.length = 0;
  config = {
    bundler: { error: false },
    subgraph: { timeout: false, response: null },
  };
}

// ============ Helpers ============

function readBody(req: http.IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf-8")));
    req.on("error", reject);
  });
}

function jsonResponse(
  res: http.ServerResponse,
  status: number,
  body: unknown
): void {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(payload),
  });
  res.end(payload);
}

function logRequest(path: string, method: string, body: unknown): void {
  requestLog.push({
    path,
    method,
    body,
    timestamp: new Date().toISOString(),
  });
}

// ============ Handlers ============

function handleHealth(
  _req: http.IncomingMessage,
  res: http.ServerResponse
): void {
  jsonResponse(res, 200, { status: "ok" });
}

function handleBundler(
  body: unknown,
  res: http.ServerResponse
): void {
  const rpc = body as { jsonrpc?: string; id?: number; method?: string; params?: unknown[] };
  const id = rpc.id ?? 1;

  if (config.bundler.error) {
    jsonResponse(res, 200, {
      jsonrpc: "2.0",
      id,
      error: { code: -32000, message: "Mock error" },
    });
    return;
  }

  switch (rpc.method) {
    case "eth_sendUserOperation": {
      const randomHex = Math.random().toString(16).slice(2, 18);
      jsonResponse(res, 200, {
        jsonrpc: "2.0",
        id,
        result: `0xfake_userop_hash_${randomHex}`,
      });
      break;
    }
    case "eth_estimateUserOperationGas":
      jsonResponse(res, 200, {
        jsonrpc: "2.0",
        id,
        result: {
          preVerificationGas: "0x1",
          verificationGasLimit: "0x1",
          callGasLimit: "0x1",
        },
      });
      break;
    case "pm_sponsorUserOperation":
      jsonResponse(res, 200, {
        jsonrpc: "2.0",
        id,
        result: { paymasterAndData: "0x00" },
      });
      break;
    case "eth_getUserOperationReceipt":
      jsonResponse(res, 200, {
        jsonrpc: "2.0",
        id,
        result: {
          userOpHash: "0xfake_receipt_hash",
          success: true,
          receipt: { transactionHash: "0xfake_tx_hash", blockNumber: "0x1" },
        },
      });
      break;
    default:
      jsonResponse(res, 200, {
        jsonrpc: "2.0",
        id,
        result: null,
      });
  }
}

function handleSubgraph(
  body: unknown,
  res: http.ServerResponse
): void {
  if (config.subgraph.timeout) {
    // Delay 30 seconds — the server should timeout before this resolves
    setTimeout(() => {
      jsonResponse(res, 200, { data: { facts: [] } });
    }, 30_000);
    return;
  }

  if (config.subgraph.response !== null) {
    jsonResponse(res, 200, config.subgraph.response);
    return;
  }

  // Default: empty facts
  jsonResponse(res, 200, { data: { facts: [] } });
}

function handleControlRequests(
  _req: http.IncomingMessage,
  res: http.ServerResponse
): void {
  jsonResponse(res, 200, requestLog);
}

function handleControlReset(
  _req: http.IncomingMessage,
  res: http.ServerResponse
): void {
  resetState();
  jsonResponse(res, 200, { status: "reset" });
}

function handleControlConfigure(
  body: unknown,
  res: http.ServerResponse
): void {
  const patch = body as Partial<MockConfig>;
  if (patch.bundler) {
    config.bundler = { ...config.bundler, ...patch.bundler };
  }
  if (patch.subgraph) {
    config.subgraph = { ...config.subgraph, ...patch.subgraph };
  }
  jsonResponse(res, 200, { status: "configured", config });
}

// ============ Router ============

async function handleRequest(
  req: http.IncomingMessage,
  res: http.ServerResponse
): Promise<void> {
  const url = new URL(req.url ?? "/", `http://${req.headers.host}`);
  const path = url.pathname;
  const method = req.method ?? "GET";

  try {
    // Health check
    if (path === "/health" && method === "GET") {
      handleHealth(req, res);
      return;
    }

    // Control plane
    if (path === "/control/requests" && method === "GET") {
      handleControlRequests(req, res);
      return;
    }
    if (path === "/control/reset" && method === "POST") {
      handleControlReset(req, res);
      return;
    }
    if (path === "/control/configure" && method === "POST") {
      const raw = await readBody(req);
      const body = raw ? JSON.parse(raw) : {};
      handleControlConfigure(body, res);
      return;
    }

    // Bundler (Pimlico JSON-RPC)
    if (path === "/bundler" && method === "POST") {
      const raw = await readBody(req);
      const body = raw ? JSON.parse(raw) : {};
      logRequest(path, method, body);
      handleBundler(body, res);
      return;
    }

    // Subgraph (GraphQL)
    if (path === "/subgraph" && method === "POST") {
      const raw = await readBody(req);
      const body = raw ? JSON.parse(raw) : {};
      logRequest(path, method, body);
      handleSubgraph(body, res);
      return;
    }

    // 404
    jsonResponse(res, 404, { error: "Not found", path });
  } catch (err) {
    console.error(`Error handling ${method} ${path}:`, err);
    jsonResponse(res, 500, { error: "Internal mock error" });
  }
}

// ============ Server ============

const PORT = parseInt(process.env.PORT ?? "9090", 10);

const server = http.createServer(handleRequest);

server.listen(PORT, "0.0.0.0", () => {
  console.log(`Mock services listening on port ${PORT}`);
});

// Graceful shutdown
process.on("SIGTERM", () => {
  console.log("SIGTERM received, shutting down...");
  server.close(() => process.exit(0));
});

process.on("SIGINT", () => {
  console.log("SIGINT received, shutting down...");
  server.close(() => process.exit(0));
});
