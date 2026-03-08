# TotalReclaw Chiado Testnet Gas Validation Report

**Generated:** 2026-03-04T00:47:48.265Z
**Network:** Gnosis Chiado Testnet (chainId=10200)
**RPC:** https://rpc.chiadochain.net
**Contract:** `0xA84c5433110Ccc93e57ec387e630E86Bad86c36f` (EventfulDataEdge)
**Wallet:** `0x30d37b26257e03942dFCf12251FC25e41ca38cA8`
**Balance before:** 0.998582813493386463 xDAI
**Balance after:** 0.994281236473312437 xDAI
**Total spent:** 0.004302 xDAI
**Transactions:** 10 succeeded, 0 failed, 10 total

## Per-Transaction Results

| # | Description | Words | Indices | Emb | Calldata (B) | Gas Used | Gas Price (Gwei) | Cost (xDAI) | Cost (USD) | Gas/Byte | Wait (s) |
|---|-------------|-------|---------|-----|-------------|----------|-----------------|-------------|------------|----------|----------|
| #1 Quick note | remember my wifi password is X | 10 | 15 | N | 1,311 | 73,410 | 1.50 | 0.000110 xDAI | $0.000110 | 56.0 | 9.0 |
| #2 Short fact | I prefer dark mode in all apps | 20 | 30 | N | 2,362 | 115,450 | 1.50 | 0.000173 xDAI | $0.000173 | 48.9 | 13.3 |
| #3 Short fact + embedding | Same as #2 with semantic search | 20 | 30 | Y | 5,493 | 240,690 | 1.50 | 0.000361 xDAI | $0.000361 | 43.8 | 5.0 |
| #4 Medium fact | Meeting notes from standup | 50 | 60 | N | 4,522 | 201,760 | 1.50 | 0.000303 xDAI | $0.000303 | 44.6 | 5.0 |
| #5 Typical fact + embedding | Most common OpenClaw usage | 50 | 60 | Y | 7,653 | 327,060 | 1.50 | 0.000491 xDAI | $0.000491 | 42.7 | 17.2 |
| #6 Long conversation extract | Full meeting summary | 100 | 90 | Y | 9,933 | 418,290 | 1.50 | 0.000627 xDAI | $0.000627 | 42.1 | 29.5 |
| #7 Heavy indices | Many unique keywords | 30 | 150 | Y | 13,473 | 559,920 | 1.50 | 0.000840 xDAI | $0.000840 | 41.6 | 5.0 |
| #8 Minimal | Tiny preference | 5 | 8 | N | 819 | 53,760 | 1.50 | 0.000081 xDAI | $0.000081 | 65.6 | 4.9 |
| #9 Large extract | Long document summary | 200 | 120 | Y | 12,513 | 521,400 | 1.50 | 0.000782 xDAI | $0.000782 | 41.7 | 25.5 |
| #10 Repeat of #5 (consistency) | Verify consistent gas | 50 | 60 | Y | 7,653 | 327,060 | 1.50 | 0.000491 xDAI | $0.000491 | 42.7 | 5.0 |

## Summary Statistics

| Metric | Min | Avg | Max |
|--------|-----|-----|-----|
| Gas Used | 53,760 | 283,880 | 559,920 |
| Cost (xDAI) | 0.000081 xDAI | 0.000426 xDAI | 0.000840 xDAI |
| Cost (USD) | $0.000081 | $0.000426 | $0.000840 |
| Gas Price (Gwei) | 1.50 | 1.50 | 1.50 |
| Gas/Byte | 41.6 | 47.0 | 65.6 |
| Confirmation Time (s) | 4.9 | 11.9 | 29.5 |

## Consistency Check (#5 vs #10 -- identical payload specs)

| Metric | #5 | #10 | Difference |
|--------|-----|------|-----------|
| Gas Used | 327,060 | 327,060 | 0 (0.0%) |
| Cost (xDAI) | 0.000491 xDAI | 0.000491 xDAI | 0.00e+0 xDAI |
| Calldata (B) | 7,653 | 7,653 | 0 |

> Gas difference of 0.0% is expected due to random payload content (different zero/non-zero byte ratios in calldata).

## Embedding Cost Impact

| Word Count | Gas (no emb) | Gas (with emb) | Calldata (no emb) | Calldata (with emb) | Gas Overhead | Cost Overhead |
|------------|-------------|----------------|-------------------|--------------------|--------------|--------------| 
| 20 | 115,450 | 240,690 | 2,362 | 5,493 | +125,240 (+108.5%) | +0.000188 xDAI |
| 50 | 201,760 | 327,060 | 4,522 | 7,653 | +125,300 (+62.1%) | +0.000188 xDAI |

## Cost Projections

**Representative fact:** #5 Typical fact + embedding (Most common OpenClaw usage)
- Calldata: 7,653 bytes
- Gas: 327,060
- Cost: 0.000491 xDAI ($0.000491)
- Gas price: 1.50 Gwei

### Monthly Cost Per User

| Usage | Facts/Day | Facts/Month | Monthly Cost (xDAI) | Monthly Cost (USD) |
|-------|-----------|-------------|--------------------|--------------------|
| Casual | 10 | 300 | 0.1472 xDAI | $0.1472 |
| Active | 50 | 1,500 | 0.7359 xDAI | $0.7359 |
| Power user | 100 | 3,000 | 1.4718 xDAI | $1.47 |

### Platform Monthly Cost (10 facts/user/day)

| Users | Facts/Month | Monthly Gas Cost (xDAI) | Monthly Gas Cost (USD) | Per-User Cost |
|-------|-------------|------------------------|----------------------|---------------|
| 100 | 30,000 | 14.7177 xDAI | $14.72 | $0.1472 |
| 1,000 | 300,000 | 147.1770 xDAI | $147.18 | $0.1472 |
| 10,000 | 3,000,000 | 1471.7700 xDAI | $1471.77 | $0.1472 |

### Platform Monthly Cost (50 facts/user/day -- power users)

| Users | Facts/Month | Monthly Gas Cost (xDAI) | Monthly Gas Cost (USD) | Per-User Cost |
|-------|-------------|------------------------|----------------------|---------------|
| 100 | 150,000 | 73.5885 xDAI | $73.59 | $0.7359 |
| 1,000 | 1,500,000 | 735.8850 xDAI | $735.89 | $0.7359 |
| 10,000 | 15,000,000 | 7358.8500 xDAI | $7358.85 | $0.7359 |

## Comparison with Theoretical Estimate

The comprehensive report estimated $0.00076/fact on Gnosis Chain based on:
- 379,650 gas/fact (Hardhat measurement)
- 2 Gwei gas price assumption

| Metric | Theoretical | Actual (Chiado) | Difference |
|--------|-------------|----------------|------------|
| Gas per typical fact | 379,650 | 327,060 | -52,590 (-13.9%) |
| Gas price | 2.00 Gwei | 1.50 Gwei | -0.50 Gwei |
| Cost per fact | $0.000760 | $0.000491 | $-2.69e-4 |

> Actual cost is **1.5x lower** than theoretical. This is likely due to lower gas prices on Chiado testnet.

## Gnosis Mainnet Projection

Gnosis mainnet typically has lower gas prices than Chiado testnet.
Using conservative estimates:

| Gas Price (Gwei) | Cost/Fact (xDAI) | Cost/Fact (USD) | Monthly (10 facts/day) | Monthly (50 facts/day) |
|-----------------|-----------------|----------------|----------------------|----------------------|
| 1.0 | 0.000327 xDAI | $0.000327 | $0.0981 | $0.4906 |
| 2.0 | 0.000654 xDAI | $0.000654 | $0.1962 | $0.9812 |
| 5.0 | 0.001635 xDAI | $0.001635 | $0.4906 | $2.45 |

## Transaction Hashes (Chiado Explorer)

- **#1 Quick note**: [`0x6281d2e728b804a37fa56e09c0b4a6e6c95799a6548db7a92f47167a84ae7e14`](https://gnosis-chiado.blockscout.com/tx/0x6281d2e728b804a37fa56e09c0b4a6e6c95799a6548db7a92f47167a84ae7e14)
- **#2 Short fact**: [`0xd105f3cfad01f6fbbecb419e27dde25e9a4701e032b7eb7e47a769eaa50cf26f`](https://gnosis-chiado.blockscout.com/tx/0xd105f3cfad01f6fbbecb419e27dde25e9a4701e032b7eb7e47a769eaa50cf26f)
- **#3 Short fact + embedding**: [`0x8da97296aff6c1c3779e235cbfcea1cb1d2d13bec77eebb33872e1802bb517f5`](https://gnosis-chiado.blockscout.com/tx/0x8da97296aff6c1c3779e235cbfcea1cb1d2d13bec77eebb33872e1802bb517f5)
- **#4 Medium fact**: [`0x2be80aba9e92dc63bd9ed56cad61a44c4ba1caa3a4779d72dc35343580c4e742`](https://gnosis-chiado.blockscout.com/tx/0x2be80aba9e92dc63bd9ed56cad61a44c4ba1caa3a4779d72dc35343580c4e742)
- **#5 Typical fact + embedding**: [`0x27db95bd0f1e170ec15ee5aaf8f2518ffc8e2782debfc7e79e59d80d825ba449`](https://gnosis-chiado.blockscout.com/tx/0x27db95bd0f1e170ec15ee5aaf8f2518ffc8e2782debfc7e79e59d80d825ba449)
- **#6 Long conversation extract**: [`0x57ed06bfb4c785e0380f396e02129c6ed500b44edbc44901944fa98a97747ac3`](https://gnosis-chiado.blockscout.com/tx/0x57ed06bfb4c785e0380f396e02129c6ed500b44edbc44901944fa98a97747ac3)
- **#7 Heavy indices**: [`0xf8c342408e5ce87d9f24822427c19f1f67c9f51e185ce5585e44ebf8394ffa0a`](https://gnosis-chiado.blockscout.com/tx/0xf8c342408e5ce87d9f24822427c19f1f67c9f51e185ce5585e44ebf8394ffa0a)
- **#8 Minimal**: [`0xee2898c7d18f7574342ffd1e33a46bf3e1df3f73f4da1cc1054003ff7bf1e96a`](https://gnosis-chiado.blockscout.com/tx/0xee2898c7d18f7574342ffd1e33a46bf3e1df3f73f4da1cc1054003ff7bf1e96a)
- **#9 Large extract**: [`0x4da190ef3efd92fc2d9b2b609ae1ca7ef20c3c35b1061752b4fad3f4edba0e1a`](https://gnosis-chiado.blockscout.com/tx/0x4da190ef3efd92fc2d9b2b609ae1ca7ef20c3c35b1061752b4fad3f4edba0e1a)
- **#10 Repeat of #5 (consistency)**: [`0x43d9137ea95761656ef48167964f4efcbfa594371beb1c16a0b480f5cda856f6`](https://gnosis-chiado.blockscout.com/tx/0x43d9137ea95761656ef48167964f4efcbfa594371beb1c16a0b480f5cda856f6)

## Key Takeaways

1. **Actual cost per typical fact:** $0.000491 on Chiado testnet
2. **Gas price observed:** 1.50 Gwei (avg across 10 transactions)
3. **Confirmation time:** 11.9s average (Chiado has ~5s block times)
4. **Embedding overhead:** adds ~3,128 bytes of calldata per fact
5. **Blind indices scale linearly:** each index adds ~66 bytes (64 hex chars + protobuf overhead)
6. **Gnosis Chain remains extremely cheap** for on-chain memory storage
