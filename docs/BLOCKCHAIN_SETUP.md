# ThermalWatch AI / IGNIS — Blockchain Anchoring & Verification Guide

This document describes the design, deployment, configuration, and verification of the blockchain anchoring layer for **ThermalWatch AI (IGNIS)**.

---

## 1. Overview & Architecture

IGNIS implements a layered evidence architecture for forensic auditability of satellite-detected wildfire intelligence:

```
+-------------------------------------------------------------+
|             NASA FIRMS Raw VIIRS Satellite Feed             |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|    Spatial-Temporal Event Clustering & Thermal Analytics    |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|             Canonical Evidence Package Generator            |
|       (Observations, Clusters, ML Predictions, Risk)       |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|          Cryptographic SHA-256 Digest Computation           |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|    Local Backward-Linked Evidence Ledger (JSONL Audit Chain)|
|          (Immediate, offline-first, deterministic)          |
+-------------------------------------------------------------+
                              |
                     (Optional / Configured)
                              v
+-------------------------------------------------------------+
|         Public EVM Testnet (Ethereum Sepolia, 11155111)      |
|               Contract: EvidenceRegistry.sol                |
|      anchorEvidence(bytes32) -> Emits EvidenceAnchored      |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|           Public Block Explorer (Sepolia Etherscan)          |
|       Immutable, Third-Party Timestamped Proof-of-Record    |
+-------------------------------------------------------------+
```

### Key Principles & Guarantees
- **Zero Fabrication**: Transaction hashes, block numbers, contract addresses, and confirmations are NEVER simulated or mocked in production.
- **Graceful Local Fallback**: When blockchain credentials or RPC are unconfigured or unavailable, the system transparently falls back to the local SHA-256 backward-linked ledger.
- **Offline Signing**: Private keys remain strictly within `backend/.env` on the backend server. The key is never exposed to the frontend or over any API.
- **Deterministic Hashing**: The canonical evidence package is normalized and hashed using `SHA-256`. The exact 32-byte hash (`bytes32`) is submitted to the EVM contract.

---

## 2. Smart Contract: `EvidenceRegistry.sol`

Located at: `backend/contracts/EvidenceRegistry.sol`  
Compiled ABI and Bytecode: `backend/contracts/EvidenceRegistry.json`

### Contract Interface

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract EvidenceRegistry {
    address public immutable owner;

    struct Anchor {
        bool exists;
        uint256 timestamp;
        address submitter;
        uint256 blockNumber;
    }

    mapping(bytes32 => Anchor) private _anchors;
    bytes32[] private _allAnchors;

    event EvidenceAnchored(
        bytes32 indexed evidenceHash,
        address indexed submitter,
        uint256 timestamp,
        uint256 blockNumber
    );

    function anchorEvidence(bytes32 evidenceHash) external returns (bool);
    function isAnchored(bytes32 evidenceHash) external view returns (bool);
    function anchoredAt(bytes32 evidenceHash) external view returns (uint256);
    function getAnchor(bytes32 evidenceHash) external view returns (bool exists, uint256 timestamp, address submitter, uint256 blockNumber);
    function totalAnchors() external view returns (uint256);
}
```

---

## 3. Prerequisites & Setup for Testnet Anchoring

### A. Prerequisites
1. Python 3.11+ environment with `web3>=6.0.0` and `py-solc-x>=2.0.0` installed:
   ```powershell
   cd backend
   .\.venv\Scripts\pip.exe install -r requirements.txt
   ```
2. Ethereum Sepolia RPC URL (e.g., from [Alchemy](https://www.alchemy.com/), [Infura](https://www.infura.io/), or a public RPC endpoint: `https://rpc.sepolia.org` or `https://ethereum-sepolia-rpc.publicnode.com`).
3. An Ethereum testnet wallet with a small amount of Sepolia test ETH (e.g. from Google Cloud Web3 Sepolia Faucet or Infura Sepolia Faucet).

### B. Environment Configuration (`backend/.env`)

Configure the following variables in `backend/.env`:

```dotenv
# Blockchain Anchoring (Ethereum Sepolia Testnet)
BLOCKCHAIN_ENABLED=true
BLOCKCHAIN_RPC_URL=https://rpc.sepolia.org
BLOCKCHAIN_CHAIN_ID=11155111
BLOCKCHAIN_PRIVATE_KEY=0xyour_private_key_here
BLOCKCHAIN_CONTRACT_ADDRESS=0xyour_deployed_contract_address_here
BLOCKCHAIN_EXPLORER_TX_URL=https://sepolia.etherscan.io/tx/{tx_hash}
BLOCKCHAIN_EXPLORER_ADDRESS_URL=https://sepolia.etherscan.io/address/{address}
```

> **Security Note**: Never commit `backend/.env` or share your private key. The `.gitignore` file already excludes `.env`.

---

## 4. Deploying the Smart Contract

A deployment script is provided at `backend/scripts/deploy_anchor_contract.py`.

Run the deployment script:
```powershell
cd C:\Users\tejap\Thermal_Watch_AI\backend
.\.venv\Scripts\python.exe scripts/deploy_anchor_contract.py
```

### Example Deployment Output:
```
======================================================================
IGNIS — EvidenceRegistry Smart Contract Deployment
======================================================================
[1/5] Connected to RPC: https://rpc.sepolia.org (Chain ID: 11155111)
[2/5] Deployer wallet: 0x9B110d29... (Balance: 0.152 ETH)
[3/5] Compiling contracts/EvidenceRegistry.sol via py-solc-x...
      Compiled successfully. Bytecode size: 3680 bytes
[4/5] Submitting deployment transaction...
      Tx Hash: 0x3d41a87...
      Waiting for receipt...
[5/5] Contract deployed successfully!
      Contract Address: 0x4B37a3465bE4f87A6E46961168B52aFa94C5632D
      Block Number: 6712390
      Etherscan: https://sepolia.etherscan.io/address/0x4B37a3465bE4f87A6E46961168B52aFa94C5632D
======================================================================
```

After deployment, copy the contract address into `backend/.env` under `BLOCKCHAIN_CONTRACT_ADDRESS`.

---

## 5. API Endpoints Reference

### 1. `GET /blockchain/status`
Returns truthful status of the blockchain connection, contract address, network, wallet, and anchored count.

**Response (Configured & Connected):**
```json
{
  "configured": true,
  "connected": true,
  "network": "Ethereum Sepolia Testnet",
  "chain_id": 11155111,
  "contract_address": "0x4B37a3465bE4f87A6E46961168B52aFa94C5632D",
  "wallet_address": "0x9B110d29...",
  "balance_eth": 0.152,
  "anchored_receipts": 3,
  "local_chain_valid": true,
  "local_receipt_count": 8,
  "explorer_url": "https://sepolia.etherscan.io/address/0x4B37a3465bE4f87A6E46961168B52aFa94C5632D",
  "note": "Public testnet anchoring is ACTIVE on Ethereum Sepolia."
}
```

**Response (Unconfigured / Disabled):**
```json
{
  "configured": false,
  "connected": false,
  "network": "Ethereum Sepolia Testnet (Chain ID 11155111)",
  "chain_id": 11155111,
  "contract_address": null,
  "wallet_address": null,
  "balance_eth": 0.0,
  "anchored_receipts": 0,
  "local_chain_valid": true,
  "local_receipt_count": 8,
  "explorer_url": null,
  "note": "Blockchain unconfigured — local SHA-256 evidence verification active."
}
```

### 2. `POST /blockchain/anchor/{event_id}`
Generates the canonical evidence package for the specified thermal event, computes its SHA-256 hash, commits it to the local evidence chain, and broadcasts an offline-signed transaction to the `EvidenceRegistry` contract on Sepolia.

**Response:**
```json
{
  "status": "SUCCESS",
  "event_id": "EV-2026-08871",
  "evidence_hash": "8f31b67a...",
  "transaction_hash": "0x7a2f58e...",
  "block_number": 6712415,
  "contract_address": "0x4B37a3465bE4f87A6E46961168B52aFa94C5632D",
  "network": "Ethereum Sepolia Testnet",
  "chain_id": 11155111,
  "explorer_url": "https://sepolia.etherscan.io/tx/0x7a2f58e...",
  "locally_anchored": true,
  "on_chain_anchored": true,
  "note": "Evidence successfully anchored on Ethereum Sepolia."
}
```

### 3. `GET /blockchain/verify/{evidence_hash}`
Verifies an evidence hash against both the local backward-linked chain and the on-chain smart contract `isAnchored()` view method.

**Response:**
```json
{
  "evidence_hash": "8f31b67a...",
  "locally_verified": true,
  "on_chain_verified": true,
  "transaction_hash": "0x7a2f58e...",
  "block_number": 6712415,
  "contract_address": "0x4B37a3465bE4f87A6E46961168B52aFa94C5632D",
  "network": "Ethereum Sepolia Testnet",
  "explorer_url": "https://sepolia.etherscan.io/tx/0x7a2f58e...",
  "timestamp": "2026-09-27T13:45:00Z",
  "status": "VALID_ON_CHAIN"
}
```

---

## 6. How to Demonstrate During SIH Judging

### Step 1: Health & System Status Inspection
1. Navigate to the **Health / System Status** page (`/health`) in the IGNIS Dashboard.
2. Observe the **Evidence & Blockchain** section:
   - When configured, shows **CONNECTED** (Green) with Network: `Ethereum Sepolia Testnet (11155111)`, Contract Address, and link to Etherscan.
   - When not configured, shows **NOT_CONFIGURED** (Muted) with explanation that local cryptographic SHA-256 chain is active.

### Step 2: Anchor an Event On-Chain
1. Open the **Events** page (`/events`) and select an active wildfire cluster (e.g. `EV-2026-08871`).
2. On the **Event Detail** page, view the **Cryptographic Evidence Package** tab.
3. Click the **Anchor to Sepolia Testnet** button.
4. The backend generates the canonical package, calculates `SHA-256`, and signs a transaction with gas estimation.
5. The UI displays the confirmed **Transaction Hash**, **Block Number**, and a direct link to **Sepolia Etherscan**.

### Step 3: Verify via Sepolia Etherscan
1. Click the Etherscan link in the dashboard.
2. The evaluator can see the transaction, the `EvidenceRegistry` contract invocation, and the `EvidenceAnchored` event log containing the matching `evidenceHash`.

### Step 4: Independent Hash Verification
1. Navigate to the **Evidence & Audit** page (`/evidence`).
2. Paste the evidence hash or click **Verify Hash**.
3. The UI queries `/blockchain/verify/{hash}` and confirms dual verification:
   - Local Backward-Linked Ledger: **VALID**
   - Ethereum Sepolia On-Chain: **CONFIRMED**
