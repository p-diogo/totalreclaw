# Account Abstraction (AA) Provider Comparison

**Date:** 2026-03-05
**Author:** Claude (automated research)
**Context:** TotalReclaw uses ERC-4337 UserOps to write encrypted facts on-chain. The current beta runs on Pimlico + Gnosis Chiado. This document evaluates all major AA providers to determine the optimal path for beta, growth, and scale.

---

## Table of Contents

1. [Provider Comparison Table](#1-provider-comparison-table)
2. [Coinbase CDP Deep Dive](#2-coinbase-cdp-deep-dive)
3. [Decision: Coinbase CDP for Beta](#3-decision-coinbase-cdp-for-beta)
4. [Migration Path: CDP to Self-Hosted Bundler](#4-migration-path-cdp-to-self-hosted-bundler)
5. [Recommendation & Timeline](#5-recommendation--timeline)

---

## 1. Provider Comparison Table

### Pricing Model Overview

There are two fundamental pricing models in the AA provider landscape:

| Model | How It Works | Implication |
|-------|-------------|-------------|
| **Gas pass-through + markup** | You pay actual gas cost + provider fee (5-10%) | Chain choice matters enormously (Base $0.005/op vs Gnosis $0.00076/op) |
| **Credit-based** | Fixed credit cost per API call, regardless of gas | Chain choice is irrelevant to provider billing; you still fund the paymaster |

### Provider Details

#### 1. Pimlico

| Attribute | Details |
|-----------|---------|
| **Pricing model** | Credit-based (10% surcharge on gas for paymaster, 10% for bundler; combined ~15.5% stacked) |
| **Free tier** | 1M credits/mo (~1,300 unsponsored ops or ~950 sponsored ops). Testnets only. |
| **Pay-as-you-go** | 10M credits/mo included, then $1 per 100K credits. ~13K unsponsored ops or ~9.5K sponsored ops included. |
| **Per-UserOp cost** | ~$0.0105/op on Gnosis (gas $0.00076 + 15.5% stacked surcharge + credit cost). ~$0.006/op on Base. |
| **Supported chains** | 25+ mainnets including Gnosis, Gnosis Chiado, Base, Ethereum, Arbitrum, Optimism, Polygon |
| **SDK** | `permissionless.js` -- excellent TypeScript SDK, first-class viem integration. Best DX in the market. |
| **Self-hosted bundler** | Alto (open-source, TypeScript, GPL-3.0). Well-documented self-hosting guide. |
| **Notes** | Currently integrated in TotalReclaw. Gnosis + Chiado support confirmed. ~100 free ops/day on free tier. |

#### 2. Coinbase CDP (OnchainKit / Paymaster)

| Attribute | Details |
|-----------|---------|
| **Pricing model** | Gas pass-through + 7% fee |
| **Free tier** | 0.25 ETH gas credits on activation. Up to $15K via Base Gasless Campaign (application required). |
| **Per-UserOp cost** | ~$0.00535/op on Base ($0.005 gas + 7% fee) |
| **Supported chains** | **Base Mainnet and Base Sepolia ONLY** |
| **SDK** | OnchainKit, Smart Wallet SDK. Good docs but less flexible than permissionless.js for custom account types. |
| **Self-hosted bundler** | Not applicable (managed service only). Coinbase's verifying-paymaster contract is open-source. |
| **Notes** | **Critical: Base-only.** No Gnosis support. $15K credits require application + demo + public launch within 3 months. Campaign eligibility requires integrating CDP tools. |

#### 3. ZeroDev

| Attribute | Details |
|-----------|---------|
| **Pricing model** | Credit-based (tiered plans) |
| **Plans** | Developer: $0/mo (50K testnet credits). Growth: $69/mo (100K credits, $250 gas sponsorship). Scale: $399/mo (1M credits, $1K gas sponsorship). Enterprise: custom. |
| **Per-UserOp cost** | Credit-to-UserOp ratio not publicly documented. At Growth tier, ~$0.069 per 100 credits amortized. |
| **Supported chains** | Most major EVM chains including Gnosis |
| **SDK** | Kernel SDK (proprietary smart account). UltraRelay for optimized gas sponsorship. Good DX. |
| **Notes** | Growth tier previously benchmarked at ~$0.60/op (extremely expensive vs Pimlico). Pricing has improved but still credit-based opacity. Not competitive for high-volume write-heavy workloads. |

#### 4. Alchemy (Account Kit / Rundler)

| Attribute | Details |
|-----------|---------|
| **Pricing model** | Gas pass-through + 8% admin fee. Compute-unit (CU) based API pricing. |
| **Free tier** | $100/mo gas sponsorship on Pay-as-you-go. |
| **Per-UserOp cost** | ~$0.0054/op on Base ($0.005 gas + 8%). On Gnosis: **not supported**. |
| **Supported chains** | Ethereum, Base, Arbitrum, Optimism, Polygon. **Does NOT support Gnosis Chain for AA.** |
| **SDK** | Account Kit -- comprehensive but opinionated (requires Alchemy accounts). |
| **Self-hosted bundler** | Rundler (open-source, Rust, LGPL-3.0). Horizontally scalable, modular architecture. |
| **Notes** | Strong infrastructure but no Gnosis support rules it out for current architecture. Rundler is an excellent self-hosted option regardless of provider choice. |

#### 5. Biconomy (Nexus)

| Attribute | Details |
|-----------|---------|
| **Pricing model** | Gas pass-through (fee structure not publicly documented). SDK is free. |
| **Free tier** | SDK free to use. Gas sponsorship requires deposit to "gas tank." |
| **Per-UserOp cost** | Not publicly documented. Revenue-sharing model for high-volume apps. |
| **Supported chains** | 50+ EVM chains including Gnosis, Base, Ethereum, Arbitrum, Polygon |
| **SDK** | AbstractJS SDK -- free, well-documented. Nexus modular smart account. |
| **Notes** | Broad chain support. Pricing opacity is a concern for cost planning. Dashboard-based configuration. Good for consumer apps, less ideal for infrastructure-grade use. |

#### 6. Stackup

| Attribute | Details |
|-----------|---------|
| **Pricing model** | N/A -- **Service discontinued** |
| **Status** | Shut down bundler/paymaster services in October 2024. Repository archived. |
| **Migration** | Stackup recommends migrating to Etherspot (3 months free Developer Plan). |
| **Self-hosted bundler** | stackup-bundler (Go, open-source) still available but unmaintained. |
| **Notes** | **Do not use.** Included for completeness. The Go bundler codebase could theoretically be forked but is no longer maintained. |

#### 7. Thirdweb

| Attribute | Details |
|-----------|---------|
| **Pricing model** | Gas pass-through + 10% premium on paymaster. Bundler (non-sponsored) is free. |
| **Free tier** | Metered billing (pay at end of month). No upfront gas sponsorship credits documented. |
| **Per-UserOp cost** | ~$0.0055/op on Base (gas + 10%). ~$0.00084/op on Gnosis (gas + 10%). |
| **Supported chains** | Broad EVM support. zkSync and EIP-7702 supported. |
| **SDK** | thirdweb SDK v5 -- comprehensive, well-documented. |
| **Notes** | 10% premium is higher than Pimlico's effective rate on low-gas chains. Enterprise plan available with 99.9% SLA. Good generalist platform but premium pricing for AA specifically. |

#### 8. Safe (4337 Module)

| Attribute | Details |
|-----------|---------|
| **Pricing model** | Safe4337Module is free (smart contract). You bring your own bundler + paymaster. |
| **Free tier** | Module deployment + usage is free. Gas costs depend on chosen bundler/paymaster. |
| **Per-UserOp cost** | Depends entirely on chosen bundler. Module itself adds ~30-50K gas overhead vs SimpleAccount. |
| **Supported chains** | All EVM chains where Safe is deployed (most major chains including Gnosis) |
| **SDK** | Safe{Core} SDK, Protocol Kit, Relay Kit. Mature but complex integration. |
| **Notes** | Not a bundler/paymaster provider. It is a smart account standard. More gas-expensive than SimpleAccount due to modular proxy architecture. Best for multi-sig or governance use cases, overkill for TotalReclaw's single-owner accounts. |

#### 9. Etherspot (Skandha + Arka)

| Attribute | Details |
|-----------|---------|
| **Pricing model** | Credit-based. No gas markup on pay-as-you-go tier. |
| **Plans** | Testnet: free (1M credits, 5 req/s). Pay-as-you-go: $1 per 250K credits (40 req/s). Enterprise: custom. |
| **Per-UserOp cost** | Gas cost only (no markup) + credit cost for API calls. On Gnosis: ~$0.0008-0.001/op. |
| **Supported chains** | All mainnets on paid plans. |
| **SDK** | Etherspot Prime SDK. Modular. |
| **Self-hosted bundler** | Skandha (open-source, TypeScript). Arka paymaster (open-source). |
| **Notes** | Both bundler AND paymaster are open-source. Interesting for self-hosted path. No gas markup is compelling. $10 minimum top-up. Good Gnosis support. |

#### 10. Particle Network

| Attribute | Details |
|-----------|---------|
| **Pricing model** | Gas pass-through. Deposit USDT to sponsor mainnet transactions. |
| **Free tier** | Free on testnets. Mainnet requires USDT deposit. No published fee schedule. |
| **Per-UserOp cost** | Not publicly documented. Presumably gas cost + operational overhead. |
| **Supported chains** | Broad EVM support ("practically all mainstream public chains"). |
| **SDK** | Particle AA SDK. Omnichain paymaster (deposit once, sponsor across chains). |
| **Notes** | Chain abstraction focus (Universal Accounts). The omnichain paymaster is interesting but adds complexity. Pricing opacity is a problem. Not ideal for infrastructure-grade cost planning. |

#### 11. Candide (Voltaire)

| Attribute | Details |
|-----------|---------|
| **Pricing model** | API request-based. Gas surcharge currently waived (0%) across all plans. |
| **Plans** | Starter: 50K requests (free). Launch: higher volume (contact sales). |
| **Per-UserOp cost** | Currently: gas cost only (0% surcharge). Future: tiered surcharges (advance notice promised). |
| **Supported chains** | Multiple EVM chains. Safe account integration. |
| **SDK** | AbstractionKit. Voltaire bundler. |
| **Self-hosted bundler** | Voltaire (open-source, Python + Rust). |
| **Notes** | The 0% surcharge promotion is temporary. Good Safe integration. Python bundler is unique (easier to hack on for Python-heavy teams). Smaller team/community than Pimlico. |

#### 12. Self-Hosted Bundler (Alto / Rundler / Silius / Skandha / Voltaire)

| Attribute | Details |
|-----------|---------|
| **Pricing model** | Infrastructure cost only. Zero provider fees. |
| **Per-UserOp cost** | Raw gas cost only. On Gnosis: ~$0.00076/op. On Base: ~$0.005/op. |
| **Infrastructure** | VPS ($10-40/mo), RPC endpoint (free tier or $20-50/mo), domain + SSL ($0). |
| **Monthly fixed cost** | ~$20-60/mo for a minimal single-node setup. |
| **Options** | Alto (TypeScript, Pimlico), Rundler (Rust, Alchemy), Silius (Rust), Skandha (TypeScript, Etherspot), Voltaire (Python, Candide) |
| **Notes** | Best cost at scale. Requires DevOps competence. Must also deploy a VerifyingPaymaster contract + signing service. See Section 4 for detailed analysis. |

#### Bonus: Circle Paymaster

| Attribute | Details |
|-----------|---------|
| **Pricing model** | 10% gas surcharge (fee waived until June 30, 2025 -- likely expired). USDC-denominated. |
| **Supported chains** | Arbitrum, Avalanche, Base, Ethereum, OP Mainnet, Polygon, Unichain. **No Gnosis.** |
| **Notes** | Interesting for USDC-native applications. Not relevant for TotalReclaw since we use paymaster sponsorship (users don't pay gas). |

### Summary Comparison Table

| Provider | Per-Op (Base) | Per-Op (Gnosis) | Free Tier | Gnosis Support | Self-Host Option |
|----------|--------------|----------------|-----------|---------------|-----------------|
| **Coinbase CDP** | $0.00535 | N/A | $15K credits | No | No |
| **Pimlico** | ~$0.006 | ~$0.0105 | ~950 ops/mo | Yes | Alto (TS) |
| **Etherspot** | ~$0.005 | ~$0.0008 | 1M credits | Yes | Skandha + Arka |
| **Thirdweb** | ~$0.0055 | ~$0.0008 | Metered | Yes | No |
| **Alchemy** | ~$0.0054 | N/A | $100/mo gas | No | Rundler (Rust) |
| **Biconomy** | Undisclosed | Undisclosed | SDK free | Yes | No |
| **ZeroDev** | ~$0.069? | ~$0.069? | 50K test credits | Yes | No |
| **Candide** | Gas only* | Gas only* | 50K requests | Likely | Voltaire (Py) |
| **Particle** | Undisclosed | Undisclosed | Free testnet | Yes | No |
| **Safe** | N/A (BYOB) | N/A (BYOB) | Free module | Yes | N/A |
| **Stackup** | Discontinued | Discontinued | N/A | N/A | Archived Go |
| **Self-hosted** | $0.005 | $0.00076 | N/A | Yes | Yes |

*Candide's 0% surcharge is temporary.

---

## 2. Coinbase CDP Deep Dive

### 2.1 Credit Structure

Coinbase CDP offers two tiers of credits:

| Credit Type | Amount | How to Get |
|------------|--------|------------|
| **Automatic** | 0.25 ETH (~$500 at $2,000/ETH) | Activate Paymaster on any CDP project |
| **Base Gasless Campaign** | Up to $15,000 | Application required (Google Form). Must have a functioning app, plan to launch publicly within 3 months, and integrate CDP tools. |
| **Demo bonus** | $1,000 | Create a demo of Base Account integration, post on Base App + X, tag @base and @CoinbaseDev |

**Total potential credits: $16,000** (0.25 ETH + $15K campaign + $1K demo bonus).

### 2.2 Credit Burn Rate

Using TotalReclaw's workload model: power users generate ~28 facts/day = ~840 facts/month per user.

| Scale | Monthly UserOps | Monthly Cost (Base, $0.00535/op) | Months $15K Lasts |
|-------|----------------|----------------------------------|-------------------|
| 10 users | 8,400 | $45 | **333 months** (27+ years) |
| 100 users | 84,000 | $449 | **33 months** (2.8 years) |
| 500 users | 420,000 | $2,247 | **6.7 months** |
| 1,000 users | 840,000 | $4,494 | **3.3 months** |
| 10,000 users | 8,400,000 | $44,940 | **10 days** |

**Key insight:** At beta scale (10-100 users), $15K credits last 2.8-27+ years. This is essentially "free" for the entire beta period and well into growth.

### 2.3 What Happens When Credits Run Out?

When credits are exhausted:
- Sponsored transactions will **fail** unless you have a payment method on file.
- CDP bills via monthly invoicing to your Coinbase account.
- You pay actual gas + 7% fee (same rate as during credits).
- No automatic cutoff -- transactions continue and you receive a bill.

### 2.4 Gnosis Chain Restriction -- CRITICAL

**Coinbase CDP Paymaster supports Base Mainnet and Base Sepolia ONLY.**

This means:
- Our current Chiado testnet deployment (Gnosis) is **incompatible** with CDP.
- We would need to deploy EventfulDataEdge on Base (or Base Sepolia for testnet).
- Our subgraph would need to be redeployed on Base.
- Our Graph Node / Graph Studio setup would need to target Base.

### 2.5 Can We Deploy on Base Instead?

**Yes.** Base is fully supported by both Graph Node and Graph Studio (it is the #1 chain on The Graph by query volume as of Q4 2025).

Trade-offs of Base vs Gnosis:

| Dimension | Base | Gnosis |
|-----------|------|--------|
| **Gas cost per UserOp** | ~$0.005 (variable, L1 data fee) | ~$0.00076 (stable, xDAI) |
| **Gas stability** | Variable (spikes during L1 congestion) | Stable (xDAI stablecoin) |
| **Graph Studio support** | Tier 1 (1.23B queries/quarter in Q4 2025) | Supported but smaller ecosystem |
| **Coinbase CDP** | Full support | Not supported |
| **Self-hosted bundler** | Supported by all bundlers | Supported by Pimlico, Etherspot |
| **Ecosystem** | Massive (Coinbase ecosystem) | Smaller but loyal (DAO-focused) |
| **ERC-4337 infra** | Excellent (all providers) | Good (Pimlico, Etherspot, Thirdweb) |
| **Decentralization** | Centralized sequencer (Coinbase) | Decentralized validators |
| **Native token for gas** | ETH (volatile) | xDAI (stable, $1 peg) |

**Assessment:** For a beta, Base is the pragmatic choice if we want CDP credits. The 6.5x higher gas cost per UserOp ($0.005 vs $0.00076) is irrelevant when credits cover it. At scale, we would need to re-evaluate.

---

## 3. Decision: Coinbase CDP for Beta

### Rationale

1. **$15K credits = 2.8 million sponsored UserOps on Base.** At 100 beta users, this lasts 33 months -- effectively the entire beta and early growth phase.

2. **Lower effective cost per op than Pimlico.** CDP charges $0.00535/op (gas + 7%) on Base vs Pimlico's ~$0.0105/op (credit cost + 15.5% gas surcharge) on Gnosis. Even though Gnosis gas is cheaper, Pimlico's credit overhead makes it 2x more expensive per op.

3. **Base is the largest subgraph ecosystem.** Moving to Base puts us in the #1 Graph Network ecosystem by query volume, which means better indexer availability and lower query costs.

4. **Application is straightforward.** TotalReclaw meets the campaign criteria: functioning app (PoC deployed), public launch planned within 3 months, integrating CDP Paymaster.

5. **No upfront cost during validation.** The entire beta validation period is free. We can validate product-market fit before spending anything on infrastructure.

### Prerequisites for CDP Migration

| Step | Effort | Description |
|------|--------|-------------|
| Deploy EventfulDataEdge on Base Sepolia | Low | Same Solidity contract, different chain |
| Deploy EventfulDataEdge on Base Mainnet | Low | Same contract, mainnet deployment |
| Update subgraph.yaml `network: base` | Low | Change network, address, startBlock |
| Deploy subgraph to Graph Studio (Base) | Low | `graph deploy --network base` |
| Update client `resolveChain()` | Low | Add Base chain ID (8453) and Base Sepolia (84532) |
| Apply for CDP credits | Low | Google Form application + demo |
| Integrate CDP paymaster SDK | Medium | Replace `createPimlicoClient` with CDP paymaster in `builder.ts` |
| Update relay proxy to forward to CDP | Medium | Change bundler endpoint from Pimlico to CDP |
| Update server config for Base chain IDs | Low | `pimlico_chain_id` -> `chain_id`, new env vars |

**Total estimated effort: 2-3 days of development.**

### What if CDP Application is Rejected?

Fallback plan: continue with Pimlico on Gnosis Chiado (current setup). Pimlico's free tier (~100 ops/day) is sufficient for a small beta. The Pimlico integration is already complete and tested.

---

## 4. Migration Path: CDP to Self-Hosted Bundler

This is the most critical section. The migration from a managed provider to self-hosted infrastructure involves several scenarios with very different complexity levels.

### 4.1 The Two-Subgraph Problem

If TotalReclaw starts on Base (with Coinbase CDP) and later moves to a cheaper chain (e.g., Gnosis) with a self-hosted bundler, we face a fundamental data continuity challenge:

```
Phase 1 (Beta):
  Base Chain -> EventfulDataEdge (Base) -> Subgraph (Base)
  All facts are on Base.

Phase 2 (Migration to Gnosis):
  Gnosis Chain -> EventfulDataEdge (Gnosis) -> Subgraph (Gnosis)
  New facts are on Gnosis. OLD facts are still on Base.

Agent Search Query:
  Must query BOTH subgraphs to get complete memory.
  Results must be merged, deduplicated (same contentFp), and ranked.
```

**This is a real problem.** On-chain data is immutable and cannot be migrated between chains. Facts written on Base stay on Base forever.

### 4.2 Migration Scenarios

#### Scenario A: Stay on Base, Swap Bundler Only

**The simplest and recommended migration path.**

```
Phase 1: Coinbase CDP Bundler + Base
Phase 2: Self-hosted Alto Bundler + Base (same chain!)
```

| Dimension | Analysis |
|-----------|----------|
| **User impact** | Zero. Users notice nothing. Same chain, same subgraph, same addresses. |
| **Agent impact** | Zero code changes. The relay proxy URL stays the same; only the server-side forwarding target changes from CDP to self-hosted Alto. |
| **Data continuity** | Perfect. Same chain = same subgraph = all facts in one place. |
| **Cost** | Gas: still ~$0.005/op (Base gas). Infra: ~$30-60/mo for Alto VPS. No provider markup. Total: $0.005/op + $30-60/mo fixed. |
| **Operational complexity** | Medium. Must run and monitor Alto bundler + VerifyingPaymaster signing service. |

**Code changes required (server-side only):**

```python
# proxy.py -- Change forwarding target
# Before (CDP):
target_url = "https://api.developer.coinbase.com/rpc/v1/base/{api_key}"

# After (self-hosted Alto):
target_url = "http://alto-bundler.internal:4337/rpc"
```

The client code (`builder.ts`) does NOT change because it talks to the relay proxy (`/v1/bundler`), not directly to any bundler.

**This is the beauty of the relay proxy architecture.** The bundler backend is an implementation detail hidden behind the relay.

#### Scenario B: Move from Base to Gnosis (Chain Migration)

**The hard path. Requires running dual subgraphs.**

```
Phase 1: CDP Bundler + Base
Phase 2: Self-hosted Alto + Gnosis (new facts)
         + Read-only subgraph on Base (old facts)
```

| Dimension | Analysis |
|-----------|----------|
| **User impact** | Moderate. Users may need to "re-register" if Smart Account addresses differ across chains (they don't -- CREATE2 is chain-agnostic with same factory). Existing seed phrases continue to work. |
| **Agent impact** | Significant. The search flow must fan out to TWO subgraph endpoints, merge results, and deduplicate by `contentFp`. |
| **Data continuity** | Maintained but complex. Old memories are on Base (read-only subgraph). New memories are on Gnosis. Agent sees unified view after client-side merge. |
| **Cost** | Much lower per-op: $0.00076/op on Gnosis vs $0.005/op on Base. But must maintain two subgraph endpoints. |
| **Operational complexity** | High. Two subgraphs, two chains to monitor, merge logic in client, dual RPC endpoints. |

**Client-side changes required:**

```typescript
// subgraph-search.ts -- Fan out to both subgraphs
async function searchFacts(trapdoors: string[]): Promise<Fact[]> {
  const [baseFacts, gnosisFacts] = await Promise.all([
    querySubgraph(BASE_SUBGRAPH_URL, trapdoors),
    querySubgraph(GNOSIS_SUBGRAPH_URL, trapdoors),
  ]);

  // Deduplicate by contentFp (same fact may exist on both chains
  // if there was an overlap period)
  const seen = new Set<string>();
  const merged: Fact[] = [];
  for (const fact of [...gnosisFacts, ...baseFacts]) {
    if (!seen.has(fact.contentFp)) {
      seen.add(fact.contentFp);
      merged.push(fact);
    }
  }

  return merged;
}
```

**Server-side proxy changes:**

```python
# proxy.py -- Route writes to Gnosis, reads fan out
@router.post("/subgraph")
async def proxy_subgraph(request: Request, ...):
    # Fan out to both subgraphs
    body = await request.body()
    async with httpx.AsyncClient(timeout=30.0) as client:
        base_resp, gnosis_resp = await asyncio.gather(
            client.post(settings.base_subgraph_endpoint, content=body, ...),
            client.post(settings.gnosis_subgraph_endpoint, content=body, ...),
            return_exceptions=True,
        )
    # Merge results server-side (preferred over client-side)
    return merge_subgraph_responses(base_resp, gnosis_resp)
```

#### Scenario C: Hybrid -- Self-Hosted Bundler on Base

**A middle ground: keep everything on Base, but replace CDP with a self-hosted bundler.**

This is identical to Scenario A but explicitly acknowledges that Base gas ($0.005/op) is higher than Gnosis ($0.00076/op). The trade-off is simplicity vs cost.

| Dimension | Analysis |
|-----------|----------|
| **User impact** | Zero. |
| **Agent impact** | Zero. |
| **Data continuity** | Perfect. |
| **Cost** | $0.005/op (Base gas, no markup) + ~$40/mo infra. At 1K users: ~$4,200/mo. |
| **vs Gnosis self-hosted** | 6.5x more expensive per op. At 1K users: $4,200/mo vs $638/mo. |
| **Break-even** | The $3,562/mo savings from Gnosis would justify the dual-subgraph complexity at ~500+ users. |

### 4.3 Self-Hosted Bundler Deep Dive

#### Open-Source Bundler Comparison

| Bundler | Language | Maintainer | License | EntryPoint v0.7 | P2P Mempool | Production Readiness |
|---------|----------|-----------|---------|-----------------|-------------|---------------------|
| **Alto** | TypeScript | Pimlico | GPL-3.0 | Yes | Yes | High (Pimlico dogfoods it) |
| **Rundler** | Rust | Alchemy | LGPL-3.0 | Yes | In development | High (Alchemy dogfoods it) |
| **Skandha** | TypeScript | Etherspot | MIT | Yes | Yes (EP6) | Medium-High |
| **Silius** | Rust | Independent | MIT/Apache | Yes | In development | Medium (smaller community) |
| **Voltaire** | Python/Rust | Candide | GPL-3.0 | Yes | Yes | Medium |

**Recommendation: Alto (Pimlico)**

Rationale:
- TypeScript aligns with TotalReclaw's client stack.
- Pimlico uses Alto in production -- it is battle-tested.
- Best documentation for self-hosting.
- `permissionless.js` SDK works identically against Alto as against Pimlico's hosted service.
- The migration from hosted Pimlico to self-hosted Alto is literally changing one URL.

#### Infrastructure Requirements

```
Self-hosted Alto Bundler (minimal setup):
+-------------------------------------------+
| VPS: 2 vCPU, 4GB RAM, 40GB SSD           |
| OS: Ubuntu 22.04 / Debian 12             |
| Runtime: Node.js 20+                     |
|                                           |
| Components:                               |
|  1. Alto bundler process                  |
|  2. VerifyingPaymaster signing service    |
|  3. Reverse proxy (Caddy/nginx)           |
|                                           |
| External dependencies:                    |
|  - RPC endpoint (chain node)              |
|  - Executor wallet (funded with gas token)|
+-------------------------------------------+
```

#### Monthly Infrastructure Cost

| Component | Provider | Cost |
|-----------|----------|------|
| **VPS** | Hetzner CX22 (2 vCPU, 4GB) | $5-8/mo |
| **RPC endpoint** | Free tier (Ankr, Blast, LlamaNodes) | $0/mo |
| **RPC endpoint** | Paid (Chainstack, Alchemy) | $20-50/mo |
| **Domain + SSL** | Cloudflare (existing) | $0/mo |
| **Executor wallet funding** | Gas token deposit (one-time) | $10-50 |
| **Monitoring** | Uptime Kuma (self-hosted) or Grafana Cloud free | $0/mo |
| **Total (minimal)** | | **$5-8/mo** |
| **Total (production)** | | **$25-60/mo** |

#### VerifyingPaymaster Setup

The self-hosted paymaster consists of two parts:

**1. On-chain contract (deploy once):**

```solidity
// Use Coinbase's open-source VerifyingPaymaster
// https://github.com/coinbase/verifying-paymaster
//
// Deploy with a trusted signer address (your server's signing key).
// The contract verifies signatures from the signer to approve sponsorship.
```

**2. Off-chain signing service (run alongside Alto):**

```typescript
// Minimal signing service (runs as HTTP endpoint)
// Receives UserOp, validates eligibility (rate limits, user tier),
// signs sponsorship approval, returns paymasterAndData to client.

import { privateKeyToAccount } from "viem/accounts";
import { encodePacked, keccak256 } from "viem";

const signer = privateKeyToAccount(PAYMASTER_SIGNER_KEY);

async function signSponsorshipRequest(userOp: UserOperation): Promise<Hex> {
  // 1. Check user eligibility (rate limits, subscription tier)
  // 2. Compute sponsorship hash
  const hash = computePaymasterHash(userOp, validUntil, validAfter);
  // 3. Sign with paymaster signer
  const signature = await signer.signMessage({ message: { raw: hash } });
  // 4. Return paymasterAndData (paymaster address + validUntil + validAfter + signature)
  return encodePacked(
    ["address", "uint48", "uint48", "bytes"],
    [PAYMASTER_ADDRESS, validUntil, validAfter, signature]
  );
}
```

**Operational concerns:**
- The signer key must be protected (HSM ideal, at minimum encrypted at rest).
- The signing service must enforce rate limits to prevent gas drain attacks.
- The executor wallet must be monitored and auto-refilled.

### 4.4 Scenario Comparison Summary

| Factor | A: Same Chain, Swap Bundler | B: Cross-Chain Migration | C: Self-Hosted on Base |
|--------|---------------------------|-------------------------|----------------------|
| **Complexity** | Low | High | Low |
| **User impact** | None | Low (same seed works) | None |
| **Agent code changes** | None | Significant (dual query) | None |
| **Data continuity** | Seamless | Requires merge logic | Seamless |
| **Per-op cost** | $0.005 (Base) or $0.00076 (Gnosis, if started there) | $0.00076 (Gnosis) | $0.005 (Base) |
| **Monthly @ 1K users** | $4,200 + $30 infra (Base) | $638 + $60 infra (Gnosis) | $4,200 + $30 infra |
| **When to choose** | Default. Always prefer this. | Only when cost savings justify complexity (500+ users) | Same as A, just noting it is on Base specifically |

---

## 5. Recommendation & Timeline

### Phase 1: Beta (Now -- Month 6)

**Provider:** Coinbase CDP on Base
**Chain:** Base (Mainnet or Sepolia for initial testing)
**Cost:** $0 (covered by $15K credits)

| Action | Priority | Est. Effort |
|--------|----------|------------|
| Apply for Base Gasless Campaign credits | P0 | 1 hour |
| Deploy EventfulDataEdge on Base Sepolia | P0 | 2 hours |
| Update subgraph for Base | P0 | 2 hours |
| Integrate CDP paymaster in `builder.ts` | P0 | 1 day |
| Update relay proxy to forward to CDP | P0 | 4 hours |
| Deploy EventfulDataEdge on Base Mainnet | P1 | 2 hours |
| Deploy subgraph to Graph Studio (Base) | P1 | 2 hours |

**Milestone:** First fact written on Base via CDP paymaster.

**Fallback (if CDP application rejected):** Continue with Pimlico on Gnosis Chiado. The existing integration is complete and functional.

### Phase 2: Growth (Month 6 -- Month 18)

**Provider:** Coinbase CDP on Base (credits still available at <500 users)
**Cost:** Still covered by credits (100 users = $449/mo, credits last 33 months)

| Action | Priority | Est. Effort |
|--------|----------|------------|
| Monitor credit burn rate | P1 | Ongoing |
| Prototype self-hosted Alto bundler | P2 | 2 days |
| Deploy VerifyingPaymaster on Base Sepolia | P2 | 1 day |
| Test full flow with self-hosted bundler | P2 | 1 day |
| Keep Pimlico + Gnosis as fallback | P3 | Maintenance only |

**Decision point:** When credits reach 25% remaining ($3,750 left), evaluate:
- If <200 users: credits will last another 8+ months. Stay on CDP.
- If 200-500 users: credits will last 2-4 months. Begin self-hosted bundler deployment.
- If 500+ users: credits will run out within 2 months. Accelerate self-hosted migration.

### Phase 3: Scale (Month 18+)

**Provider:** Self-hosted Alto bundler on Base
**Chain:** Base (same chain -- Scenario A)
**Cost:** ~$0.005/op + $30-60/mo infrastructure

| Action | Priority | Est. Effort |
|--------|----------|------------|
| Deploy Alto bundler to production VPS | P0 | 1 day |
| Deploy VerifyingPaymaster on Base Mainnet | P0 | 2 hours |
| Deploy paymaster signing service | P0 | 1 day |
| Switch relay proxy from CDP to Alto | P0 | 1 hour |
| Set up monitoring + alerting | P0 | 4 hours |
| Fund executor wallet | P0 | 30 min |
| Monitor executor wallet balance | P1 | Automated |

**Milestone:** First fact written via self-hosted bundler. Zero user-facing changes.

### Phase 4: Optimization (If Needed)

**Only if Base gas costs become a significant line item (>$5,000/mo).**

At that point (likely 1,000+ users), evaluate Scenario B (cross-chain migration to Gnosis):

| Monthly savings from Gnosis | Users | Worth the complexity? |
|---------------------------|-------|----------------------|
| $3,562/mo saved | 1,000 | Borderline. $43K/year savings vs dual-subgraph complexity. |
| $17,810/mo saved | 5,000 | Yes. $214K/year savings justifies the engineering investment. |
| $35,620/mo saved | 10,000 | Absolutely. Build the dual-subgraph architecture. |

**Decision threshold:** Migrate to Gnosis when monthly gas cost on Base exceeds $5,000 AND the team has capacity for the dual-subgraph engineering work (estimated 1-2 weeks).

### Cost Projection Summary

| Phase | Users | Monthly Cost | Provider |
|-------|-------|-------------|----------|
| Beta (Mo 1-6) | 10-50 | $0 (credits) | Coinbase CDP + Base |
| Growth (Mo 6-18) | 50-500 | $0-$2,247 (credits) | Coinbase CDP + Base |
| Scale (Mo 18+) | 500-1K | $2,500-$4,200 + $40 infra | Self-hosted Alto + Base |
| Optimization (Mo 24+) | 1K+ | $638 + $60 infra (Gnosis) | Self-hosted Alto + Gnosis |

### Key Decision Points

```
Credits < 25% remaining?
  YES -> Begin self-hosted bundler prep (Phase 3)
  NO  -> Stay on CDP

Monthly gas > $5,000?
  YES -> Evaluate Gnosis migration (Phase 4)
  NO  -> Stay on Base with self-hosted bundler

Monthly gas > $15,000? (3K+ users)
  YES -> Gnosis migration is mandatory
  NO  -> Base is fine
```

---

## Appendix A: Integration Code Changes for CDP Migration

### builder.ts Changes

The key change is replacing `createPimlicoClient` with CDP's paymaster:

```typescript
// BEFORE (Pimlico):
import { createPimlicoClient } from "permissionless/clients/pimlico";

const pimlicoClient = createPimlicoClient({
  transport: http(rpcUrl),
  entryPoint: { address: entryPoint07Address, version: "0.7" },
});

const smartAccountClient = createSmartAccountClient({
  account: smartAccount,
  chain,
  bundlerTransport: http(rpcUrl),
  paymaster: pimlicoClient,
});

// AFTER (CDP):
// CDP exposes an ERC-7677 compliant paymaster endpoint.
// permissionless.js supports ERC-7677 paymasters natively.
const smartAccountClient = createSmartAccountClient({
  account: smartAccount,
  chain,
  bundlerTransport: http(rpcUrl), // relay proxy -> CDP bundler
  paymaster: {
    getPaymasterData: async (userOperation) => {
      // The relay proxy handles adding the CDP API key
      const response = await fetch(`${serverUrl}/v1/paymaster`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jsonrpc: "2.0",
          method: "pm_getPaymasterStubData",
          params: [userOperation, entryPoint07Address, chainId.toString()],
        }),
      });
      return response.json();
    },
  },
});
```

### resolveChain() Update

```typescript
async function resolveChain(chainId: number): Promise<Chain> {
  const { gnosis, gnosisChiado, base, baseSepolia } = await import("viem/chains");
  switch (chainId) {
    case 100: return gnosis;
    case 10200: return gnosisChiado;
    case 8453: return base;          // NEW
    case 84532: return baseSepolia;   // NEW
    default:
      throw new Error(`Unsupported chain ID ${chainId}`);
  }
}
```

---

## Appendix B: Sources

- [Pimlico Pricing](https://docs.pimlico.io/infra/platform/pricing)
- [Pimlico Supported Chains](https://docs.pimlico.io/guides/supported-chains)
- [Pimlico Alto Self-Hosting](https://docs.pimlico.io/references/bundler/self-host)
- [Alto GitHub](https://github.com/pimlicolabs/alto)
- [Coinbase CDP Paymaster](https://docs.cdp.coinbase.com/paymaster/introduction/welcome)
- [Coinbase Verifying Paymaster (GitHub)](https://github.com/coinbase/verifying-paymaster)
- [Base Gasless Campaign](https://docs.base.org/base-account/more/base-gasless-campaign)
- [Base Paymaster Gas Credits Application](https://docs.google.com/forms/d/e/1FAIpQLScxhJxK_AC0PZ_wMgLU9M93gaxctE7x643tW6CA26CflvTlWQ/viewform)
- [ZeroDev Pricing](https://zerodev.app/pricing)
- [Alchemy Pricing](https://www.alchemy.com/pricing)
- [Alchemy Rundler (GitHub)](https://github.com/alchemyplatform/rundler)
- [Biconomy Nexus](https://www.biconomy.io/nexus)
- [Etherspot Pricing](https://etherspot.io/pricing/)
- [Etherspot Skandha (GitHub)](https://github.com/etherspot/skandha)
- [Etherspot Arka Paymaster (GitHub)](https://github.com/etherspot/arka)
- [Thirdweb Bundler & Paymaster](https://portal.thirdweb.com/connect/account-abstraction/infrastructure)
- [Safe 4337 Module](https://docs.safe.global/advanced/erc-4337/4337-safe)
- [Particle Network Paymaster](https://developers.particle.network/guides/aa/paymaster)
- [Candide Voltaire (GitHub)](https://github.com/candidelabs/voltaire)
- [Circle Paymaster](https://www.circle.com/paymaster)
- [ERC-4337 Bundler Docs](https://docs.erc4337.io/bundlers/index.html)
- [ERC-4337 Paymasters Docs](https://docs.erc4337.io/paymasters/index.html)
- [Graph Studio - Base Support](https://thegraph.com/blog/the-graph-indexing-data-coinbase-Base-l2/)
- [Base Gas Tracker](https://basescan.org/gastracker)
- [Gnosis Gas Tracker](https://gnosisscan.io/gastracker)
