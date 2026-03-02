# v2 Real-World Data Testbed Progress

**Started:** 2026-02-20
**Status:** ✅ Phase 1 Complete | Phase 2 Ready

---

## Phase 1 Complete ✅

### Documents Created
- `docs/TotalReclaw Improvement Suggestions after benchmark.md`
- `docs/TotalReclaw-v0.6-Encrypted-BM25-Index-Specification.md`

### Data Processed
- **WhatsApp**: 9 chats → 8,248 messages → **1,162 memories**
- Output: `testbed/v2-realworld-data/processed/whatsapp_memories.json`

### Scripts Created
- `scripts/parse_whatsapp.py` - WhatsApp parser ✅
- `scripts/parse_telegram.py` - Telegram parser (ready)
- `scripts/parse_gmail.py` - Gmail parser (ready)
- `scripts/generate_embeddings.py` - Embedding generator
- `scripts/generate_ground_truth.py` - GT generator

### v0.6 Algorithm
- `testbed/totalreclaw_v06_eval.py` - Main evaluator
- `testbed/src/totalreclaw_v06/` - BM25, query expansion, search

---

## Phase 2: Next Tasks

| Task | Description |
|------|-------------|
| **#1** | Generate embeddings for 1,162 WhatsApp memories |
| **#2** | Generate ground truth (LLM-based) |
| **#3** | Run v0.6 benchmark |
| **#4** | Compare all algorithms |

### Comparison Targets
| Algorithm | BM25 Scope | E2EE |
|-----------|------------|------|
| BM25-Only | Full | ❌ |
| Vector-Only | None | ❌ |
| OpenClaw Hybrid | Full | ❌ |
| QMD Hybrid | Full | ❌ |
| v0.2 | Top 250 | ✅ |
| v0.5 | Top 250 | ✅ |
| **v0.6** | **Full** | ✅ |

---

## Key Paths

```
testbed/v2-realworld-data/
├── config/testbed_config.yaml
├── processed/whatsapp_memories.json  # 1,162 memories
├── scripts/
│   ├── generate_embeddings.py
│   └── generate_ground_truth.py
└── results/

testbed/
├── totalreclaw_v06_eval.py
└── src/totalreclaw_v06/
    ├── bm25_index.py
    ├── query_expansion.py
    └── search.py
```
