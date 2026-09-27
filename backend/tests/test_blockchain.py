"""Comprehensive tests for EVM Testnet blockchain integration and graceful degradation.

Covers:
- blockchain disabled
- RPC unavailable
- wrong chain ID
- missing private key
- invalid contract
- successful anchoring with mocked provider
- duplicate evidence hash
- verification
- local fallback
- API responses (/blockchain/status, /blockchain/anchor/{id}, /blockchain/verify/{hash})
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.evidence import evidence_package, verify_chain, verify_evidence, anchor_blockchain
from app.blockchain import (
    get_blockchain_status,
    get_wallet_address,
    anchor_evidence_on_chain,
    verify_evidence_on_chain,
    EVIDENCE_REGISTRY_ABI,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_blockchain_receipts(tmp_path, monkeypatch):
    """Mocked transactions must never enter the application's receipt registry."""
    monkeypatch.setattr("app.blockchain._blockchain_receipts_path", lambda: tmp_path / "test_chain.jsonl")
    monkeypatch.setattr("app.evidence._chain_path", lambda: tmp_path / "local_chain.jsonl")

DUMMY_KEY = "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7e22d318b205c"
DUMMY_ADDR = "0x90F79bf6EB2c4f870365E785982E1f101E93b906"
DUMMY_CONTRACT = "0x1234567890123456789012345678901234567890"


def sample_event():
    return {
        "id": 59639849,
        "data_mode": "FIRMS SNAPSHOT",
        "start_time": "2026-09-25T09:05:00+00:00",
        "end_time": "2026-09-26T21:14:00+00:00",
        "persistence": {"active_days": 2, "trend": "STABLE", "average_intensity": 315.0},
        "risk": {"score": 59.0, "severity": "HIGH", "factors": ["heat_signature"]},
        "classification": {"classification": "anomalous_thermal_pattern", "model_status": "PROTOTYPE"},
        "observations": []
    }


def test_hash_generation_deterministic():
    """Verify that evidence package hash is deterministic and 64-char SHA-256."""
    e = sample_event()
    p1 = evidence_package(e)
    p2 = evidence_package(e)

    assert p1["sha256"] == p2["sha256"]
    assert len(p1["sha256"]) == 64
    assert p1["evidence_id"] == f"TW-{p1['sha256'][:16].upper()}"


def test_local_chain_verification():
    """Verify a test-owned chain, independent of demo runtime files."""
    from app.evidence import anchor_local
    anchor_local(evidence_package(sample_event()))
    chain = verify_chain()
    assert chain["valid"] is True
    assert chain["receipt_count"] == 1
    assert "latest_chain_sha256" in chain


def test_blockchain_disabled():
    """Verify status when BLOCKCHAIN_ENABLED is false."""
    with patch.object(settings, "BLOCKCHAIN_ENABLED", False):
        status = get_blockchain_status()
        assert status["configured"] is False
        assert status["connected"] is False
        assert status["status"] == "NOT_CONFIGURED"
        assert "local evidence verification active" in status["note"]


def test_missing_private_key():
    """Verify status when enabled but missing private key."""
    with patch.object(settings, "BLOCKCHAIN_ENABLED", True), \
         patch.object(settings, "BLOCKCHAIN_CONTRACT_ADDRESS", DUMMY_CONTRACT), \
         patch.object(settings, "BLOCKCHAIN_PRIVATE_KEY", ""):
        status = get_blockchain_status()
        assert status["configured"] is False
        assert status["connected"] is False
        assert status["wallet_address"] is None


def test_rpc_unavailable():
    """Verify status when RPC is unreachable."""
    with patch.object(settings, "BLOCKCHAIN_ENABLED", True), \
         patch.object(settings, "BLOCKCHAIN_CONTRACT_ADDRESS", DUMMY_CONTRACT), \
         patch.object(settings, "BLOCKCHAIN_PRIVATE_KEY", DUMMY_KEY), \
         patch("app.blockchain.get_web3_client") as mock_client:
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = False
        mock_client.return_value = mock_w3

        status = get_blockchain_status()
        assert status["configured"] is True
        assert status["connected"] is False
        assert status["status"] == "RPC_UNAVAILABLE"


def test_wrong_chain_id():
    """Verify status when connected to unexpected chain ID."""
    with patch.object(settings, "BLOCKCHAIN_ENABLED", True), \
         patch.object(settings, "BLOCKCHAIN_CONTRACT_ADDRESS", DUMMY_CONTRACT), \
         patch.object(settings, "BLOCKCHAIN_PRIVATE_KEY", DUMMY_KEY), \
         patch("app.blockchain.get_web3_client") as mock_client:
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.chain_id = 1  # Ethereum mainnet instead of 11155111 Sepolia
        mock_client.return_value = mock_w3

        status = get_blockchain_status()
        assert status["configured"] is True
        assert status["connected"] is False
        assert status["status"] == "WRONG_CHAIN_ID"
        assert status["chain_id"] == 1


def test_invalid_contract():
    """Verify status when contract address has no deployed bytecode on testnet."""
    with patch.object(settings, "BLOCKCHAIN_ENABLED", True), \
         patch.object(settings, "BLOCKCHAIN_CONTRACT_ADDRESS", DUMMY_CONTRACT), \
         patch.object(settings, "BLOCKCHAIN_PRIVATE_KEY", DUMMY_KEY), \
         patch("app.blockchain.get_web3_client") as mock_client:
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.chain_id = 11155111
        mock_w3.eth.get_code.return_value = b""  # Empty code
        mock_client.return_value = mock_w3

        status = get_blockchain_status()
        assert status["configured"] is True
        assert status["connected"] is False
        assert status["status"] == "INVALID_CONTRACT"


@pytest.mark.parametrize("tx_status, contract_verifies", [(1, True), (0, False), (1, False)])
def test_successful_anchoring_with_mocked_provider(tx_status, contract_verifies):
    """Verify successful transaction submission and receipt parsing with mocked Web3."""
    with patch.object(settings, "BLOCKCHAIN_ENABLED", True), \
         patch.object(settings, "BLOCKCHAIN_CONTRACT_ADDRESS", DUMMY_CONTRACT), \
         patch.object(settings, "BLOCKCHAIN_PRIVATE_KEY", DUMMY_KEY), \
         patch("app.blockchain.get_web3_client") as mock_client:
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.chain_id = 11155111
        mock_w3.eth.get_code.return_value = b"\x60\x80\x60\x40"
        mock_contract = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract
        mock_client.return_value = mock_w3

        # Not already anchored
        mock_contract.functions.isAnchored.return_value.call.side_effect = [False, contract_verifies]
        mock_w3.eth.get_transaction_count.return_value = 5
        mock_w3.eth.gas_price = 20000000000
        mock_contract.functions.anchorEvidence.return_value.build_transaction.return_value = {
            "to": DUMMY_CONTRACT, "data": "0x1234"
        }
        mock_w3.eth.estimate_gas.return_value = 50000

        mock_signed = MagicMock()
        mock_signed.raw_transaction = b"signed_raw_tx"
        mock_w3.eth.account.sign_transaction.return_value = mock_signed

        mock_tx_hash = MagicMock()
        mock_tx_hash.hex.return_value = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        mock_w3.eth.send_raw_transaction.return_value = mock_tx_hash

        mock_w3.eth.wait_for_transaction_receipt.return_value = {
            "status": tx_status,
            "blockNumber": 6709999,
            "gasUsed": 45120
        }
        mock_w3.eth.get_block.return_value = {"timestamp": 1727440000}

        package = {"sha256": "f" * 64, "event_id": 59639849, "evidence_id": "TW-FFFF"}
        if tx_status != 1 or not contract_verifies:
            with pytest.raises(ValueError):
                anchor_evidence_on_chain(59639849, package)
            from app.blockchain import _get_blockchain_receipts
            assert _get_blockchain_receipts() == []
            return
        receipt = anchor_evidence_on_chain(59639849, package)

        assert receipt["event_id"] == 59639849
        assert receipt["block_number"] == 6709999
        assert receipt["transaction_hash"].startswith("0xabcdef")
        assert receipt["on_chain_verified"] is True
        assert "sepolia.etherscan.io/tx/" in receipt["explorer_url"]


def test_duplicate_evidence_hash():
    """Verify that attempting to anchor an already anchored hash returns existing record without throwing."""
    with patch.object(settings, "BLOCKCHAIN_ENABLED", True), \
         patch.object(settings, "BLOCKCHAIN_CONTRACT_ADDRESS", DUMMY_CONTRACT), \
         patch.object(settings, "BLOCKCHAIN_PRIVATE_KEY", DUMMY_KEY), \
         patch("app.blockchain.get_web3_client") as mock_client:
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.chain_id = 11155111
        mock_w3.eth.get_code.return_value = b"\x60\x80\x60\x40"
        mock_contract = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract
        mock_client.return_value = mock_w3

        # Already anchored on contract
        mock_contract.functions.isAnchored.return_value.call.return_value = True
        # getAnchor returns (exists, timestamp, submitter, blockNumber)
        mock_contract.functions.getAnchor.return_value.call.return_value = (
            True, 1727438400, DUMMY_ADDR, 6701234
        )

        package = {"sha256": "e" * 64, "event_id": 59639849, "evidence_id": "TW-EEEE"}
        receipt = anchor_evidence_on_chain(59639849, package)

        assert receipt["on_chain_verified"] is True
        assert receipt["block_number"] == 6701234
        assert "previously anchored" in receipt["note"]


def test_on_chain_verification():
    """Verify get /blockchain/verify/{evidence_hash} responses."""
    test_hash = "abcdef" * 10 + "1234"
    with patch.object(settings, "BLOCKCHAIN_ENABLED", True), \
         patch.object(settings, "BLOCKCHAIN_CONTRACT_ADDRESS", DUMMY_CONTRACT), \
         patch.object(settings, "BLOCKCHAIN_PRIVATE_KEY", DUMMY_KEY), \
         patch("app.blockchain.get_web3_client") as mock_client:
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.chain_id = 11155111
        mock_w3.eth.get_code.return_value = b"\x60\x80\x60\x40"
        mock_contract = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract
        mock_client.return_value = mock_w3

        mock_contract.functions.isAnchored.return_value.call.return_value = True
        mock_contract.functions.getAnchor.return_value.call.return_value = (
            True, 1727438400, DUMMY_ADDR, 6701234
        )

        res = verify_evidence_on_chain(test_hash)
        assert res["on_chain_verified"] is True
        assert res["block_number"] == 6701234
        assert res["network"] == "Sepolia"
        assert res["submitter"] == DUMMY_ADDR


def test_api_blockchain_endpoints():
    """Verify /blockchain/status, /blockchain/anchor/{id}, /blockchain/verify/{hash} API responses."""
    # 1. Status
    res = client.get("/blockchain/status")
    assert res.status_code == 200
    data = res.json()
    assert "configured" in data
    assert "connected" in data
    assert "network" in data
    assert "chain_id" in data
    assert "local_chain" in data
    assert data["local_chain"]["valid"] is True

    # 2. Verify hash
    res_verify = client.get("/blockchain/verify/789d47bf45ba15d647d6fa5c41108faef22f871b5eed1e62be00f0336abbbeae")
    assert res_verify.status_code == 200
    vdata = res_verify.json()
    assert "hash" in vdata
    assert "locally_verified" in vdata
    assert "on_chain_verified" in vdata
    assert client.get("/blockchain/verify/not-a-digest").status_code == 422


def test_cached_receipt_cannot_prove_blockchain_or_content(monkeypatch):
    from app.blockchain import _save_blockchain_receipt
    monkeypatch.setattr(settings, "BLOCKCHAIN_ENABLED", False)
    _save_blockchain_receipt({"evidence_hash": "a" * 64, "on_chain_verified": True,
                            "network": settings.BLOCKCHAIN_NETWORK,
                            "contract_address": settings.BLOCKCHAIN_CONTRACT_ADDRESS})
    result = verify_evidence_on_chain("a" * 64)
    assert result["on_chain_verified"] is False
    assert result["locally_verified"] is False
