# Paymaster Comparison: Pimlico vs ZeroDev

**Date:** 2026-03-03
**Context:** TotalReclaw gas sponsorship on Gnosis Chain
**Task:** T362

---

## Summary & Recommendation

**Recommendation: Pimlico**

Pimlico is the stronger choice for TotalReclaw's paymaster needs on Gnosis Chain. The key reasons:

1. **Confirmed Gnosis Chain + Chiado testnet support** with EntryPoint v0.6, v0.7, and v0.8 -- explicitly documented with chain IDs and account compatibility matrices.
2. **Purpose-built webhook sponsorship policies** with cryptographic verification (`@pimlico/webhook` package), structured request/response format, and per-UserOp approve/reject capability -- exactly what we need for subscription gating.
3. **Pay-as-you-go pricing** with no monthly commitment (10% gas surcharge + ~$0.0105/sponsored UserOp) -- ideal for a startup with unpredictable early usage.
4. **`permissionless.js`** is the de facto standard TypeScript SDK for ERC-4337, built on viem, with explicit Gnosis Chain integration guides in the Gnosis Chain docs themselves.
5. **Infrastructure-only** -- Pimlico provides bundler + paymaster without imposing a smart account implementation, giving us maximum flexibility.

ZeroDev is a strong product but is better suited for teams that want a full-stack smart account platform (account creation, session keys, plugins, batching). For TotalReclaw, where the smart account is seed-derived and the primary need is gas sponsorship with custom webhook gating, Pimlico's focused infrastructure approach is a better fit.

---

## Detailed Comparison

| Dimension | Pimlico | ZeroDev | Winner |
|-----------|---------|---------|--------|
| **Gnosis mainnet (100)** | Supported (v0.6, v0.7, v0.8) | Supported (docs + Gnosis guide) | Tie |
| **Chiado testnet (10200)** | Explicitly supported (v0.6, v0.7, v0.8) | Not explicitly confirmed in docs | Pimlico |
| **EntryPoint v0.7** | Supported (bundler + paymaster) | Supported (Kernel v3) | Tie |
| **Webhook policies** | Native, with crypto verification | Supported (simpler: true/false) | Pimlico |
| **Bundler included** | Yes (Alto, TypeScript) | Yes (meta-infra, proxied) | Pimlico |
| **Pricing model** | Pay-as-you-go, 10% surcharge | $69-399/mo tiers | Pimlico |
| **Free tier** | Testnet only, 1M credits | 50K testnet credits | Pimlico |
| **TypeScript SDK** | permissionless.js (244 stars) | ZeroDev SDK + permissionless.js (54 stars) | Pimlico |
| **Smart accounts** | Any (Safe, Kernel, Simple, Light, Biconomy) | Kernel (own product) | Pimlico |
| **Documentation** | Excellent, Gnosis-specific guides | Good, Gnosis guide available | Pimlico |
| **Community** | Active GitHub, Slack/Telegram support | Active GitHub, Discord | Tie |

---

## Dimension-by-Dimension Analysis

### 1. Chain Support

**Pimlico:**
- Gnosis Chain (100): Full support -- EntryPoint v0.6, v0.7, v0.8
- Chiado Testnet (10200): Full support -- EntryPoint v0.6, v0.7, v0.8
- Account types on Gnosis: Safe 1.4.1, Kernel 0.2.1-0.2.4, Light 1.1.0, SimpleAccount, Biconomy, Etherspot
- API endpoint format: `https://api.pimlico.io/v2/gnosis/rpc?apikey=YOUR_KEY`
- Documented in both Pimlico docs and Gnosis Chain official docs

**ZeroDev:**
- Gnosis Chain (100): Supported -- confirmed via Gnosis Chain docs and ZeroDev dashboard
- Chiado Testnet (10200): Not explicitly listed in available documentation; ZeroDev claims "50+ networks" but does not publish a definitive chain list
- Dashboard-based chain selection: Create project, select "Gnosis," receive ProjectID/BundlerRPC/PaymasterRPC

**Verdict:** Pimlico wins. Explicit support matrix with EntryPoint versions and account types for both Gnosis mainnet AND Chiado testnet. ZeroDev's Gnosis support is confirmed for mainnet but testnet coverage is unclear.

### 2. Sponsorship Policies (Webhook)

This is the most critical dimension for TotalReclaw. We need the relay server to approve/reject gas sponsorship per-UserOp based on subscription status.

**Pimlico:**
- Dedicated webhook sponsorship policy feature
- Webhook receives structured JSON with `type: "user_operation.sponsorship.requested"` containing:
  - Full UserOperation details
  - EntryPoint address
  - Chain ID
  - Sponsorship policy ID
  - API key
- Respond with `{"sponsor": true}` or `{"sponsor": false}`
- Second notification webhook fires on `"user_operation.sponsorship.finalized"`
- Cryptographic verification via `@pimlico/webhook` npm package (HMAC with webhook secret)
- Can combine with other policy rules: global maximums, per-user limits, date ranges, chain restrictions
- Configuration via Pimlico dashboard (attach webhook URL to a sponsorship policy)

**ZeroDev:**
- Custom gas policy webhook feature
- Webhook accepts UserOps, returns `true` (sponsored) or `false` (not sponsored)
- Simpler interface -- less structured than Pimlico's
- Can be configured via dashboard or admin API
- Also supports predefined policies (global limits, per-user limits)

**Verdict:** Pimlico wins. More mature webhook implementation with cryptographic verification, structured event types (requested vs. finalized), and richer metadata in the webhook payload. Both support the core approve/reject flow, but Pimlico's implementation is more production-ready for a billing integration.

### 3. Bundler

**Pimlico:**
- **Alto** bundler -- open-source, written in TypeScript
- 211 GitHub stars, 80 forks, actively maintained (last push: 2026-03-03)
- Focused on transaction inclusion reliability (handles gas price spikes, chain reorgs)
- Supports EntryPoint v0.6, v0.7, v0.8
- Runs as a hosted service via Pimlico API, or self-hostable

**ZeroDev:**
- "Meta infrastructure" approach -- ZeroDev proxies bundler traffic to multiple providers (Pimlico, Alchemy, Gelato, StackUp)
- More reliable in theory (fallback across providers), but adds a layer of indirection
- You are not running Pimlico's bundler directly; ZeroDev acts as an intermediary

**Verdict:** Pimlico wins for our use case. Direct bundler access with no intermediary. ZeroDev's meta-infra is clever for reliability but adds complexity and a dependency on ZeroDev's proxy layer. If ZeroDev's meta-infra routes to Pimlico anyway, we can cut out the middleman.

### 4. Pricing

**Pimlico (Pay-as-you-go):**
- $0/mo subscription (card required)
- 10M API credits included/month (~13,000 UserOps)
- Additional: $1 per 100,000 credits (~$0.0075/UserOp, ~$0.0105 if sponsored)
- 10% surcharge on actual on-chain gas cost for Verifying Paymaster (mainnet only)
- No minimum commitment
- Billing threshold: $1,000/month triggers immediate payment

**ZeroDev:**
- Developer (Free): 50K testnet credits, no mainnet
- Growth: $69/month -- 100K credits, up to $250 gas sponsorship
- Scale: $399/month -- 1M credits, up to $1,000 gas sponsorship
- Enterprise: Custom

**Verdict:** Pimlico wins decisively. Pay-as-you-go with no monthly fee is ideal for a startup with uncertain early volumes. ZeroDev's $69/mo Growth tier has a $250 gas sponsorship cap which could be limiting, and the jump to $399/mo is steep for early-stage usage.

### 5. SDK

**Pimlico -- `permissionless.js`:**
- 244 GitHub stars, 92 forks
- Built on viem (same patterns, composable)
- Supports all major smart account types: Safe, Kernel, Biconomy, SimpleAccount, TrustWallet, LightAccount
- No provider lock-in by design
- Small bundle size, tree-shakeable
- Extensive documentation with tutorials

**ZeroDev SDK:**
- 54 GitHub stars, 44 forks
- Also built on top of permissionless.js internally
- Tightly coupled to Kernel smart accounts
- Additional abstractions: `createKernelAccount`, `createKernelAccountClient`
- Includes higher-level features: passkeys, social login, session keys, batching

**Verdict:** Pimlico wins. `permissionless.js` is the lower-level, more flexible SDK. Since ZeroDev's own SDK is built on `permissionless.js`, using Pimlico directly gives us the foundational layer without extra abstraction. We don't need ZeroDev's higher-level smart wallet features (passkeys, social login) because TotalReclaw uses seed-derived ECDSA keys.

### 6. Smart Account Flexibility

**Pimlico:** Account-agnostic. Works with Safe, Kernel, SimpleAccount, LightAccount, Biconomy, Etherspot, or any custom ERC-4337 account. Documentation covers all major implementations.

**ZeroDev:** Kernel-first. While Kernel is excellent (gas-efficient, modular, ERC-7579 compatible), ZeroDev's SDK and documentation are optimized for Kernel. Using a different account type is possible but not the primary path.

**Verdict:** Pimlico wins. TotalReclaw's billing spec uses SimpleAccount derived from a BIP-39 seed. Pimlico explicitly supports SimpleAccount on Gnosis Chain across all EntryPoint versions.

### 7. Documentation Quality

**Pimlico:**
- Comprehensive docs at docs.pimlico.io
- Gnosis Chain-specific integration guide in Gnosis Chain official docs
- Step-by-step tutorials for paymaster, bundler, and account setup
- Explicit supported chains page with EntryPoint version matrix
- API reference for all bundler and paymaster methods

**ZeroDev:**
- Good docs at docs.zerodev.app
- Gnosis Chain guide in Gnosis Chain official docs
- Focus on higher-level "getting started" experience
- Chain support less explicitly documented (no published matrix)
- Blog posts explaining concepts well

**Verdict:** Pimlico edges ahead. The explicit chain support matrix and dedicated webhook documentation are particularly valuable for our integration.

### 8. Community & Support

**Pimlico:**
- GitHub: permissionless.js (244 stars), Alto (211 stars) -- both actively maintained
- Support: Community (free), private Slack/Telegram (pay-as-you-go), 24/7 phone (enterprise)
- Founded by known AA researchers; active in ERC-4337 ecosystem

**ZeroDev:**
- GitHub: Kernel (238 stars), SDK (54 stars) -- Kernel actively maintained
- Support: Community (free), team support (Growth+), dedicated engineering (Enterprise)
- 6M+ smart accounts deployed, 200+ teams
- Active on X/Twitter with feature announcements

**Verdict:** Tie. Both have active communities and responsive support channels. ZeroDev has more deployed smart accounts (indicative of a broader user base for the full-stack product), while Pimlico has stronger infrastructure-focused community engagement.

---

## Integration Notes

### Pimlico Integration Pattern for TotalReclaw

```typescript
// 1. Install dependencies
// npm install permissionless viem @pimlico/webhook

// 2. Set up clients
import { createPublicClient, http } from "viem";
import { gnosis } from "viem/chains";
import { createPimlicoClient } from "permissionless/clients/pimlico";
import { createBundlerClient } from "permissionless";

const publicClient = createPublicClient({
  chain: gnosis,
  transport: http("https://gnosis.drpc.org"),
});

const pimlicoClient = createPimlicoClient({
  chain: gnosis,
  transport: http(
    `https://api.pimlico.io/v2/gnosis/rpc?apikey=${PIMLICO_API_KEY}`
  ),
  entryPoint: { version: "0.7" },
});

const bundlerClient = createBundlerClient({
  chain: gnosis,
  transport: http(
    `https://api.pimlico.io/v2/gnosis/rpc?apikey=${PIMLICO_API_KEY}`
  ),
  entryPoint: { version: "0.7" },
});
```

### Webhook Handler (Relay Server)

```typescript
// Express endpoint on the relay server
import { pimlicoWebhookVerifier } from "@pimlico/webhook";

app.post("/webhook/paymaster", async (req, res) => {
  // 1. Verify webhook signature
  const verifier = pimlicoWebhookVerifier(WEBHOOK_SECRET);
  if (!verifier(req)) {
    return res.status(401).json({ sponsor: false });
  }

  // 2. Extract user's smart account address from UserOp
  const { userOperation, chainId } = req.body.data.object;
  const sender = userOperation.sender;

  // 3. Check subscription status
  const subscription = await db.getSubscription(sender);

  if (subscription.tier === "paid" && subscription.active) {
    return res.json({ sponsor: true });
  }

  if (subscription.tier === "free") {
    const usage = await db.getMonthlyUsage(sender);
    if (usage < FREE_TIER_QUOTA) {
      return res.json({ sponsor: true });
    }
  }

  return res.json({ sponsor: false });
});
```

### Sponsorship Policy Setup (Pimlico Dashboard)

1. Create a sponsorship policy in the Pimlico dashboard
2. Set "Enabled Chains" to Gnosis Chain only
3. Set a global maximum USD spend as a safety net
4. Attach webhook URL: `https://relay.totalreclaw.com/webhook/paymaster`
5. Copy the webhook secret for signature verification
6. Use the sponsorship policy ID in the `pm_sponsorUserOperation` call

---

## Pricing Analysis

### Assumptions
- Gnosis Chain gas price: ~1 Gwei (xDAI)
- Gas per UserOp: ~380,000 (our measured gas per fact store)
- Gas cost per UserOp: ~0.00038 xDAI (~$0.00038)

### Pimlico Cost Projections

| Daily UserOps | Monthly UserOps | Pimlico API Cost | Pimlico Gas Surcharge (10%) | Total Pimlico Cost | On-chain Gas Cost |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 100 | 3,000 | $0 (within 13K included) | $0.11 | **~$0.11/mo** | $1.14 |
| 500 | 15,000 | ~$2.10 (2K excess) | $0.57 | **~$2.67/mo** | $5.70 |
| 1,000 | 30,000 | ~$17.85 (17K excess) | $1.14 | **~$18.99/mo** | $11.40 |

Notes:
- First ~13,000 UserOps/month included in the 10M free API credits
- Gas surcharge is 10% of actual on-chain gas cost (very small on Gnosis)
- API cost dominates over gas surcharge on Gnosis due to extremely low gas prices

### ZeroDev Cost Projections

| Daily UserOps | Monthly UserOps | ZeroDev Plan | Plan Cost | Gas Sponsorship Cap | Sufficient? |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 100 | 3,000 | Growth | **$69/mo** | $250 | Yes (need ~$1.14) |
| 500 | 15,000 | Growth | **$69/mo** | $250 | Yes (need ~$5.70) |
| 1,000 | 30,000 | Scale | **$399/mo** | $1,000 | Yes (need ~$11.40) |

Notes:
- Growth plan includes 100K credits -- should cover ~15K UserOps
- At 30K UserOps/month, the 100K credit limit on Growth may be insufficient, requiring Scale tier
- Gas sponsorship caps are more than sufficient for Gnosis (gas is very cheap)

### Cost Comparison Summary

| Volume | Pimlico | ZeroDev | Savings with Pimlico |
|--------|---------|---------|---------------------|
| 100/day | ~$0.11/mo | $69/mo | **$68.89/mo (99.8%)** |
| 500/day | ~$2.67/mo | $69/mo | **$66.33/mo (96.1%)** |
| 1,000/day | ~$18.99/mo | $399/mo | **$380.01/mo (95.2%)** |

**Pimlico's pay-as-you-go model is dramatically cheaper at our expected volumes.** The cost difference is most extreme at low volumes (startup phase) where ZeroDev charges a flat monthly fee regardless of usage.

---

## Risk Assessment

### Pimlico Risks
| Risk | Severity | Mitigation |
|------|----------|------------|
| Single bundler provider (no fallback) | LOW | Alto is open-source; can self-host as fallback |
| API credit pricing changes | LOW | Lock in pricing on enterprise plan if volumes grow |
| Gnosis Chain deprioritized | LOW | Gnosis is explicitly in their supported matrix; large AA infra providers don't drop chains |

### ZeroDev Risks
| Risk | Severity | LOW |
|------|----------|-----|
| Meta-infra adds latency | LOW | Proxy overhead is minimal |
| Tier pricing doesn't scale linearly | MEDIUM | Jump from $69 to $399 is steep |
| Kernel lock-in | LOW | Kernel is open-source and ERC-7579 compatible |

---

## Conclusion

For TotalReclaw's specific needs -- gas sponsorship with custom webhook-based subscription gating on Gnosis Chain -- **Pimlico is the clear winner**:

1. **Explicit Gnosis + Chiado support** with documented EntryPoint versions
2. **Production-grade webhook policies** with cryptographic verification
3. **Pay-as-you-go pricing** saves $69-380/month vs ZeroDev at our volumes
4. **`permissionless.js`** is the industry-standard TypeScript SDK for ERC-4337
5. **Account-agnostic** -- works with our SimpleAccount without imposing Kernel

ZeroDev would be the better choice if we needed a full-stack smart wallet platform with passkeys, session keys, and social login. But TotalReclaw's architecture (seed-derived keys, relay-mediated transactions) needs infrastructure, not a wallet framework.

**Next steps:**
1. Sign up for Pimlico (free tier for Chiado testing)
2. Create a sponsorship policy with webhook pointing to relay server
3. Implement the webhook handler for subscription-based gas gating
4. Test the full flow on Chiado testnet before Gnosis mainnet deployment
