# Paymaster/Bundler Provider Cost Comparison

**Date:** 2026-03-05
**Context:** Deciding between providers for TotalReclaw's ERC-4337 UserOp submission

## Key Finding: Two Pricing Models

| Model | How it works | Chain matters? | Providers |
|-------|-------------|---------------|-----------|
| **Credit-based** | Fixed cost per UserOp regardless of gas | No | Pimlico, ZeroDev |
| **Gas pass-through + markup** | You pay actual gas + 7-8% fee | Yes | Coinbase CDP, Alchemy |

## Per-UserOp Cost

| Provider + Chain | Gas Cost | Provider Fee | Total per UserOp |
|-----------------|----------|--------------|------------------|
| **Coinbase CDP + Base** | $0.005 | 7% ($0.00035) | **$0.00535** |
| **Alchemy + Base** | $0.005 | 8% ($0.0004) | **$0.0054** |
| **Pimlico + Gnosis** | $0.00076 | credits ($0.0105) | **$0.01058** |
| **Self-operated + Gnosis** | $0.00076 | none | **$0.00076** |

Note: Alchemy does NOT support Gnosis for AA infrastructure (bundler + paymaster).

## Monthly Cost at Scale (power users @ 28 facts/day)

| Provider | 100 users ($84K ops) | 1K users ($840K ops) | 10K users ($8.4M ops) |
|----------|---------------------|---------------------|-----------------------|
| **Coinbase CDP + Base** | $449 | $4,494 | $44,940 |
| **Pimlico + Gnosis** | $789 | $8,784 | $88,739 |
| **Self-operated + Gnosis** | $64 | $638 | $6,384 |

## Coinbase $15K Credit Burn Rate

| Scale | Monthly cost | Months $15K lasts |
|-------|-------------|-------------------|
| 100 users | $449/mo | **33 months** |
| 1,000 users | $4,494/mo | **3.3 months** |
| 10,000 users | $44,940/mo | **10 days** |

## 12-Month Total Cost

| Provider | 100 users | 1K users | 10K users |
|----------|-----------|----------|-----------|
| **Coinbase CDP + Base** | $5,388 | $53,928 | $539,280 |
| **Pimlico + Gnosis** | $9,468 | $105,408 | $1,064,868 |
| **Self-operated + Gnosis** | $768 | $7,656 | $76,608 |

## Recommendation

1. **Beta (now):** Pimlico pay-as-you-go on Gnosis/Chiado. Already integrated. ~$0/month for <10 users.
2. **Growth (100-300 users):** Evaluate Coinbase CDP + Base migration vs self-operated bundler on Gnosis.
3. **Scale (1K+ users):** Self-operated bundler on Gnosis is 14x cheaper than any managed provider.

## Constraints

- Coinbase CDP: Base only (not Gnosis)
- Alchemy AA: Does not support Gnosis Chain
- Pimlico: Supports Gnosis + Chiado, credit-based pricing (chain-agnostic)
- ZeroDev: $69/mo Growth tier, credit-based, supports Gnosis
- Base gas: Variable (L1 data fee spikes during Ethereum congestion)
- Gnosis gas: Stable (xDAI stablecoin, no L1 data fee)
