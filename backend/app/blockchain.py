"""EVM Testnet blockchain anchoring service for ThermalWatch AI / IGNIS.

Interacts with the EvidenceRegistry smart contract on Ethereum Sepolia.
Preserves local SHA-256 evidence verification while enabling verifiable on-chain anchoring.
Private keys and RPC secrets remain strictly in backend environment variables.
Never fabricates transaction hashes, block numbers, or contract confirmations.
"""

from __future__ import annotations

import json
import re
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_blockchain_lock = Lock()

# ABI for EvidenceRegistry contract
EVIDENCE_REGISTRY_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "evidenceHash", "type": "bytes32"}
        ],
        "name": "anchorEvidence",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "evidenceHash", "type": "bytes32"}
        ],
        "name": "isAnchored",
        "outputs": [
            {"internalType": "bool", "name": "", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "evidenceHash", "type": "bytes32"}
        ],
        "name": "anchoredAt",
        "outputs": [
            {"internalType": "uint256", "name": "", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "evidenceHash", "type": "bytes32"}
        ],
        "name": "getAnchor",
        "outputs": [
            {"internalType": "bool", "name": "exists", "type": "bool"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"internalType": "address", "name": "submitter", "type": "address"},
            {"internalType": "uint256", "name": "blockNumber", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "totalAnchored",
        "outputs": [
            {"internalType": "uint256", "name": "", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "bytes32", "name": "evidenceHash", "type": "bytes32"},
            {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "submitter", "type": "address"}
        ],
        "name": "EvidenceAnchored",
        "type": "event"
    }
]


def _blockchain_receipts_path() -> Path:
    base = Path(settings.FIRMS_SNAPSHOT_PATH) if settings.FIRMS_SNAPSHOT_PATH else Path("data/demo_evidence.jsonl")
    return base.with_name("evidence_blockchain_chain.jsonl")


def _get_blockchain_receipts() -> list[dict[str, Any]]:
    path = _blockchain_receipts_path()
    if not path.is_file():
        return []
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception as e:
        logger.warning("Could not read blockchain receipts: %s", e)
        return []


def _save_blockchain_receipt(receipt: dict[str, Any]) -> None:
    path = _blockchain_receipts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, sort_keys=True) + "\n")


def get_wallet_address() -> Optional[str]:
    """Safely derive public address from private key without exposing private key."""
    if not settings.BLOCKCHAIN_PRIVATE_KEY:
        return None
    try:
        from eth_account import Account
        acct = Account.from_key(settings.BLOCKCHAIN_PRIVATE_KEY)
        return acct.address
    except Exception as e:
        logger.warning("Invalid private key configured (%s)", type(e).__name__)
        return None


def get_web3_client():
    """Create a Web3 client instance with timeout."""
    if not settings.BLOCKCHAIN_RPC_URL:
        return None
    try:
        from web3 import Web3
        return Web3(Web3.HTTPProvider(settings.BLOCKCHAIN_RPC_URL, request_kwargs={"timeout": 15}))
    except Exception as e:
        logger.warning("Could not initialize Web3 client (%s)", type(e).__name__)
        return None


def get_blockchain_status() -> dict[str, Any]:
    """Return truthful information about blockchain configuration, connectivity, and receipts."""
    receipts = _get_blockchain_receipts()
    wallet_addr = get_wallet_address()
    latest_receipt = receipts[-1] if receipts else None

    # Base unconfigured response
    if not settings.BLOCKCHAIN_ENABLED:
        return {
            "configured": False,
            "connected": False,
            "status": "NOT_CONFIGURED",
            "network": settings.BLOCKCHAIN_NETWORK.capitalize() if settings.BLOCKCHAIN_NETWORK else "Sepolia",
            "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
            "wallet_address": wallet_addr,
            "contract_address": settings.BLOCKCHAIN_CONTRACT_ADDRESS or None,
            "anchored_receipts": len(receipts),
            "latest_transaction": latest_receipt.get("transaction_hash") if latest_receipt else None,
            "explorer_tx_url": settings.BLOCKCHAIN_EXPLORER_TX_URL,
            "explorer_address_url": settings.BLOCKCHAIN_EXPLORER_ADDRESS_URL,
            "note": "Blockchain disabled — local evidence verification active.",
        }

    # Configured check
    if not settings.BLOCKCHAIN_RPC_URL or not settings.BLOCKCHAIN_CONTRACT_ADDRESS or not wallet_addr:
        return {
            "configured": False,
            "connected": False,
            "status": "INCOMPLETE_CONFIG",
            "network": settings.BLOCKCHAIN_NETWORK.capitalize() if settings.BLOCKCHAIN_NETWORK else "Sepolia",
            "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
            "wallet_address": wallet_addr,
            "contract_address": settings.BLOCKCHAIN_CONTRACT_ADDRESS or None,
            "anchored_receipts": len(receipts),
            "latest_transaction": latest_receipt.get("transaction_hash") if latest_receipt else None,
            "explorer_tx_url": settings.BLOCKCHAIN_EXPLORER_TX_URL,
            "explorer_address_url": settings.BLOCKCHAIN_EXPLORER_ADDRESS_URL,
            "note": "Blockchain configuration incomplete (missing RPC, contract, or key) — local evidence verification active.",
        }

    # Attempt connection
    try:
        w3 = get_web3_client()
        if not w3 or not w3.is_connected():
            return {
                "configured": True,
                "connected": False,
                "status": "RPC_UNAVAILABLE",
                "network": settings.BLOCKCHAIN_NETWORK.capitalize(),
                "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
                "wallet_address": wallet_addr,
                "contract_address": settings.BLOCKCHAIN_CONTRACT_ADDRESS,
                "anchored_receipts": len(receipts),
                "latest_transaction": latest_receipt.get("transaction_hash") if latest_receipt else None,
                "explorer_tx_url": settings.BLOCKCHAIN_EXPLORER_TX_URL,
                "explorer_address_url": settings.BLOCKCHAIN_EXPLORER_ADDRESS_URL,
                "note": "Blockchain RPC unreachable — local evidence verification active.",
            }

        # Check chain ID
        remote_chain_id = w3.eth.chain_id
        if remote_chain_id != settings.BLOCKCHAIN_CHAIN_ID:
            return {
                "configured": True,
                "connected": False,
                "status": "WRONG_CHAIN_ID",
                "network": settings.BLOCKCHAIN_NETWORK.capitalize(),
                "chain_id": remote_chain_id,
                "expected_chain_id": settings.BLOCKCHAIN_CHAIN_ID,
                "wallet_address": wallet_addr,
                "contract_address": settings.BLOCKCHAIN_CONTRACT_ADDRESS,
                "anchored_receipts": len(receipts),
                "latest_transaction": latest_receipt.get("transaction_hash") if latest_receipt else None,
                "explorer_tx_url": settings.BLOCKCHAIN_EXPLORER_TX_URL,
                "explorer_address_url": settings.BLOCKCHAIN_EXPLORER_ADDRESS_URL,
                "note": f"Connected to RPC with chain ID {remote_chain_id}, expected {settings.BLOCKCHAIN_CHAIN_ID}.",
            }

        # Verify contract has deployed bytecode
        checksum_contract = w3.to_checksum_address(settings.BLOCKCHAIN_CONTRACT_ADDRESS)
        code = w3.eth.get_code(checksum_contract)
        if not code or code == b"" or code == b"\x00":
            return {
                "configured": True,
                "connected": False,
                "status": "INVALID_CONTRACT",
                "network": settings.BLOCKCHAIN_NETWORK.capitalize(),
                "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
                "wallet_address": wallet_addr,
                "contract_address": settings.BLOCKCHAIN_CONTRACT_ADDRESS,
                "anchored_receipts": len(receipts),
                "latest_transaction": latest_receipt.get("transaction_hash") if latest_receipt else None,
                "explorer_tx_url": settings.BLOCKCHAIN_EXPLORER_TX_URL,
                "explorer_address_url": settings.BLOCKCHAIN_EXPLORER_ADDRESS_URL,
                "note": "Contract address has no deployed bytecode on testnet.",
            }

        # All four conditions satisfied
        contract = w3.eth.contract(address=checksum_contract, abi=EVIDENCE_REGISTRY_ABI)
        total_on_chain = None
        try:
            total_on_chain = contract.functions.totalAnchored().call()
        except Exception:
            pass

        return {
            "configured": True,
            "connected": True,
            "status": "CONNECTED",
            "network": settings.BLOCKCHAIN_NETWORK.capitalize(),
            "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
            "wallet_address": wallet_addr,
            "contract_address": settings.BLOCKCHAIN_CONTRACT_ADDRESS,
            "anchored_receipts": len(receipts),
            "total_on_chain": total_on_chain,
            "current_block": w3.eth.block_number,
            "latest_transaction": latest_receipt.get("transaction_hash") if latest_receipt else None,
            "explorer_tx_url": settings.BLOCKCHAIN_EXPLORER_TX_URL,
            "explorer_address_url": settings.BLOCKCHAIN_EXPLORER_ADDRESS_URL,
            "note": f"Connected to {settings.BLOCKCHAIN_NETWORK.capitalize()} testnet. Contract verified.",
        }
    except Exception as e:
        logger.warning("Blockchain status query error (%s)", type(e).__name__)
        return {
            "configured": True,
            "connected": False,
            "status": "RPC_UNAVAILABLE",
            "network": settings.BLOCKCHAIN_NETWORK.capitalize(),
            "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
            "wallet_address": wallet_addr,
            "contract_address": settings.BLOCKCHAIN_CONTRACT_ADDRESS,
            "anchored_receipts": len(receipts),
            "latest_transaction": latest_receipt.get("transaction_hash") if latest_receipt else None,
            "explorer_tx_url": settings.BLOCKCHAIN_EXPLORER_TX_URL,
            "explorer_address_url": settings.BLOCKCHAIN_EXPLORER_ADDRESS_URL,
            "error": "Blockchain RPC check failed",
            "note": "Blockchain unavailable — local evidence verification active.",
        }


def anchor_evidence_on_chain(event_id: int, package: dict[str, Any]) -> dict[str, Any]:
    """Anchor an evidence package's SHA-256 hash to the EvidenceRegistry smart contract."""
    status = get_blockchain_status()
    if not status["configured"]:
        raise ValueError("Blockchain is not configured in backend environment.")
    if not status["connected"]:
        raise ConnectionError(f"Blockchain unavailable: {status.get('note')}")

    evidence_hash = package["sha256"]
    evidence_id = package["evidence_id"]

    if not re.fullmatch(r"[0-9a-fA-F]{64}", evidence_hash):
        raise ValueError("Evidence hash must be a SHA-256 digest")
    if package.get("payload") is not None:
        from app.evidence import _hash
        if _hash(package["payload"]) != evidence_hash:
            raise ValueError("Evidence content hash does not match")

    with _blockchain_lock:
        w3 = get_web3_client()
        if not w3 or not w3.is_connected():
            raise ConnectionError("Blockchain RPC connection lost.")

        wallet_addr = get_wallet_address()
        checksum_contract = w3.to_checksum_address(settings.BLOCKCHAIN_CONTRACT_ADDRESS)
        contract = w3.eth.contract(address=checksum_contract, abi=EVIDENCE_REGISTRY_ABI)

        hash_bytes = bytes.fromhex(evidence_hash.replace("0x", ""))

        # Check if already anchored on contract
        is_anchored = contract.functions.isAnchored(hash_bytes).call()
        if is_anchored:
            anchor_info = contract.functions.getAnchor(hash_bytes).call()
            receipt = {
                "event_id": event_id,
                "evidence_id": evidence_id,
                "evidence_hash": evidence_hash,
                "transaction_hash": None,
                "block_number": anchor_info[3] if len(anchor_info) > 3 else None,
                "anchored_at": datetime.fromtimestamp(anchor_info[1], tz=timezone.utc).isoformat() if len(anchor_info) > 1 and anchor_info[1] > 0 else datetime.now(timezone.utc).isoformat(),
                "submitter": anchor_info[2] if len(anchor_info) > 2 else wallet_addr,
                "network": settings.BLOCKCHAIN_NETWORK.capitalize(),
                "contract_address": settings.BLOCKCHAIN_CONTRACT_ADDRESS,
                "explorer_url": f"{settings.BLOCKCHAIN_EXPLORER_ADDRESS_URL}{settings.BLOCKCHAIN_CONTRACT_ADDRESS}",
                "locally_verified": True,
                "on_chain_verified": True,
                "note": "Evidence hash was previously anchored in contract.",
            }
            _save_blockchain_receipt(receipt)
            return receipt

        # Build and sign transaction
        nonce = w3.eth.get_transaction_count(wallet_addr, "pending")
        gas_price = w3.eth.gas_price

        tx = contract.functions.anchorEvidence(hash_bytes).build_transaction({
            "from": wallet_addr,
            "nonce": nonce,
            "gasPrice": int(gas_price * 1.25),
            "chainId": settings.BLOCKCHAIN_CHAIN_ID,
        })

        try:
            tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.2)
        except Exception:
            tx["gas"] = 100000

        signed = w3.eth.account.sign_transaction(tx, private_key=settings.BLOCKCHAIN_PRIVATE_KEY)

        # Broadcast
        tx_hash_bytes = w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = tx_hash_bytes.hex()
        if not tx_hash_hex.startswith("0x"):
            tx_hash_hex = f"0x{tx_hash_hex}"

        # Wait for confirmation receipt
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=90)
        if tx_receipt.get("status") != 1:
            raise ValueError("Blockchain transaction reverted; evidence was not anchored")
        if not contract.functions.isAnchored(hash_bytes).call():
            raise ValueError("Mined transaction did not establish the evidence anchor")
        block_number = tx_receipt["blockNumber"]

        block = w3.eth.get_block(block_number)
        block_ts = block.get("timestamp", int(datetime.now(timezone.utc).timestamp()))
        anchored_at = datetime.fromtimestamp(block_ts, tz=timezone.utc).isoformat()

        receipt = {
            "event_id": event_id,
            "evidence_id": evidence_id,
            "evidence_hash": evidence_hash,
            "transaction_hash": tx_hash_hex,
            "block_number": block_number,
            "anchored_at": anchored_at,
            "submitter": wallet_addr,
            "network": settings.BLOCKCHAIN_NETWORK.capitalize(),
            "contract_address": settings.BLOCKCHAIN_CONTRACT_ADDRESS,
            "explorer_url": f"{settings.BLOCKCHAIN_EXPLORER_TX_URL}{tx_hash_hex}",
            "gas_used": tx_receipt.get("gasUsed"),
            "locally_verified": True,
            "on_chain_verified": True,
            "note": f"Confirmed on {settings.BLOCKCHAIN_NETWORK.capitalize()} testnet at block {block_number}.",
        }

        _save_blockchain_receipt(receipt)
        return receipt


def verify_evidence_on_chain(evidence_hash: str) -> dict[str, Any]:
    """Verify an evidence SHA-256 hash on-chain and against local receipts."""
    clean_hash = evidence_hash.removeprefix("0x").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", clean_hash):
        raise ValueError("Evidence hash must be a SHA-256 digest")
    cached = next(
        (r for r in _get_blockchain_receipts() if (r.get("evidence_hash") or r.get("evidence_sha256", "")).lower() == clean_hash and r.get("contract_address", "").lower() == settings.BLOCKCHAIN_CONTRACT_ADDRESS.lower() and r.get("network", "").lower() == settings.BLOCKCHAIN_NETWORK.lower()),
        None
    )

    status = get_blockchain_status()
    network_name = settings.BLOCKCHAIN_NETWORK.capitalize() if settings.BLOCKCHAIN_NETWORK else "Sepolia"

    # If blockchain is unconfigured or disconnected, report truthful local fallback
    if not status["configured"] or not status["connected"]:
        return {
            "hash": clean_hash,
            "locally_verified": False,
            "on_chain_verified": False,
            "transaction_hash": None,
            "contract_address": settings.BLOCKCHAIN_CONTRACT_ADDRESS or None,
            "network": network_name,
            "explorer_url": None,
            "note": status.get("note", "Blockchain unavailable — local evidence verification active."),
        }

    try:
        w3 = get_web3_client()
        assert w3 and w3.is_connected()
        checksum_contract = w3.to_checksum_address(settings.BLOCKCHAIN_CONTRACT_ADDRESS)
        contract = w3.eth.contract(address=checksum_contract, abi=EVIDENCE_REGISTRY_ABI)

        hash_bytes = bytes.fromhex(clean_hash)
        is_anchored = contract.functions.isAnchored(hash_bytes).call()

        if not is_anchored:
            return {
                "hash": clean_hash,
                "locally_verified": False,
                "on_chain_verified": False,
                "transaction_hash": None,
                "contract_address": settings.BLOCKCHAIN_CONTRACT_ADDRESS,
                "network": network_name,
                "explorer_url": None,
                "note": "Hash is not anchored in the smart contract.",
            }

        anchor_info = contract.functions.getAnchor(hash_bytes).call()
        tx_hash = cached.get("transaction_hash") if cached else None
        explorer_url = f"{settings.BLOCKCHAIN_EXPLORER_TX_URL}{tx_hash}" if tx_hash else f"{settings.BLOCKCHAIN_EXPLORER_ADDRESS_URL}{settings.BLOCKCHAIN_CONTRACT_ADDRESS}"

        return {
            "hash": clean_hash,
            "locally_verified": False,
            "on_chain_verified": True,
            "transaction_hash": tx_hash,
            "contract_address": settings.BLOCKCHAIN_CONTRACT_ADDRESS,
            "network": network_name,
            "explorer_url": explorer_url,
            "block_number": anchor_info[3] if len(anchor_info) > 3 else (cached.get("block_number") if cached else None),
            "timestamp": anchor_info[1] if len(anchor_info) > 1 else None,
            "submitter": anchor_info[2] if len(anchor_info) > 2 else None,
            "note": f"Verified on {network_name} testnet contract.",
        }
    except Exception as e:
        logger.warning("On-chain verification query failed (%s)", type(e).__name__)
        return {
            "hash": clean_hash,
            "locally_verified": False,
            "on_chain_verified": False,
            "transaction_hash": None,
            "contract_address": settings.BLOCKCHAIN_CONTRACT_ADDRESS or None,
            "network": network_name,
            "explorer_url": None,
            "error": "Blockchain RPC verification failed",
            "note": "Blockchain RPC error during verification — local evidence verification active.",
        }
