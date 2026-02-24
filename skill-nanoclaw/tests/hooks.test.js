/**
 * @jest-environment node
 */

jest.mock('@openmemory/client', () => ({
  OpenMemory: jest.fn(),
}));

function createMockClient(overrides = {}) {
  return {
    recall: jest.fn().mockResolvedValue([]),
    remember: jest.fn().mockResolvedValue('fact-id'),
    forget: jest.fn().mockResolvedValue(undefined),
    isReady: jest.fn().mockReturnValue(true),
    ...overrides,
  };
}

describe('beforeAgentStart', () => {
  it('should retrieve and format memories', async () => {
    const mockClient = createMockClient({
      recall: jest.fn().mockResolvedValue([
        {
          fact: {
            id: 'fact-1',
            text: 'User prefers TypeScript',
            embedding: [],
            metadata: { importance: 0.8, tags: ['namespace:main', 'preference'] },
            decayScore: 0.8,
            createdAt: new Date(),
          },
          score: 0.9,
          vectorScore: 0.85,
          textScore: 0.9,
          decayAdjustedScore: 0.8,
        },
      ]),
    });

    const { beforeAgentStart } = require('../dist/hooks/before-agent-start.js');
    const result = await beforeAgentStart(mockClient, {
      userMessage: 'What language should I use?',
      groupFolder: 'main',
    });

    expect(result.memories).toHaveLength(1);
    expect(result.memories[0].text).toBe('User prefers TypeScript');
    expect(result.contextString).toContain('## Relevant Memories');
  });

  it('should filter by namespace', async () => {
    const mockClient = createMockClient({
      recall: jest.fn().mockResolvedValue([
        {
          fact: {
            id: 'fact-1',
            text: 'Work memory',
            embedding: [],
            metadata: { importance: 0.8, tags: ['namespace:work'] },
            decayScore: 0.8,
            createdAt: new Date(),
          },
          score: 0.9,
          vectorScore: 0.9,
          textScore: 0.9,
          decayAdjustedScore: 0.8,
        },
        {
          fact: {
            id: 'fact-2',
            text: 'Main memory',
            embedding: [],
            metadata: { importance: 0.8, tags: ['namespace:main'] },
            decayScore: 0.8,
            createdAt: new Date(),
          },
          score: 0.85,
          vectorScore: 0.85,
          textScore: 0.85,
          decayAdjustedScore: 0.8,
        },
      ]),
    });

    const { beforeAgentStart } = require('../dist/hooks/before-agent-start.js');
    const result = await beforeAgentStart(mockClient, {
      userMessage: 'test',
      groupFolder: 'main',
    });

    expect(result.memories).toHaveLength(1);
    expect(result.memories[0].text).toBe('Main memory');
  });

  it('should handle errors gracefully', async () => {
    const mockClient = createMockClient({
      recall: jest.fn().mockRejectedValue(new Error('Network error')),
    });

    const { beforeAgentStart } = require('../dist/hooks/before-agent-start.js');
    const result = await beforeAgentStart(mockClient, {
      userMessage: 'test',
      groupFolder: 'main',
    });

    expect(result.memories).toEqual([]);
    expect(result.latencyMs).toBeGreaterThanOrEqual(0);
  });
});

describe('agentEnd', () => {
  it('should skip extraction when turn count not at interval', async () => {
    const mockClient = createMockClient();
    const mockLLMClient = { generate: jest.fn() };

    const { agentEnd } = require('../dist/hooks/agent-end.js');
    const result = await agentEnd(mockClient, mockLLMClient, {
      conversationHistory: [{ role: 'user', content: 'test' }],
      groupFolder: 'main',
      turnCount: 3,
    });

    expect(result.factsExtracted).toBe(0);
    expect(result.factsStored).toBe(0);
    expect(mockLLMClient.generate).not.toHaveBeenCalled();
  });

  it('should extract at interval', async () => {
    const mockClient = createMockClient();
    const mockLLMClient = {
      generate: jest.fn().mockResolvedValue(JSON.stringify({
        facts: [{
          factText: 'User likes TypeScript',
          type: 'preference',
          importance: 8,
          confidence: 0.9,
          action: 'ADD',
          entities: [],
          relations: [],
        }],
      })),
    };

    const { agentEnd } = require('../dist/hooks/agent-end.js');
    const result = await agentEnd(mockClient, mockLLMClient, {
      conversationHistory: [
        { role: 'user', content: 'I like TypeScript' },
        { role: 'assistant', content: 'Got it' },
        { role: 'user', content: 'Remember that' },
      ],
      groupFolder: 'main',
      turnCount: 5,
    });

    expect(result.factsExtracted).toBe(1);
    expect(result.factsStored).toBe(1);
    expect(mockClient.remember).toHaveBeenCalled();
  });
});

describe('preCompact', () => {
  it('should perform comprehensive extraction', async () => {
    const mockClient = createMockClient();
    const mockLLMClient = {
      generate: jest.fn().mockResolvedValue(JSON.stringify({
        facts: [
          {
            factText: 'User works on OpenMemory',
            type: 'fact',
            importance: 7,
            confidence: 0.9,
            action: 'ADD',
            entities: [],
            relations: [],
          },
          {
            factText: 'Old fact',
            type: 'fact',
            importance: 5,
            confidence: 0.9,
            action: 'DELETE',
            existingFactId: 'old-fact-id',
            entities: [],
            relations: [],
          },
        ],
      })),
    };

    const { preCompact } = require('../dist/hooks/pre-compact.js');
    const result = await preCompact(mockClient, mockLLMClient, {
      transcript: 'Long conversation...',
      groupFolder: 'main',
    });

    expect(result.factsExtracted).toBe(2);
    expect(result.factsStored).toBe(1);
  });

  it('should handle UPDATE action', async () => {
    const mockClient = createMockClient();
    const mockLLMClient = {
      generate: jest.fn().mockResolvedValue(JSON.stringify({
        facts: [{
          factText: 'Updated fact',
          type: 'fact',
          importance: 7,
          confidence: 0.9,
          action: 'UPDATE',
          existingFactId: 'old-fact-id',
          entities: [],
          relations: [],
        }],
      })),
    };

    const { preCompact } = require('../dist/hooks/pre-compact.js');
    const result = await preCompact(mockClient, mockLLMClient, {
      transcript: 'Conversation',
      groupFolder: 'main',
    });

    expect(mockClient.forget).toHaveBeenCalledWith('old-fact-id');
    expect(result.factsStored).toBe(1);
  });
});

describe('Extraction Prompts', () => {
  describe('validateExtractionResponse', () => {
    it('should validate correct response', () => {
      const { validateExtractionResponse } = require('../dist/extraction/prompts.js');
      const response = {
        facts: [{
          factText: 'Test fact',
          type: 'preference',
          importance: 7,
          confidence: 0.9,
          action: 'ADD',
          entities: [],
          relations: [],
        }],
      };

      const result = validateExtractionResponse(response);

      expect(result.valid).toBe(true);
      expect(result.facts).toHaveLength(1);
      expect(result.facts[0].factText).toBe('Test fact');
    });

    it('should reject invalid response', () => {
      const { validateExtractionResponse } = require('../dist/extraction/prompts.js');
      const response = {
        facts: [{
          factText: '',
          type: 'invalid',
          importance: 15,
          confidence: 2,
          action: 'INVALID',
        }],
      };

      const result = validateExtractionResponse(response);

      expect(result.valid).toBe(false);
      expect(result.errors.length).toBeGreaterThan(0);
    });

    it('should require facts array', () => {
      const { validateExtractionResponse } = require('../dist/extraction/prompts.js');
      const result = validateExtractionResponse({});

      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Response must have a "facts" array');
    });
  });

  describe('formatConversationHistory', () => {
    it('should format turns correctly', () => {
      const { formatConversationHistory } = require('../dist/extraction/prompts.js');
      const turns = [
        { role: 'user', content: 'Hello', timestamp: new Date('2024-01-01T10:00:00Z') },
        { role: 'assistant', content: 'Hi there', timestamp: new Date('2024-01-01T10:00:05Z') },
      ];

      const result = formatConversationHistory(turns);

      expect(result).toContain('[1] USER');
      expect(result).toContain('[2] ASSISTANT');
      expect(result).toContain('Hello');
      expect(result).toContain('Hi there');
    });
  });
});

describe('beforeAgentStart extended', () => {
  it('should handle default namespace correctly', async () => {
    const mockClient = createMockClient({
      recall: jest.fn().mockResolvedValue([
        {
          fact: {
            id: 'fact-1',
            text: 'Fact without explicit namespace',
            embedding: [],
            metadata: { importance: 0.8, tags: ['preference'] },
            decayScore: 0.8,
            createdAt: new Date(),
          },
          score: 0.9,
          vectorScore: 0.9,
          textScore: 0.9,
          decayAdjustedScore: 0.8,
        },
      ]),
    });

    const { beforeAgentStart } = require('../dist/hooks/before-agent-start.js');
    const result = await beforeAgentStart(mockClient, {
      userMessage: 'test',
      groupFolder: 'default',
    });

    expect(result.memories).toHaveLength(1);
  });

  it('should respect maxMemories limit', async () => {
    const mockClient = createMockClient({
      recall: jest.fn().mockResolvedValue(
        Array(15).fill(null).map((_, i) => ({
          fact: {
            id: `fact-${i}`,
            text: `Memory ${i}`,
            embedding: [],
            metadata: { tags: ['namespace:main'] },
            decayScore: 0.5,
            createdAt: new Date(),
          },
          score: 0.9,
          vectorScore: 0.9,
          textScore: 0.9,
          decayAdjustedScore: 0.5,
        }))
      ),
    });

    const { beforeAgentStart } = require('../dist/hooks/before-agent-start.js');
    const result = await beforeAgentStart(mockClient, {
      userMessage: 'test',
      groupFolder: 'main',
    }, 5);

    expect(mockClient.recall).toHaveBeenCalledWith('test', 5);
  });

  it('should include decay-adjusted info in context', async () => {
    const mockClient = createMockClient({
      recall: jest.fn().mockResolvedValue([
        {
          fact: {
            id: 'fact-1',
            text: 'High importance memory',
            embedding: [],
            metadata: { tags: ['namespace:main'], importance: 0.9 },
            decayScore: 0.95,
            createdAt: new Date(),
          },
          score: 0.9,
          vectorScore: 0.85,
          textScore: 0.92,
          decayAdjustedScore: 0.88,
        },
      ]),
    });

    const { beforeAgentStart } = require('../dist/hooks/before-agent-start.js');
    const result = await beforeAgentStart(mockClient, {
      userMessage: 'test',
      groupFolder: 'main',
    });

    expect(result.memories[0].score).toBe(0.9);
    expect(result.contextString).toContain('High importance memory');
  });

  it('should return undefined contextString when no memories', async () => {
    const mockClient = createMockClient({
      recall: jest.fn().mockResolvedValue([]),
    });

    const { beforeAgentStart } = require('../dist/hooks/before-agent-start.js');
    const result = await beforeAgentStart(mockClient, {
      userMessage: 'test',
      groupFolder: 'main',
    });

    expect(result.memories).toEqual([]);
    expect(result.contextString).toBeUndefined();
  });
});

describe('agentEnd extended', () => {
  it('should skip when llmClient is null', async () => {
    const mockClient = createMockClient();

    const { agentEnd } = require('../dist/hooks/agent-end.js');
    const result = await agentEnd(mockClient, null, {
      conversationHistory: [{ role: 'user', content: 'test' }],
      groupFolder: 'main',
      turnCount: 5,
    });

    expect(result.factsExtracted).toBe(0);
    expect(result.factsStored).toBe(0);
  });

  it('should store facts with correct namespace tags', async () => {
    const mockClient = createMockClient();
    const mockLLMClient = {
      generate: jest.fn().mockResolvedValue(JSON.stringify({
        facts: [{
          factText: 'User prefers VSCode',
          type: 'preference',
          importance: 8,
          confidence: 0.9,
          action: 'ADD',
          entities: [],
          relations: [],
        }],
      })),
    };

    const { agentEnd } = require('../dist/hooks/agent-end.js');
    await agentEnd(mockClient, mockLLMClient, {
      conversationHistory: [
        { role: 'user', content: 'I use VSCode' },
      ],
      groupFolder: 'work-project',
      turnCount: 5,
    });

    expect(mockClient.remember).toHaveBeenCalledWith(
      'User prefers VSCode',
      expect.objectContaining({
        tags: expect.arrayContaining(['namespace:work-project', 'preference']),
        importance: 0.8,
        source: 'agent_end_extraction',
      })
    );
  });

  it('should filter out low importance facts', async () => {
    const mockClient = createMockClient();
    const mockLLMClient = {
      generate: jest.fn().mockResolvedValue(JSON.stringify({
        facts: [
          {
            factText: 'Important fact',
            type: 'fact',
            importance: 8,
            confidence: 0.9,
            action: 'ADD',
            entities: [],
            relations: [],
          },
          {
            factText: 'Low importance note',
            type: 'fact',
            importance: 3,
            confidence: 0.9,
            action: 'ADD',
            entities: [],
            relations: [],
          },
        ],
      })),
    };

    const { agentEnd } = require('../dist/hooks/agent-end.js');
    const result = await agentEnd(mockClient, mockLLMClient, {
      conversationHistory: [{ role: 'user', content: 'test' }],
      groupFolder: 'main',
      turnCount: 5,
    });

    expect(result.factsExtracted).toBe(2);
    expect(result.factsStored).toBe(1);
  });

  it('should handle invalid JSON from LLM', async () => {
    const mockClient = createMockClient();
    const mockLLMClient = {
      generate: jest.fn().mockResolvedValue('not valid json'),
    };

    const { agentEnd } = require('../dist/hooks/agent-end.js');
    const result = await agentEnd(mockClient, mockLLMClient, {
      conversationHistory: [{ role: 'user', content: 'test' }],
      groupFolder: 'main',
      turnCount: 5,
    });

    expect(result.factsExtracted).toBe(0);
    expect(result.factsStored).toBe(0);
  });
});

describe('preCompact extended', () => {
  it('should handle DELETE action', async () => {
    const mockClient = createMockClient();
    const mockLLMClient = {
      generate: jest.fn().mockResolvedValue(JSON.stringify({
        facts: [{
          factText: 'Outdated info',
          type: 'fact',
          importance: 5,
          confidence: 0.9,
          action: 'DELETE',
          existingFactId: 'old-fact-123',
          entities: [],
          relations: [],
        }],
      })),
    };

    const { preCompact } = require('../dist/hooks/pre-compact.js');
    const result = await preCompact(mockClient, mockLLMClient, {
      transcript: 'Conversation',
      groupFolder: 'main',
    });

    expect(mockClient.forget).toHaveBeenCalledWith('old-fact-123');
    expect(result.factsStored).toBe(0);
  });

  it('should handle NOOP action', async () => {
    const mockClient = createMockClient();
    const mockLLMClient = {
      generate: jest.fn().mockResolvedValue(JSON.stringify({
        facts: [{
          factText: 'Already known',
          type: 'fact',
          importance: 5,
          confidence: 0.9,
          action: 'NOOP',
          entities: [],
          relations: [],
        }],
      })),
    };

    const { preCompact } = require('../dist/hooks/pre-compact.js');
    const result = await preCompact(mockClient, mockLLMClient, {
      transcript: 'Conversation',
      groupFolder: 'main',
    });

    expect(result.factsExtracted).toBe(1);
    expect(result.factsStored).toBe(0);
    expect(mockClient.remember).not.toHaveBeenCalled();
    expect(mockClient.forget).not.toHaveBeenCalled();
  });

  it('should skip when llmClient is null', async () => {
    const mockClient = createMockClient();

    const { preCompact } = require('../dist/hooks/pre-compact.js');
    const result = await preCompact(mockClient, null, {
      transcript: 'Conversation',
      groupFolder: 'main',
    });

    expect(result.factsExtracted).toBe(0);
    expect(result.factsStored).toBe(0);
    expect(result.claudeMdUpdated).toBe(false);
  });

  it('should handle invalid extraction response', async () => {
    const mockClient = createMockClient();
    const mockLLMClient = {
      generate: jest.fn().mockResolvedValue(JSON.stringify({
        facts: [{
          factText: '',
          type: 'invalid-type',
          importance: 15,
          confidence: 2,
          action: 'INVALID',
        }],
      })),
    };

    const { preCompact } = require('../dist/hooks/pre-compact.js');
    const result = await preCompact(mockClient, mockLLMClient, {
      transcript: 'Conversation',
      groupFolder: 'main',
    });

    expect(result.factsExtracted).toBe(0);
    expect(result.factsStored).toBe(0);
  });

  it('should use existing memories for context', async () => {
    const mockClient = createMockClient({
      recall: jest.fn().mockResolvedValue([
        {
          fact: {
            id: 'existing-1',
            text: 'User likes Python',
            embedding: [],
            metadata: { tags: ['namespace:main'] },
            decayScore: 0.5,
            createdAt: new Date(),
          },
          score: 1,
          vectorScore: 1,
          textScore: 1,
          decayAdjustedScore: 0.5,
        },
        {
          fact: {
            id: 'existing-2',
            text: 'Other namespace fact',
            embedding: [],
            metadata: { tags: ['namespace:other'] },
            decayScore: 0.5,
            createdAt: new Date(),
          },
          score: 1,
          vectorScore: 1,
          textScore: 1,
          decayAdjustedScore: 0.5,
        },
      ]),
    });
    const mockLLMClient = {
      generate: jest.fn().mockResolvedValue(JSON.stringify({
        facts: [],
      })),
    };

    const { preCompact } = require('../dist/hooks/pre-compact.js');
    await preCompact(mockClient, mockLLMClient, {
      transcript: 'Conversation',
      groupFolder: 'main',
    });

    const callArgs = mockLLMClient.generate.mock.calls[0];
    expect(callArgs[1]).toContain('[ID: existing-1]');
    expect(callArgs[1]).not.toContain('Other namespace fact');
  });
});

describe('Cross-Namespace Isolation', () => {
  it('should not leak memories across namespaces in beforeAgentStart', async () => {
    const mockClient = createMockClient({
      recall: jest.fn().mockResolvedValue([
        {
          fact: {
            id: 'fact-1',
            text: 'Personal secret',
            embedding: [],
            metadata: { tags: ['namespace:personal'] },
            decayScore: 0.8,
            createdAt: new Date(),
          },
          score: 0.95,
          vectorScore: 0.95,
          textScore: 0.95,
          decayAdjustedScore: 0.8,
        },
        {
          fact: {
            id: 'fact-2',
            text: 'Work info',
            embedding: [],
            metadata: { tags: ['namespace:work'] },
            decayScore: 0.8,
            createdAt: new Date(),
          },
          score: 0.9,
          vectorScore: 0.9,
          textScore: 0.9,
          decayAdjustedScore: 0.8,
        },
      ]),
    });

    const { beforeAgentStart } = require('../dist/hooks/before-agent-start.js');
    const result = await beforeAgentStart(mockClient, {
      userMessage: 'secret',
      groupFolder: 'work',
    });

    expect(result.memories).toHaveLength(1);
    expect(result.memories[0].text).toBe('Work info');
  });

  it('should store to correct namespace in agentEnd', async () => {
    const mockClient = createMockClient();
    const mockLLMClient = {
      generate: jest.fn().mockResolvedValue(JSON.stringify({
        facts: [{
          factText: 'Namespace-specific fact',
          type: 'fact',
          importance: 7,
          confidence: 0.9,
          action: 'ADD',
          entities: [],
          relations: [],
        }],
      })),
    };

    const { agentEnd } = require('../dist/hooks/agent-end.js');
    await agentEnd(mockClient, mockLLMClient, {
      conversationHistory: [{ role: 'user', content: 'test' }],
      groupFolder: 'project-alpha',
      turnCount: 5,
    });

    expect(mockClient.remember).toHaveBeenCalledWith(
      'Namespace-specific fact',
      expect.objectContaining({
        tags: expect.arrayContaining(['namespace:project-alpha']),
      })
    );
  });
});

describe('Decay Score Handling', () => {
  it('should include decayScore in memory format', async () => {
    const mockClient = createMockClient({
      recall: jest.fn().mockResolvedValue([
        {
          fact: {
            id: 'fact-1',
            text: 'Fresh memory',
            embedding: [],
            metadata: { tags: ['namespace:main'], importance: 0.8 },
            decayScore: 0.95,
            createdAt: new Date(),
          },
          score: 0.9,
          vectorScore: 0.9,
          textScore: 0.9,
          decayAdjustedScore: 0.85,
        },
        {
          fact: {
            id: 'fact-2',
            text: 'Decayed memory',
            embedding: [],
            metadata: { tags: ['namespace:main'], importance: 0.8 },
            decayScore: 0.3,
            createdAt: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000),
          },
          score: 0.9,
          vectorScore: 0.9,
          textScore: 0.9,
          decayAdjustedScore: 0.27,
        },
      ]),
    });

    const { beforeAgentStart } = require('../dist/hooks/before-agent-start.js');
    const result = await beforeAgentStart(mockClient, {
      userMessage: 'test',
      groupFolder: 'main',
    });

    expect(result.memories).toHaveLength(2);
  });
});
