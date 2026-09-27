"""Deterministic event evidence and an explicitly local, verifiable hash chain."""

from __future__ import annotations

import hashlib
import json
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
    observations.sort(key=lambda item: (item["timestamp"], item["latitude"], item["longitude"]))
    payload = {
        "schema_version": "thermalwatch-evidence-v1", "event_id": event["id"],
        "data_mode": event["data_mode"], "observations": observations,
        "start_time": event["start_time"].isoformat(),
        "end_time": event["end_time"].isoformat(),
        "persistence": event["persistence"],
        "risk": {key: event["risk"][key] for key in ("score", "severity", "factors") if key in event["risk"]},
        "classification": {key: event["classification"].get(key) for key in
                           ("classification", "model_status", "model_version", "anomaly_score", "methodology")},
    }
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
        return {"valid": True, "receipt_count": len(receipts), "latest_chain_sha256": previous,
                "scope": "Local file hash chain", "on_chain": False}
    except (OSError, KeyError, ValueError, TypeError):
        return {"valid": False, "receipt_count": 0, "error": "Local chain could not be read or verified", "on_chain": False}


def anchor_local(package: dict) -> dict:
    with _lock:
        status = verify_chain()
        if not status["valid"]:
            raise ValueError("Existing local chain is invalid")
        receipts = _receipts()
        for receipt in receipts:
            if receipt["evidence_id"] == package["evidence_id"]:
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
        return receipt


def verify_evidence(package: dict) -> dict:
    digest_matches = _hash(package["payload"]) == package["sha256"]
    chain = verify_chain()
    receipt = next((item for item in reversed(_receipts()) if item["event_id"] == package["event_id"]), None) if chain["valid"] else None
    receipt_matches = receipt is not None and receipt["evidence_sha256"] == package["sha256"]
    return {"evidence_id": package["evidence_id"], "content_hash_valid": digest_matches,
            "local_anchor_present": receipt is not None, "local_anchor_valid": bool(receipt_matches and chain["valid"]),
            "local_chain_valid": chain["valid"], "on_chain": False,
            "note": "No blockchain transaction is configured; this verifies current content and optional local receipts."}
