# NanoClaw Production Readiness Assessment

**Date:** 2026-02-23  
**Version:** v0.5 PoC  
**Status:** Pre-MVP

---

## Test Coverage Summary

### What's Tested

| Component | Test File | Coverage |
|-----------|-----------|----------|
| MCP Tools (remember/recall/forget/export/import) | `mcp/tests/server.test.js` | Full validation, namespace handling, merge strategies |
| Hook Lifecycle (beforeAgentStart/agentEnd/preCompact) | `skill-nanoclaw/tests/hooks.test.js` | Turn tracking, extraction, deduplication, error handling |
| Hook Integration | `skill/tests/integration/hooks-integration.test.ts` | Cross-hook flows, state management |
| Server Integration | `skill/tests/integration/server-integration.test.ts` | Auth, CRUD, concurrent ops, performance |
| E2E Flow | `skill/tests/integration/e2e-flow.test.ts` | Full conversation lifecycle |

### What's Mocked vs Real

| Component | Mocked | Real Server Required |
|-----------|--------|---------------------|
| OpenMemory Client | Yes (in-memory Map) | No |
| LLM Client | Yes (predefined responses) | No |
| Vector Store | Yes (random embeddings) | No |
| Reranker | Yes (sorted by input order) | No |
| HTTP Server | In-process mock | No |

**Estimated Unit Test Coverage:** ~75%  
**Estimated Integration Test Coverage:** ~40% (all mocked)

### Test Count by Type

- **Unit Tests:** ~150 tests
- **Integration Tests:** ~80 tests (all with mocks)
- **E2E Tests:** ~30 tests (skip if server unavailable)
- **Real Server Tests:** 0

---

## Known Gaps

### 1. Integration Tests (HIGH Priority)
**Status:** All tests use mocks, none require running OpenMemory server

**What's Missing:**
- Tests against actual PostgreSQL database
- Tests against actual encryption (AES-GCM)
- Tests with real vector embeddings
- Network latency simulation

**Fix Plan:**
1. Create `tests/integration/real-server/` directory
2. Add Docker Compose for test infrastructure
3. Implement `@openmemory/test-helpers` package
4. Add CI job with real server

**Effort:** 16-24 hours

---

### 2. LLM Client Interface (HIGH Priority)
**Status:** MockLLMClient returns predefined JSON, no actual LLM calls

**What's Missing:**
- OpenAI/Anthropic/Ollama client implementations
- Token counting and cost tracking
- Retry logic for rate limits
- Streaming response handling

**Fix Plan:**
1. Define `LLMClient` interface in `src/llm/types.ts`
2. Implement `OpenAIClient`, `AnthropicClient`, `OllamaClient`
3. Add `MockLLMClient` for testing
4. Document configuration options

**Effort:** 12-16 hours

---

### 3. CLAUDE.md Sync (MEDIUM Priority)
**Status:** `preCompact` has optional sync but no tests

**What's Missing:**
- File system operations
- Conflict resolution (manual edits vs auto-sync)
- Backup before overwrite
- Format preservation

**Fix Plan:**
1. Add `src/sync/claude-md-sync.ts`
2. Implement atomic write with backup
3. Add diff/merge for manual edits
4. Test with various CLAUDE.md formats

**Effort:** 8-12 hours

---

### 4. Credential Management (HIGH Priority)
**Status:** Master password stored in memory only

**What's Missing:**
- Secure credential storage (keychain/credential-helper)
- Password rotation workflow
- Session timeout and re-authentication
- Multi-device credential sync

**Fix Plan:**
1. Integrate with system keychain (node-keytar)
2. Add `openmemory auth rotate` command
3. Implement session management
4. Add secure export/import for migration

**Effort:** 16-20 hours

---

### 5. Namespace Migration (LOW Priority)
**Status:** No tool to migrate facts between namespaces

**What's Missing:**
- `openmemory namespace migrate` command
- Bulk fact re-tagging
- Preview before migration
- Undo capability

**Fix Plan:**
1. Add to MCP tools: `openmemory_migrate_namespace`
2. Implement batch update with transaction
3. Add `--dry-run` option
4. Track migration in metadata

**Effort:** 6-8 hours

---

### 6. Rollback Support (MEDIUM Priority)
**Status:** `import_id` is generated but `forget by import_id` not implemented

**What's Missing:**
```typescript
// Current import output includes:
interface ImportOutput {
  import_id: string; // e.g., "import-1735000000-abc123"
  // ...
}

// Missing implementation:
await client.forget({ import_id: "import-1735000000-abc123" });
```

**Fix Plan:**
1. Store `import_id` in fact metadata during import
2. Add `forgetByImportId` to client interface
3. Update MCP tool to accept `import_id` parameter
4. Add tests for rollback scenarios

**Effort:** 4-6 hours

---

## Production Use Cases

### 1. User stores a preference → agent recalls it next session
| Aspect | Status | Notes |
|--------|--------|-------|
| Storage | Works | `remember` tool functional |
| Retrieval | Works | `recall` with namespace filter |
| Persistence | Partial | Requires running server |
| Cross-session | Untested | No session management tests |

**Gap:** Session continuity not tested

---

### 2. User corrects information → old fact updated
| Aspect | Status | Notes |
|--------|--------|-------|
| Detection | Works | LLM can detect corrections |
| UPDATE action | Works | Forget + re-member |
| DELETE action | Works | `forget` by ID |
| History | Missing | No audit log |

**Gap:** No versioning or history

---

### 3. User switches between group folders → namespace isolation
| Aspect | Status | Notes |
|--------|--------|-------|
| Namespace tags | Works | `namespace:work` format |
| Filtering | Works | Client-side filter |
| Cross-namespace leak | Tested | Tests verify isolation |
| Migration | Missing | Can't move facts |

**Gap:** Namespace migration not implemented

---

### 4. User exports from OpenClaw → imports to NanoClaw
| Aspect | Status | Notes |
|--------|--------|-------|
| JSON export | Works | Full format support |
| Markdown export | Works | Parser implemented |
| Import validation | Works | `validate_only` option |
| Merge strategies | Works | skip/overwrite/merge |

**Gap:** No format versioning

---

### 5. User changes master password → credential rotation
| Aspect | Status | Notes |
|--------|--------|-------|
| Current storage | Memory only | Lost on restart |
| Rotation API | Missing | Not implemented |
| Re-encryption | Missing | Would need to re-encrypt all facts |

**Gap:** Entire credential lifecycle missing

---

### 6. System crash during import → rollback
| Aspect | Status | Notes |
|--------|--------|-------|
| Import ID generation | Works | Unique ID created |
| Tracking | Missing | ID not stored |
| Rollback API | Missing | No `forget by import_id` |
| Atomicity | Missing | No transaction support |

**Gap:** No crash recovery mechanism

---

### 7. Multiple devices syncing → conflict resolution
| Aspect | Status | Notes |
|--------|--------|-------|
| Single device | Works | In-memory sync |
| Multi-device | Missing | No sync protocol |
| Conflict detection | Missing | No vector clocks |
| Resolution | Missing | No merge strategy |

**Gap:** Entire multi-device sync missing

---

## Improvement Roadmap

### Must-Have Before MVP

| Item | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Real server integration tests | HIGH | 24h | Docker setup |
| LLM client implementations | HIGH | 16h | None |
| Credential storage | HIGH | 20h | keychain integration |
| Rollback support | MEDIUM | 6h | None |

**Total MVP Effort:** ~66 hours

---

### Nice-to-Have

| Item | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| CLAUDE.md sync | MEDIUM | 12h | None |
| Namespace migration | LOW | 8h | None |
| Import/export versioning | LOW | 4h | None |
| Audit logging | MEDIUM | 8h | Storage schema |

**Total Nice-to-Have Effort:** ~32 hours

---

### Future Enhancements

| Item | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Multi-device sync | LOW | 40h | Conflict resolution design |
| Fact versioning | LOW | 16h | Storage schema |
| Embedding model selection | LOW | 8h | Multiple model support |
| Performance benchmarking | LOW | 16h | Benchmark harness |

**Total Future Effort:** ~80 hours

---

## Recommendations

### Immediate Actions (Next Sprint)

1. **Add real server tests** - Critical for production confidence
2. **Implement LLM client interface** - Required for actual fact extraction
3. **Add credential storage** - Required for production use

### Before Production Release

1. Complete all "Must-Have" items
2. Add performance regression tests
3. Document deployment guide
4. Add health check endpoints

### Post-MVP

1. Collect user feedback on gaps
2. Prioritize "Nice-to-Have" based on usage
3. Plan multi-device sync architecture

---

## Appendix: Test File Summary

```
skill-nanoclaw/tests/hooks.test.js         772 lines  Unit tests (mocked)
mcp/tests/server.test.js                   682 lines  Unit tests (mocked)
skill/tests/integration/hooks-integration.test.ts  1332 lines  Integration (mocked)
skill/tests/integration/server-integration.test.ts  947 lines  Integration (mock server)
skill/tests/integration/e2e-flow.test.ts   1146 lines  E2E (skips if no server)
```

**Total test lines:** ~4,900 lines  
**Test commands:**
```bash
npm test                                    # Run all unit tests
npm run test:integration                    # Run integration tests (mocked)
npm run test:e2e -- --server-url=http://... # Run E2E with real server
```
