import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  GetPromptRequestSchema,
  ListPromptsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';

import { OpenMemory } from '@openmemory/client';
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
import { SYSTEM_PROMPT_FRAGMENT } from './prompts.js';

const SERVER_URL = process.env.OPENMEMORY_SERVER_URL || 'http://127.0.0.1:8080';
const DEFAULT_NAMESPACE = process.env.OPENMEMORY_NAMESPACE || 'default';
const MASTER_PASSWORD = process.env.OPENMEMORY_MASTER_PASSWORD;

interface ClientState {
  client: OpenMemory | null;
  userId: string | null;
  salt: Buffer | null;
}

const clientState: ClientState = {
  client: null,
  userId: null,
  salt: null,
};

async function getClient(): Promise<OpenMemory> {
  if (clientState.client && clientState.client.isReady()) {
    return clientState.client;
  }

  const client = new OpenMemory({ serverUrl: SERVER_URL });
  await client.init();

  const credentialsPath = process.env.OPENMEMORY_CREDENTIALS_PATH || '/workspace/.openmemory/credentials.json';

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

const server = new Server(
  { name: 'openmemory', version: '1.0.0' },
  {
    capabilities: {
      tools: {},
      prompts: {},
    },
  }
);

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
      case 'openmemory_remember':
        return await handleRemember(client, args, DEFAULT_NAMESPACE);

      case 'openmemory_recall':
        return await handleRecall(client, args, DEFAULT_NAMESPACE);

      case 'openmemory_forget':
        return await handleForget(client, args, DEFAULT_NAMESPACE);

      case 'openmemory_export':
        return await handleExport(client, args, DEFAULT_NAMESPACE);

      case 'openmemory_import':
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

server.setRequestHandler(ListPromptsRequestSchema, async () => ({
  prompts: [{
    name: 'openmemory_instructions',
    description: 'Instructions for using OpenMemory tools',
  }],
}));

server.setRequestHandler(GetPromptRequestSchema, async (request) => {
  if (request.params.name === 'openmemory_instructions') {
    return {
      messages: [{
        role: 'assistant',
        content: { type: 'text', text: SYSTEM_PROMPT_FRAGMENT },
      }],
    };
  }
  throw new Error(`Unknown prompt: ${request.params.name}`);
});

async function main(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('OpenMemory MCP server started');
}

main().catch((error) => {
  console.error('Server error:', error);
  process.exit(1);
});
