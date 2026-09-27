"""Deterministic event evidence and an explicitly local, verifiable hash chain."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.config import settings

_lock = Lock()


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str,
                      allow_nan=False).encode("utf-8")


def _hash(value: dict) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def evidence_package(event: dict) -> dict:
    observations = [{
        "timestamp": observation.timestamp.isoformat(),
        "latitude": observation.latitude, "longitude": observation.longitude,
        "brightness_kelvin": observation.intensity,
        "confidence": observation.confidence, "source": observation.source,
        "sensor": observation.sensor, "raw_fields": observation.metadata_json,
    } for observation in event["observations"]]
    for item in observations:
        item["source_observation_id"] = _hash({key: item[key] for key in ("source", "timestamp", "latitude", "longitude", "sensor")})
    observations.sort(key=lambda item: (item["timestamp"], item["latitude"], item["longitude"], _hash(item)))
    payload = {
        "schema_version": "thermalwatch-evidence-v2", "event_id": event["id"],
        "centroid": {"latitude": event.get("latitude"), "longitude": event.get("longitude")},
        "features": event["classification"].get("features", {}),
        "data_mode": event["data_mode"], "observations": observations,
        "start_time": event["start_time"].isoformat() if hasattr(event["start_time"], "isoformat") else str(event["start_time"]),
        "end_time": event["end_time"].isoformat() if hasattr(event["end_time"], "isoformat") else str(event["end_time"]),
        "persistence": event["persistence"],
        "risk": {key: event["risk"][key] for key in ("score", "severity", "factors", "explanation") if key in event["risk"]},
        "classification": {key: event["classification"].get(key) for key in
                           ("classification", "model_status", "model_version", "anomaly_score", "methodology")},
    }
    if event.get("data_mode") != "DEMO DATA":
        from app.ml.weak_classifier import predict_weak
        try:
            weak = predict_weak(event["id"], event["observations"],
                                anomaly_score=event["classification"].get("anomaly_score"))
            payload["weak_classification"] = {
                key: weak[key] for key in ("prediction", "model_status", "model_version",
                                           "uncalibrated_model_scores", "feature_values",
                                           "top_contributing_features", "model_provenance")
            }
        except (LookupError, ValueError):
            payload["weak_classification"] = {"status": "UNAVAILABLE"}
    digest = _hash(payload)
    return {"evidence_id": f"TW-{digest[:16].upper()}", "sha256": digest,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": sorted({item["source"] for item in observations}),
            "observation_count": len(observations), "event_id": event["id"],
            "hash_algorithm": "SHA-256", "payload": payload,
            "verification_scope": "Current local event content", "on_chain": False}


def _chain_path() -> Path:
    base = Path(settings.FIRMS_SNAPSHOT_PATH) if settings.FIRMS_SNAPSHOT_PATH else Path("data/demo_evidence.jsonl")
    return base.with_name("evidence_local_chain.jsonl")


def _receipts() -> list[dict]:
    path = _chain_path()
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def verify_chain() -> dict:
    try:
        receipts = _receipts()
        previous = "0" * 64
        for index, receipt in enumerate(receipts):
            fields = {key: receipt[key] for key in ("sequence", "event_id", "evidence_id", "evidence_sha256", "previous_sha256", "anchored_at")}
            if receipt["sequence"] != index + 1 or receipt["previous_sha256"] != previous or receipt["chain_sha256"] != _hash(fields):
                return {"valid": False, "receipt_count": len(receipts), "error": f"Local receipt {index + 1} failed verification"}
            previous = receipt["chain_sha256"]
        checkpoint = _chain_path().with_suffix(".head.json")
        if checkpoint.is_file():
            head = json.loads(checkpoint.read_text(encoding="utf-8"))
            if head != {"receipt_count": len(receipts), "latest_chain_sha256": previous}:
                return {"valid": False, "receipt_count": len(receipts), "error": "Local chain head mismatch: possible truncation or incomplete write", "on_chain": False}
        return {"valid": True, "receipt_count": len(receipts), "latest_chain_sha256": previous,
                "checkpoint_present": checkpoint.is_file(),
                "scope": "Local file hash chain; local checkpoint detects truncation but is not an external trust anchor", "on_chain": False}
    except (OSError, KeyError, ValueError, TypeError):
        return {"valid": False, "receipt_count": 0, "error": "Local chain could not be read or verified", "on_chain": False}


def anchor_local(package: dict) -> dict:
    with _lock:
        if _hash(package["payload"]) != package["sha256"] or package["evidence_id"] != f"TW-{package['sha256'][:16].upper()}":
            raise ValueError("Evidence content does not match its digest")
        status = verify_chain()
        if not status["valid"]:
            raise ValueError("Existing local chain is invalid")
        receipts = _receipts()
        for receipt in receipts:
            if receipt["evidence_id"] == package["evidence_id"]:
                _save_head(status)
                return receipt
        fields = {"sequence": len(receipts) + 1, "event_id": package["event_id"],
                  "evidence_id": package["evidence_id"],
                  "evidence_sha256": package["sha256"],
                  "previous_sha256": status["latest_chain_sha256"],
                  "anchored_at": datetime.now(timezone.utc).isoformat()}
        receipt = {**fields, "chain_sha256": _hash(fields), "on_chain": False,
                   "anchor_type": "LOCAL_FILE_ONLY"}
        path = _chain_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(receipt, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        _save_head({"receipt_count": len(receipts) + 1, "latest_chain_sha256": receipt["chain_sha256"]})
        return receipt


def _save_head(status: dict) -> None:
    path = _chain_path().with_suffix(".head.json")
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({key: status[key] for key in ("receipt_count", "latest_chain_sha256")}), encoding="utf-8")
    temporary.replace(path)


def anchor_blockchain(package: dict) -> dict:
    """Anchor an evidence package hash to the configured EVM testnet."""
    from app.blockchain import anchor_evidence_on_chain
    return anchor_evidence_on_chain(int(package["event_id"]), package)


def verify_evidence(package: dict) -> dict:
    digest_matches = _hash(package["payload"]) == package["sha256"]
    chain = verify_chain()
    receipt = next((item for item in reversed(_receipts()) if item["event_id"] == package["event_id"]), None) if chain["valid"] else None
    receipt_matches = receipt is not None and receipt["evidence_sha256"] == package["sha256"]

    # Check on-chain verification
    from app.blockchain import verify_evidence_on_chain, get_blockchain_status
    bc_status = get_blockchain_status()
    on_chain_info = verify_evidence_on_chain(package["sha256"])

    is_on_chain = digest_matches and on_chain_info.get("on_chain_verified", False)
    if not digest_matches:
        note = "Evidence content does not match its SHA-256 digest. Verification failed."
    elif is_on_chain:
        note = f"Verified on-chain on {on_chain_info.get('network', 'testnet')} at block {on_chain_info.get('block_number')}."
    elif bc_status.get("configured") and bc_status.get("status") == "CONNECTED":
        note = "Evidence package hash is valid locally; not yet submitted to the testnet contract."
    else:
        note = "Blockchain unavailable — local evidence verification active."

    return {
        "evidence_id": package["evidence_id"],
        "content_hash_valid": digest_matches,
        "local_anchor_present": receipt is not None,
        "local_anchor_valid": bool(digest_matches and receipt_matches and chain["valid"]),
        "local_chain_valid": chain["valid"],
        "local_receipt": receipt,
        "local_chain": chain,
        "on_chain": is_on_chain,
        "blockchain": {
            "status": bc_status.get("status"),
            "network": bc_status.get("network"),
            "contract_address": bc_status.get("contract_address"),
            "tx_hash": on_chain_info.get("transaction_hash"),
            "block_number": on_chain_info.get("block_number"),
            "explorer_link": on_chain_info.get("explorer_url"),
            "anchored_at": on_chain_info.get("anchored_at"),
        },
        "note": note,
    }

