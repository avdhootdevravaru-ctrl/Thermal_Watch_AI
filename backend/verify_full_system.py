"""Comprehensive end-to-end verification script for ThermalWatch AI."""

import json
import urllib.request

def test_url(url, method="GET", data=None):
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        content = resp.read().decode("utf-8")
        try:
            return resp.status, json.loads(content)
        except Exception:
            return resp.status, content

print("=== 1. SYSTEM HEALTH & MODE ===")
s, health = test_url("http://127.0.0.1:8000/health")
print("Health:", health["status"], "| Mode:", health["data_mode"], "| Classifier:", health["classifier_status"])
assert health["data_mode"] == "FIRMS SNAPSHOT"

print("\n=== 2. MODEL HEALTH ===")
s, model = test_url("http://127.0.0.1:8000/health/model")
print("Model:", model["model_type"], "| Version:", model["version"], "| Samples:", model.get("training_samples"))
print("Provenance:", model.get("label_provenance"))
assert model["model_type"] == "IsolationForest"

print("\n=== 3. DATA QUALITY & INGESTION STATS ===")
s, quality = test_url("http://127.0.0.1:8000/history/data-quality")
rec = quality["records_received"]
acc = quality["records_accepted"]
rej = quality["records_rejected"]
print(f"Received: {rec}, Accepted: {acc}, Rejected: {rej}")
print("Database status:", quality.get("database_status"))
assert quality["records_accepted"] == 423

print("\n=== 4. MAP HOTSPOTS ===")
s, hotspots = test_url("http://127.0.0.1:8000/map/hotspots?limit=300")
print("Total markers:", hotspots["total"], "Risk summary:", hotspots["risk_summary"])
assert hotspots["total"] == 288

print("\n=== 5. EVENTS LISTING & ENRICHMENT ===")
s, events = test_url("http://127.0.0.1:8000/thermal-events?page=1&page_size=5")
print("Total events:", events["total"])
e0 = events["items"][0]
print(f"Sample Event #{e0['id']}: {e0['location_name']} | Risk: {e0.get('risk_severity')} ({e0.get('risk_score')}) | Anomaly: {e0.get('anomaly_score')} | Peak FRP: {e0.get('max_frp')}")
assert e0["location_name"] is not None

print("\n=== 6. EVENT DETAIL & ISOLATION FOREST REASONING ===")
s, detail = test_url(f"http://127.0.0.1:8000/thermal-events/{e0['id']}")
c = detail["risk"]["classification"]
print("Event location:", detail.get("location_name"))
print("Classification type:", c["type"])
print("Anomaly score:", c.get("anomaly_score"))
print("Reasoning lines:", len(c.get("reasoning", [])))
for r in c.get("reasoning", [])[:3]:
    print(" -", r)
print("Top contributing features:", len(c.get("top_contributing_features", [])))
for feat in c.get("top_contributing_features", [])[:3]:
    print(" -", feat)

print("\n=== 7. EVIDENCE VERIFICATION & LOCAL CHAIN ===")
s, ev = test_url(f"http://127.0.0.1:8000/evidence/{e0['id']}")
print("Evidence ID:", ev["evidence_id"], "| SHA-256:", ev["sha256"])
print("Integrity status:", ev["integrity"])
assert ev["integrity"]["content_hash_valid"] is True

print("\n=== 8. BLOCKCHAIN STATUS ===")
s, bc = test_url("http://127.0.0.1:8000/blockchain/status")
print("Status:", bc["status"], "| On-chain:", bc["on_chain"], "| Local chain valid:", bc["local_chain"]["valid"], "| Receipts:", bc["local_chain"]["receipt_count"])
assert bc["on_chain"] is False

print("\n=== 9. FRONTEND PROXY ENDPOINTS ===")
for ep in ["/api/health", "/api/map/hotspots", "/api/thermal-events", f"/api/evidence/{e0['id']}"]:
    s, d = test_url(f"http://localhost:3000{ep}")
    assert s == 200
print("All proxy endpoints verified successfully (200 OK)!")

print("\n=== 10. FRONTEND PAGES ===")
for path in ["/", "/events", f"/events/{e0['id']}", "/analytics", "/model", "/evidence"]:
    s, content = test_url(f"http://localhost:3000{path}")
    assert s == 200
print("All frontend routes verified successfully (200 OK)!")

print("\n==========================================")
print(">>> ALL VERIFICATION CHECKS PASSED (10/10) <<<")
print("==========================================")
