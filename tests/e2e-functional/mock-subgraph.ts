/**
 * Mock Subgraph Server
 *
 * Provides two in-memory HTTP services for subgraph-mode E2E testing:
 *
 *   1. Mock Relay endpoint (POST /v1/relay)
 *      Accepts protobuf-encoded facts (as hex calldata), decodes them,
 *      stores them in memory, and returns a fake txHash.
 *
 *   2. Mock GraphQL endpoint (POST /)
 *      Responds to the same GraphQL queries the plugin issues:
 *        - SearchByBlindIndex / PaginateBlindIndex: match stored facts by blind index
 *        - FactCount / globalStates: return the current fact count
 *
 * This eliminates the need for a real Graph Node, Hardhat, or any on-chain
 * infrastructure during functional testing.
 *
 * Protobuf wire format matches skill/plugin/subgraph-store.ts encodeFactProtobuf():
 *   Field 1 (id):                  string  (wire type 2, length-delimited)
 *   Field 2 (timestamp):           string  (wire type 2)
 *   Field 3 (owner):               string  (wire type 2)
 *   Field 4 (encrypted_blob):      bytes   (wire type 2)
 *   Field 5 (blind_indices):       repeated string (wire type 2)
 *   Field 6 (decay_score):         double  (wire type 1, fixed 64-bit)
 *   Field 7 (is_active):           varint  (wire type 0)
 *   Field 8 (version):             varint  (wire type 0)
 *   Field 9 (source):              string  (wire type 2)
 *   Field 10 (content_fp):         string  (wire type 2)
 *   Field 11 (agent_id):           string  (wire type 2)
 *   Field 12 (sequence_id):        varint  (wire type 0)
 *   Field 13 (encrypted_embedding): string (wire type 2)
 */

import http from 'node:http';
import crypto from 'node:crypto';

// ---------------------------------------------------------------------------
// In-memory storage
// ---------------------------------------------------------------------------

interface SubgraphFact {
  id: string;
  timestamp: string;
  owner: string;
  encryptedBlob: string;   // hex-encoded
  blindIndices: string[];
  decayScore: number;
  isActive: boolean;
  version: number;
  source: string;
  contentFp: string;
  agentId: string;
  sequenceId: number;
  encryptedEmbedding: string | null;
}

/** All facts stored via the relay, keyed by fact id. */
const facts = new Map<string, SubgraphFact>();

/** Auto-incrementing sequence ID, mimicking the subgraph mapping. */
let nextSequenceId = 1;

// ---------------------------------------------------------------------------
// Protobuf decoder (minimal, matches encodeFactProtobuf wire format)
// ---------------------------------------------------------------------------

interface DecodedFact {
  id: string;
  timestamp: string;
  owner: string;
  encryptedBlob: Buffer;
  blindIndices: string[];
  decayScore: number;
  isActive: boolean;
  version: number;
  source: string;
  contentFp: string;
  agentId: string;
  encryptedEmbedding: string | null;
}

function decodeVarint(buf: Buffer, offset: number): { value: number; bytesRead: number } {
  let result = 0;
  let shift = 0;
  let bytesRead = 0;
  let byte: number;

  do {
    if (offset + bytesRead >= buf.length) {
      throw new Error('Varint overflows buffer');
    }
    byte = buf[offset + bytesRead];
    result |= (byte & 0x7f) << shift;
    shift += 7;
    bytesRead++;
  } while (byte & 0x80);

  return { value: result >>> 0, bytesRead };
}

function decodeProtobuf(buf: Buffer): DecodedFact {
  const result: DecodedFact = {
    id: '',
    timestamp: '',
    owner: '',
    encryptedBlob: Buffer.alloc(0),
    blindIndices: [],
    decayScore: 7.0,
    isActive: true,
    version: 1,
    source: '',
    contentFp: '',
    agentId: '',
    encryptedEmbedding: null,
  };

  let offset = 0;

  while (offset < buf.length) {
    const tag = decodeVarint(buf, offset);
    offset += tag.bytesRead;

    const fieldNumber = tag.value >>> 3;
    const wireType = tag.value & 0x07;

    if (wireType === 0) {
      // Varint
      const val = decodeVarint(buf, offset);
      offset += val.bytesRead;

      switch (fieldNumber) {
        case 7:
          result.isActive = val.value !== 0;
          break;
        case 8:
          result.version = val.value;
          break;
        case 12:
          // sequence_id — ignored (mock assigns its own)
          break;
      }
    } else if (wireType === 1) {
      // 64-bit (fixed64 / double)
      if (offset + 8 > buf.length) break;
      if (fieldNumber === 6) {
        result.decayScore = buf.readDoubleLE(offset);
      }
      offset += 8;
    } else if (wireType === 2) {
      // Length-delimited
      const len = decodeVarint(buf, offset);
      offset += len.bytesRead;
      const data = buf.subarray(offset, offset + len.value);
      offset += len.value;

      switch (fieldNumber) {
        case 1:
          result.id = data.toString('utf-8');
          break;
        case 2:
          result.timestamp = data.toString('utf-8');
          break;
        case 3:
          result.owner = data.toString('utf-8');
          break;
        case 4:
          result.encryptedBlob = Buffer.from(data);
          break;
        case 5:
          result.blindIndices.push(data.toString('utf-8'));
          break;
        case 9:
          result.source = data.toString('utf-8');
          break;
        case 10:
          result.contentFp = data.toString('utf-8');
          break;
        case 11:
          result.agentId = data.toString('utf-8');
          break;
        case 13:
          result.encryptedEmbedding = data.toString('utf-8');
          break;
      }
    } else if (wireType === 5) {
      // 32-bit (fixed32)
      offset += 4;
    } else {
      // Unknown wire type — skip is unsafe, break out
      break;
    }
  }

  return result;
}

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

async function readBody(req: http.IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) {
    chunks.push(chunk as Buffer);
  }
  return Buffer.concat(chunks).toString('utf8');
}

function jsonResponse(
  res: http.ServerResponse,
  status: number,
  body: unknown,
): void {
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
  });
  res.end(JSON.stringify(body));
}

// ---------------------------------------------------------------------------
// Relay handler
// ---------------------------------------------------------------------------

async function handleRelay(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const body = JSON.parse(await readBody(req));
  const { calldata } = body as { calldata: string };

  if (!calldata) {
    jsonResponse(res, 400, { success: false, error: 'Missing calldata' });
    return;
  }

  try {
    const protobufBuf = Buffer.from(calldata, 'hex');
    const decoded = decodeProtobuf(protobufBuf);

    // Dedup by content_fp (same logic as mock-server.ts)
    if (decoded.contentFp) {
      for (const existing of facts.values()) {
        if (existing.contentFp === decoded.contentFp && existing.isActive) {
          // Duplicate — return success but don't store
          const txHash = `0x${crypto.randomBytes(32).toString('hex')}`;
          jsonResponse(res, 200, { tx_hash: txHash, success: true });
          return;
        }
      }
    }

    const seqId = nextSequenceId++;
    const fact: SubgraphFact = {
      id: decoded.id || `fact-${crypto.randomUUID()}`,
      timestamp: decoded.timestamp || new Date().toISOString(),
      owner: decoded.owner || '0x0000000000000000000000000000000000000000',
      encryptedBlob: decoded.encryptedBlob.toString('hex'),
      blindIndices: decoded.blindIndices,
      decayScore: decoded.decayScore,
      isActive: decoded.isActive,
      version: decoded.version,
      source: decoded.source,
      contentFp: decoded.contentFp,
      agentId: decoded.agentId,
      sequenceId: seqId,
      encryptedEmbedding: decoded.encryptedEmbedding,
    };

    facts.set(fact.id, fact);

    const txHash = `0x${crypto.randomBytes(32).toString('hex')}`;
    jsonResponse(res, 200, { tx_hash: txHash, success: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    jsonResponse(res, 400, { success: false, error: `Protobuf decode failed: ${message}` });
  }
}

// ---------------------------------------------------------------------------
// GraphQL handler
// ---------------------------------------------------------------------------

/**
 * Handle GraphQL queries in the same format the plugin issues them.
 *
 * Supported queries:
 *   - SearchByBlindIndex / PaginateBlindIndex — match facts by blind index hash
 *   - FactCount / globalStates — return count of stored facts
 */
async function handleGraphQL(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const body = JSON.parse(await readBody(req));
  const { query, variables } = body as {
    query: string;
    variables?: Record<string, unknown>;
  };

  if (!query) {
    jsonResponse(res, 400, { errors: [{ message: 'Missing query' }] });
    return;
  }

  // -----------------------------------------------------------------------
  // FactCount / globalStates
  // -----------------------------------------------------------------------
  if (query.includes('globalStates') || query.includes('FactCount')) {
    const activeFacts = Array.from(facts.values()).filter((f) => f.isActive);
    jsonResponse(res, 200, {
      data: {
        globalStates: [
          {
            totalFacts: String(activeFacts.length),
          },
        ],
      },
    });
    return;
  }

  // -----------------------------------------------------------------------
  // SearchByBlindIndex / PaginateBlindIndex
  // -----------------------------------------------------------------------
  if (query.includes('blindIndexes')) {
    const trapdoors = (variables?.trapdoors as string[]) ?? [];
    const owner = (variables?.owner as string) ?? '';
    const first = (variables?.first as number) ?? 1000;
    const lastId = (variables?.lastId as string) ?? '';
    const trapdoorSet = new Set(trapdoors);

    // Collect all blind index entries that match any trapdoor.
    // Each blind index entry references the parent fact (same structure
    // the real subgraph returns).
    const entries: Array<{
      id: string;
      fact: {
        id: string;
        encryptedBlob: string;
        encryptedEmbedding: string | null;
        decayScore: string;
        timestamp: string;
        isActive: boolean;
        contentFp: string;
        sequenceId: string;
        version: string;
      };
    }> = [];

    for (const fact of facts.values()) {
      if (!fact.isActive) continue;
      // Owner filtering: if owner is provided and non-empty, match against fact.owner.
      // The subgraph stores owner as lowercase hex; be lenient here.
      if (owner && fact.owner && fact.owner.toLowerCase() !== owner.toLowerCase()) {
        continue;
      }

      for (const idx of fact.blindIndices) {
        if (trapdoorSet.has(idx)) {
          const entryId = `${fact.id}-${idx}`;

          // For PaginateBlindIndex with cursor: skip entries at or before lastId
          if (lastId && entryId <= lastId) continue;

          entries.push({
            id: entryId,
            fact: {
              id: fact.id,
              encryptedBlob: fact.encryptedBlob,
              encryptedEmbedding: fact.encryptedEmbedding,
              decayScore: String(fact.decayScore),
              timestamp: fact.timestamp,
              isActive: fact.isActive,
              contentFp: fact.contentFp,
              sequenceId: String(fact.sequenceId),
              version: String(fact.version),
            },
          });
        }
      }
    }

    // Sort by id descending (default for SearchByBlindIndex) unless
    // the query requests ascending (PaginateBlindIndex uses orderDirection: asc).
    const isAsc = query.includes('orderDirection: asc') || query.includes('PaginateBlindIndex');
    entries.sort((a, b) =>
      isAsc ? a.id.localeCompare(b.id) : b.id.localeCompare(a.id),
    );

    // Apply `first` limit
    const limited = entries.slice(0, first);

    jsonResponse(res, 200, {
      data: {
        blindIndexes: limited,
      },
    });
    return;
  }

  // -----------------------------------------------------------------------
  // Unrecognised query — return empty data
  // -----------------------------------------------------------------------
  jsonResponse(res, 200, { data: {} });
}

// ---------------------------------------------------------------------------
// Server lifecycle
// ---------------------------------------------------------------------------

export interface MockSubgraph {
  relayUrl: string;
  graphqlUrl: string;
  relayPort: number;
  graphqlPort: number;
  stop: () => Promise<void>;
  reset: () => void;
}

export async function startMockSubgraph(
  relayPort = 0,
  graphqlPort = 0,
): Promise<MockSubgraph> {
  // ---------------------------------------------------------------------------
  // Relay server
  // ---------------------------------------------------------------------------
  const relayServer = http.createServer(async (req, res) => {
    try {
      const url = req.url ?? '/';
      const method = req.method ?? 'GET';

      // Handle CORS preflight
      if (method === 'OPTIONS') {
        res.writeHead(204, {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
        });
        res.end();
        return;
      }

      if (method === 'GET' && url === '/health') {
        jsonResponse(res, 200, { status: 'ok' });
        return;
      }

      if (method === 'POST' && url === '/v1/relay') {
        await handleRelay(req, res);
        return;
      }

      jsonResponse(res, 404, { error: 'Not found' });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      jsonResponse(res, 500, { error: message });
    }
  });

  // ---------------------------------------------------------------------------
  // GraphQL server
  // ---------------------------------------------------------------------------
  const graphqlServer = http.createServer(async (req, res) => {
    try {
      const method = req.method ?? 'GET';

      // Handle CORS preflight
      if (method === 'OPTIONS') {
        res.writeHead(204, {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
        });
        res.end();
        return;
      }

      if (method === 'GET' && req.url === '/health') {
        jsonResponse(res, 200, { status: 'ok' });
        return;
      }

      if (method === 'POST') {
        await handleGraphQL(req, res);
        return;
      }

      jsonResponse(res, 404, { error: 'Not found' });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      jsonResponse(res, 500, { error: message });
    }
  });

  // ---------------------------------------------------------------------------
  // Start both servers
  // ---------------------------------------------------------------------------
  const startServer = (
    server: http.Server,
    port: number,
  ): Promise<{ port: number; url: string }> =>
    new Promise((resolve) => {
      server.listen(port, '127.0.0.1', () => {
        const addr = server.address() as { port: number };
        resolve({
          port: addr.port,
          url: `http://127.0.0.1:${addr.port}`,
        });
      });
    });

  const [relayAddr, graphqlAddr] = await Promise.all([
    startServer(relayServer, relayPort),
    startServer(graphqlServer, graphqlPort),
  ]);

  return {
    relayUrl: relayAddr.url,
    graphqlUrl: graphqlAddr.url,
    relayPort: relayAddr.port,
    graphqlPort: graphqlAddr.port,
    stop: async () => {
      await Promise.all([
        new Promise<void>((resolve) => relayServer.close(() => resolve())),
        new Promise<void>((resolve) => graphqlServer.close(() => resolve())),
      ]);
    },
    reset: () => {
      facts.clear();
      nextSequenceId = 1;
    },
  };
}
