# Chiado Testnet Deployment Guide

> Deploy TotalReclaw contracts (EventfulDataEdge + TotalReclawPaymaster) to Gnosis Chiado testnet and configure the subgraph.

**Status:** Deployment-ready. All prerequisites validated.

---

## Prerequisites

| Requirement | Status |
|-------------|--------|
| Hardhat config with Chiado network | Done (`contracts/hardhat.config.ts`) |
| Deploy script supporting Gnosis/Chiado | Done (`contracts/scripts/deploy.ts`) |
| Contracts compile successfully | Done (Solidity 0.8.24, Cancun EVM) |
| Chiado RPC reachable | Verified (`https://rpc.chiadochain.net`, chainId 10200) |
| ERC-4337 EntryPoint v0.7 on Chiado | Verified (`0x0000000071727De22E5E9d8BAf0edAc6f37da032`) |
| Blockscout API (no API key needed) | Verified (`https://gnosis-chiado.blockscout.com/api`) |
| Deployer wallet with Chiado xDAI | **Manual step required** |

---

## Step 1: Create Deployer Wallet

If you don't already have a `.env` file in the project root:

```bash
# Generate a fresh test-only private key
cd /path/to/totalreclaw
node -e "
const crypto = require('crypto');
const { ethers } = require('ethers');
const pk = '0x' + crypto.randomBytes(32).toString('hex');
const wallet = new ethers.Wallet(pk);
console.log('DEPLOYER_PRIVATE_KEY=' + pk);
console.log('Deployer address: ' + wallet.address);
"
```

Create `.env` in the project root (NOT in `contracts/`):

```env
# TotalReclaw — Deployment Configuration
# WARNING: This file contains secrets. NEVER commit to git.

DEPLOYER_PRIVATE_KEY=0x<your-private-key>

# Gnosis Chain RPCs
GNOSIS_RPC_URL=https://rpc.gnosischain.com
CHIADO_RPC_URL=https://rpc.chiadochain.net

# Block explorer API keys (optional for Chiado — Blockscout works without)
GNOSISSCAN_API_KEY=
```

> **Note:** The `.env` file is already in `.gitignore`. It will not be committed.

---

## Step 2: Fund Deployer with Chiado xDAI

The deployer wallet needs Chiado xDAI (test tokens) for gas. Estimated gas cost for deployment: ~0.01-0.05 xDAI (two contract deployments).

### Option A: Official Gnosis Faucet (Recommended)

1. Go to **https://faucet.chiadochain.net/**
2. Select network: **Chiado** (should be default)
3. Paste your deployer address
4. Complete the Cloudflare Turnstile CAPTCHA
5. Click **Claim**
6. Receive 1 xDAI (plus 1 GNO for staking/testing)
7. Rate limit: 1 claim per day

### Option B: ETHGlobal Faucet

1. Go to **https://ethglobal.com/faucet/gnosis-chiado-10200**
2. Paste your deployer address
3. Receive 0.05 xDAI per day

### Option C: Triangle Faucet

1. Go to **https://faucet.triangleplatform.com/gnosis/chiado**
2. Paste your deployer address
3. Complete Google reCAPTCHA
4. Receive 0.001 xDAI

### Option D: dRPC Faucet

1. Go to **https://drpc.org/faucet/gnosis**
2. Select **Chiado Testnet**
3. Paste your deployer address

### Verify Balance

```bash
# Using curl + RPC
curl -s -X POST "https://rpc.chiadochain.net" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_getBalance","params":["<YOUR_ADDRESS>","latest"],"id":1}'

# Using cast (if Foundry installed)
cast balance <YOUR_ADDRESS> --rpc-url https://rpc.chiadochain.net

# Using hardhat
cd contracts && npx hardhat console --network chiado
# > (await ethers.provider.getBalance("<YOUR_ADDRESS>")).toString()
```

---

## Step 3: Compile Contracts

```bash
cd contracts
npx hardhat compile
```

Expected output:
```
Nothing to compile       # if already compiled
No need to generate any newer typings.
```

---

## Step 4: Deploy to Chiado

```bash
cd contracts
npx hardhat run scripts/deploy.ts --network chiado
```

Expected output:
```
=== TotalReclaw Contract Deployment ===
Network:  chiado
Deployer: 0x<your-address>
Balance:  1.0 xDAI

EntryPoint: 0x0000000071727De22E5E9d8BAf0edAc6f37da032

Deploying EventfulDataEdge...
  Address: 0x<edge-address>
  Tx:      0x<tx-hash>

Deploying TotalReclawPaymaster...
  Address: 0x<paymaster-address>
  Tx:      0x<tx-hash>

Addresses saved to /path/to/contracts/deployed-addresses.json
ABI copied to subgraph/abis/

=== Deployment Complete ===
```

The script automatically:
- Saves addresses to `contracts/deployed-addresses.json`
- Copies ABI to `subgraph/abis/EventfulDataEdge.json`

---

## Step 5: Verify Contracts on Blockscout

Blockscout on Chiado does not require an API key for verification.

```bash
cd contracts
npx hardhat run scripts/verify.ts --network chiado
```

Or verify individually:

```bash
# EventfulDataEdge
npx hardhat verify --network chiado <EDGE_ADDRESS> \
  "0x0000000071727De22E5E9d8BAf0edAc6f37da032"

# TotalReclawPaymaster
npx hardhat verify --network chiado <PAYMASTER_ADDRESS> \
  "0x0000000071727De22E5E9d8BAf0edAc6f37da032" \
  "<EDGE_ADDRESS>" \
  100 \
  3600
```

View on Blockscout:
- EventfulDataEdge: `https://gnosis-chiado.blockscout.com/address/<EDGE_ADDRESS>`
- Paymaster: `https://gnosis-chiado.blockscout.com/address/<PAYMASTER_ADDRESS>`

---

## Step 6: Fund Paymaster (Optional)

The paymaster needs xDAI deposited to sponsor UserOperations:

```bash
cd contracts
npx hardhat run scripts/fund-paymaster.ts --network chiado
```

Default: 0.1 xDAI. For testnet, this is plenty (~200-500 sponsored operations).

---

## Step 7: Deploy Subgraph

### 7a: Update subgraph.yaml

After contract deployment, update `subgraph/subgraph.yaml`:

```yaml
dataSources:
  - kind: ethereum
    name: EventfulDataEdge
    network: gnosis-chiado    # IMPORTANT: use 'gnosis-chiado' for Chiado testnet
    source:
      address: "<EDGE_ADDRESS>"     # from deployed-addresses.json
      abi: EventfulDataEdge
      startBlock: <BLOCK_NUMBER>     # from deployed-addresses.json
```

> **Note:** Graph Node uses `gnosis-chiado` as the network identifier for Chiado testnet (not `chiado`). For Gnosis mainnet, use `gnosis`.

### 7b: Build Subgraph

```bash
cd subgraph
npm run codegen
npm run build
```

### 7c: Deploy to Subgraph Studio

1. Create a subgraph on [Subgraph Studio](https://thegraph.com/studio/)
2. Authenticate:
   ```bash
   npx graph auth --studio <DEPLOY_KEY>
   ```
3. Deploy:
   ```bash
   npx graph deploy --studio totalreclaw-chiado
   ```

### Alternative: Deploy to Self-Hosted Graph Node

If using the local docker-compose setup:

```bash
# Start Graph Node (see subgraph/docker-compose.yml)
cd subgraph
docker compose up -d

# Create subgraph
npx graph create --node http://localhost:8020/ totalreclaw

# Deploy
npx graph deploy --node http://localhost:8020/ --ipfs http://localhost:5001 totalreclaw
```

> **Note:** For self-hosted Graph Node with Chiado, configure the `ethereum` endpoint in docker-compose.yml:
> ```yaml
> environment:
>   ethereum: 'gnosis-chiado:https://rpc.chiadochain.net'
> ```

---

## Step 8: Post-Deployment Checklist

- [ ] Contract addresses saved in `contracts/deployed-addresses.json`
- [ ] Contracts verified on Blockscout
- [ ] ABI copied to `subgraph/abis/`
- [ ] `subgraph/subgraph.yaml` updated with contract address and startBlock
- [ ] Subgraph codegen + build successful
- [ ] Subgraph deployed (Studio or self-hosted)
- [ ] Subgraph indexing verified (query a few blocks)
- [ ] Send a test `Log(bytes)` transaction to verify event handling

### Test Transaction

```bash
# Using cast (Foundry)
cast send <EDGE_ADDRESS> \
  "submitLog(bytes)" \
  "0x<protobuf-encoded-data>" \
  --rpc-url https://rpc.chiadochain.net \
  --private-key $DEPLOYER_PRIVATE_KEY
```

---

## Reference

| Resource | URL |
|----------|-----|
| Chiado RPC | `https://rpc.chiadochain.net` |
| Chiado Chain ID | 10200 |
| Block Explorer | https://gnosis-chiado.blockscout.com |
| Official Faucet | https://faucet.chiadochain.net |
| Faucet API (info) | `https://api.faucet.chiadochain.net/api/v1/info` |
| Gnosis Docs | https://docs.gnosischain.com/about/networks/chiado |
| Subgraph Studio | https://thegraph.com/studio |
| ERC-4337 EntryPoint v0.7 | `0x0000000071727De22E5E9d8BAf0edAc6f37da032` |

### Gas Estimates (from benchmarks)

| Operation | Gas | Cost (at 1 Gwei) |
|-----------|-----|-------------------|
| Deploy EventfulDataEdge | ~2.5M gas | ~0.0025 xDAI |
| Deploy TotalReclawPaymaster | ~1.5M gas | ~0.0015 xDAI |
| Store one fact (Log event) | ~380K gas | ~0.00038 xDAI |

---

## Troubleshooting

### "Deployer has no xDAI"
Fund the deployer address from one of the faucets listed in Step 2.

### "Transaction underpriced"
Chiado uses EIP-1559. Hardhat should handle this automatically. If not, set gas price explicitly:
```typescript
// In hardhat.config.ts chiado network config
gasPrice: 2_000_000_000, // 2 Gwei
```

### Blockscout verification fails
Blockscout may take a few minutes after deployment to index the contract. Wait 2-3 minutes and retry.

### Subgraph not indexing
1. Check that the `network` in subgraph.yaml matches Graph Node's ethereum config
2. Verify the `startBlock` is correct (check `deployed-addresses.json`)
3. Check Graph Node logs: `docker compose logs -f graph-node`

---

## Mainnet Deployment (Gnosis Chain)

When ready for production:

1. Replace `--network chiado` with `--network gnosis`
2. Use real xDAI (purchase from bridge: https://bridge.gnosischain.com)
3. Update `subgraph.yaml` network to `gnosis`
4. Deploy subgraph to The Graph Network (not Studio)
5. Set `GNOSISSCAN_API_KEY` for Gnosisscan verification
