import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  GetPromptRequestSchema,
  ListPromptsRequestSchema,
  ListResourcesRequestSchema,
  ReadResourceRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';

import { TotalReclaw } from '@totalreclaw/client';
import {
  rememberToolDefinition,
  recallToolDefinition,
  forgetToolDefinition,
  exportToolDefinition,
  importToolDefinition,
  handleRemember,
  handleRecall,
  handleForget,
  handleExport,
  handleImport,
} from './tools/index.js';
import { setOnRememberCallback } from './tools/remember.js';
import {
  SERVER_INSTRUCTIONS,
  PROMPT_DEFINITIONS,
  getPromptMessages,
} from './prompts.js';
import {
  memoryContextResource,
  readMemoryContext,
  invalidateMemoryContextCache,
} from './resources/index.js';

const SERVER_URL = process.env.TOTALRECLAW_SERVER_URL || 'http://127.0.0.1:8080';
const DEFAULT_NAMESPACE = process.env.TOTALRECLAW_NAMESPACE || 'default';
const MASTER_PASSWORD = process.env.TOTALRECLAW_MASTER_PASSWORD;

interface ClientState {
  client: TotalReclaw | null;
  userId: string | null;
  salt: Buffer | null;
}

const clientState: ClientState = {
  client: null,
  userId: null,
  salt: null,
};

async function getClient(): Promise<TotalReclaw> {
  if (clientState.client && clientState.client.isReady()) {
    return clientState.client;
  }

  const client = new TotalReclaw({ serverUrl: SERVER_URL });
  await client.init();

  const credentialsPath = process.env.TOTALRECLAW_CREDENTIALS_PATH || '/workspace/.totalreclaw/credentials.json';

  if (await credentialsExist(credentialsPath)) {
    const credentials = await loadCredentials(credentialsPath);
    await client.login(credentials.userId, MASTER_PASSWORD || 'default-password', credentials.salt);
    clientState.userId = credentials.userId;
    clientState.salt = credentials.salt;
  } else {
    const userId = await client.register(MASTER_PASSWORD || 'default-password');
    clientState.userId = userId;
    clientState.salt = client.getSalt();
    await saveCredentials(credentialsPath, {
      userId: clientState.userId!,
      salt: clientState.salt!,
    });
  }

  clientState.client = client;
  return client;
}

async function credentialsExist(path: string): Promise<boolean> {
  try {
    const fs = await import('fs/promises');
    await fs.access(path);
    return true;
  } catch {
    return false;
  }
}

interface StoredCredentials {
  userId: string;
  salt: string;
}

async function loadCredentials(path: string): Promise<{ userId: string; salt: Buffer }> {
  const fs = await import('fs/promises');
  const data = await fs.readFile(path, 'utf-8');
  const parsed = JSON.parse(data) as StoredCredentials;
  return {
    userId: parsed.userId,
    salt: Buffer.from(parsed.salt, 'base64'),
  };
}

async function saveCredentials(path: string, credentials: { userId: string; salt: Buffer }): Promise<void> {
  const fs = await import('fs/promises');
  const dir = path.substring(0, path.lastIndexOf('/'));
  await fs.mkdir(dir, { recursive: true }).catch(() => {});
  const data: StoredCredentials = {
    userId: credentials.userId,
    salt: credentials.salt.toString('base64'),
  };
  await fs.writeFile(path, JSON.stringify(data, null, 2), 'utf-8');
}

// ── Layer 1: Server with instructions ────────────────────────────────────────

const server = new Server(
  { name: 'totalreclaw', version: '1.0.0' },
  {
    capabilities: {
      tools: {},
      prompts: {},
      resources: { subscribe: true, listChanged: true },
    },
    instructions: SERVER_INSTRUCTIONS,
  }
);

// ── Wire up cache invalidation ───────────────────────────────────────────────
// When facts are stored, invalidate the memory context resource cache

setOnRememberCallback(() => {
  invalidateMemoryContextCache();
  // Notify subscribed clients that the resource has been updated
  server.sendResourceUpdated({ uri: memoryContextResource.uri }).catch(() => {});
});

// ── Layer 2 + 3: Tool handlers ───────────────────────────────────────────────

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    rememberToolDefinition,
    recallToolDefinition,
    forgetToolDefinition,
    exportToolDefinition,
    importToolDefinition,
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    const client = await getClient();

    switch (name) {
      case 'totalreclaw_remember': {
        const result = await handleRemember(client, args, DEFAULT_NAMESPACE);
        return result;
      }

      case 'totalreclaw_recall':
        return await handleRecall(client, args, DEFAULT_NAMESPACE);

      case 'totalreclaw_forget': {
        const result = await handleForget(client, args, DEFAULT_NAMESPACE);
        // Invalidate cache on forget too
        invalidateMemoryContextCache();
        server.sendResourceUpdated({ uri: memoryContextResource.uri }).catch(() => {});
        return result;
      }

      case 'totalreclaw_export':
        return await handleExport(client, args, DEFAULT_NAMESPACE);

      case 'totalreclaw_import':
        return await handleImport(client, args, DEFAULT_NAMESPACE);

      default:
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({ error: `Unknown tool: ${name}` }),
          }],
          isError: true,
        };
    }
  } catch (error) {
    return {
      content: [{
        type: 'text',
        text: JSON.stringify({
          error: error instanceof Error ? error.message : 'Unknown error',
        }),
      }],
      isError: true,
    };
  }
});

// ── Layer 4: Resources ───────────────────────────────────────────────────────

server.setRequestHandler(ListResourcesRequestSchema, async () => ({
  resources: [memoryContextResource],
}));

server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
  const { uri } = request.params;

  if (uri === memoryContextResource.uri) {
    const client = await getClient();
    const content = await readMemoryContext(client, DEFAULT_NAMESPACE);

    return {
      contents: [
        {
          uri: memoryContextResource.uri,
          mimeType: 'text/markdown',
          text: content,
        },
      ],
    };
  }

  throw new Error(`Unknown resource: ${uri}`);
});

// ── Layer 5: Prompts ─────────────────────────────────────────────────────────

server.setRequestHandler(ListPromptsRequestSchema, async () => ({
  prompts: [
    // Legacy instructions prompt (backward compat)
    {
      name: 'totalreclaw_instructions',
      description: 'Instructions for using TotalReclaw tools',
    },
    // New auto-memory prompt fallbacks
    ...PROMPT_DEFINITIONS,
  ],
}));

server.setRequestHandler(GetPromptRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  const messages = getPromptMessages(name, args as Record<string, string> | undefined);
  return { messages };
});

// ── Main ─────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('TotalReclaw MCP server started');
}

main().catch((error) => {
  console.error('Server error:', error);
  process.exit(1);
});
