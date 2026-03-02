/**
 * Client Reconnection Protocol Tests (v0.3.1b)
 *
 * Tests for the sync client that pulls delta from server
 * and reconciles local state.
 *
 * Spec: docs/specs/totalreclaw/server.md v0.3.1b section 8.2
 */
import {
  SyncClient,
  SyncState,
  reconcileLocalFacts,
  type SyncedFact,
  type LocalPendingFact,
} from '../src/api/sync';

// Mock HTTP fetch for sync endpoint
const mockFetch = jest.fn();

describe('Client Reconnection Protocol (v0.3.1b)', () => {
  let syncClient: SyncClient;

  beforeEach(() => {
    mockFetch.mockReset();
    syncClient = new SyncClient({
      serverUrl: 'http://localhost:8080',
      fetchImpl: mockFetch,
    });
  });

  describe('SyncClient.syncSince', () => {
    test('calls /sync with correct query params', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          facts: [],
          latest_sequence: 0,
          has_more: false,
        }),
      });

      await syncClient.syncSince(42, 'fake-auth-key');

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url, opts] = mockFetch.mock.calls[0];
      expect(url).toContain('/sync?since_sequence=42');
      expect(opts.headers['Authorization']).toBe('Bearer fake-auth-key');
    });

    test('returns facts and latest sequence', async () => {
      const serverFacts: SyncedFact[] = [
        {
          id: 'fact-1',
          sequence_id: 101,
          encrypted_blob: 'aabb',
          blind_indices: ['idx1'],
          decay_score: 1.0,
          is_active: true,
          version: 1,
          source: 'test',
          content_fp: 'fp-1',
          agent_id: 'agent-a',
        },
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          facts: serverFacts,
          latest_sequence: 101,
          has_more: false,
        }),
      });

      const result = await syncClient.syncSince(0, 'fake-auth-key');
      expect(result.facts).toHaveLength(1);
      expect(result.latestSequence).toBe(101);
      expect(result.hasMore).toBe(false);
    });

    test('throws on HTTP error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(syncClient.syncSince(0, 'key')).rejects.toThrow('Sync failed: HTTP 500');
    });

    test('throws on server error response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: false,
          error_message: 'DB down',
        }),
      });

      await expect(syncClient.syncSince(0, 'key')).rejects.toThrow('Sync failed: DB down');
    });
  });

  describe('SyncClient.syncAllSince', () => {
    test('paginates when has_more is true', async () => {
      // First page
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          facts: [{ id: 'f1', sequence_id: 1, content_fp: 'fp1' }],
          latest_sequence: 2,
          has_more: true,
        }),
      });
      // Second page
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          facts: [{ id: 'f2', sequence_id: 2, content_fp: 'fp2' }],
          latest_sequence: 2,
          has_more: false,
        }),
      });

      const result = await syncClient.syncAllSince(0, 'fake-auth-key');
      expect(result.facts).toHaveLength(2);
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });

    test('stops when empty page returned', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          facts: [],
          latest_sequence: 0,
          has_more: false,
        }),
      });

      const result = await syncClient.syncAllSince(0, 'fake-auth-key');
      expect(result.facts).toHaveLength(0);
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });
  });

  describe('reconcileLocalFacts', () => {
    test('skips local facts whose content_fp matches server', () => {
      const serverFacts: SyncedFact[] = [
        { id: 'server-1', content_fp: 'fp-aaa', sequence_id: 1 } as SyncedFact,
      ];
      const localFacts: LocalPendingFact[] = [
        { id: 'local-1', content_fp: 'fp-aaa', plaintext: 'same content' },
        { id: 'local-2', content_fp: 'fp-bbb', plaintext: 'new content' },
      ];

      const result = reconcileLocalFacts(serverFacts, localFacts);
      expect(result.skip).toHaveLength(1);
      expect(result.skip[0].id).toBe('local-1');
      expect(result.push).toHaveLength(1);
      expect(result.push[0].id).toBe('local-2');
    });

    test('pushes all local facts when server has none', () => {
      const result = reconcileLocalFacts([], [
        { id: 'local-1', content_fp: 'fp-1', plaintext: 'fact 1' },
        { id: 'local-2', content_fp: 'fp-2', plaintext: 'fact 2' },
      ]);
      expect(result.skip).toHaveLength(0);
      expect(result.push).toHaveLength(2);
    });

    test('skips all when all local facts match server', () => {
      const serverFacts: SyncedFact[] = [
        { id: 's-1', content_fp: 'fp-1', sequence_id: 1 } as SyncedFact,
        { id: 's-2', content_fp: 'fp-2', sequence_id: 2 } as SyncedFact,
      ];
      const localFacts: LocalPendingFact[] = [
        { id: 'l-1', content_fp: 'fp-1', plaintext: 'a' },
        { id: 'l-2', content_fp: 'fp-2', plaintext: 'b' },
      ];

      const result = reconcileLocalFacts(serverFacts, localFacts);
      expect(result.skip).toHaveLength(2);
      expect(result.push).toHaveLength(0);
    });

    test('handles local facts without content_fp (always push)', () => {
      const result = reconcileLocalFacts([], [
        { id: 'local-1', content_fp: undefined, plaintext: 'no fp' } as any,
      ]);
      expect(result.push).toHaveLength(1);
    });
  });

  describe('SyncState', () => {
    test('initializes with sequence 0', () => {
      const state = new SyncState();
      expect(state.lastSequence).toBe(0);
    });

    test('updates sequence after sync', () => {
      const state = new SyncState();
      state.update(42);
      expect(state.lastSequence).toBe(42);
    });

    test('serializes and deserializes', () => {
      const state = new SyncState();
      state.update(100);
      const json = state.toJSON();
      const restored = SyncState.fromJSON(json);
      expect(restored.lastSequence).toBe(100);
    });

    test('preserves lastSyncAt through serialization', () => {
      const state = new SyncState();
      state.update(50);
      expect(state.lastSyncAt).not.toBeNull();

      const json = state.toJSON();
      const restored = SyncState.fromJSON(json);
      expect(restored.lastSyncAt).not.toBeNull();
    });
  });
});
