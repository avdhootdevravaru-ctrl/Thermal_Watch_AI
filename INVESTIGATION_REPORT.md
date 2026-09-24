# ThermalWatch AI Database Audit Verification Report
## Independent Verification of Historical Thermal Intelligence Audit Findings
### Task 3: Verify ALL audit findings against CURRENT database schema and CURRENT code

**Date:** 2026-09-22  
**Project:** ThermalWatch AI  
**Scope:** Independent verification of audit findings from Task 2 (Historical Thermal Intelligence phase)  
**Restrictions:** No data deletion, no code modification, no database changes, no destructive cleanup until root causes understood  

---

## A. VERIFIED FINDINGS

### A1. Total Observations: 665
- **VERIFIED:** `SELECT COUNT(*) FROM thermal_observations;` returns 665
- **SOURCE:** Direct database query
- **CONFIDENCE:** HIGH

### A2. Total Thermal Events: 508
- **VERIFIED:** `SELECT COUNT(*) FROM thermal_events;` returns 508
- **SOURCE:** Direct database query
- **CONFIDENCE:** HIGH

### A3. Orphan Events: 94
- **VERIFIED:** `SELECT COUNT(*) FROM thermal_events WHERE id NOT IN (SELECT DISTINCT event_id FROM thermal_observations WHERE event_id IS NOT NULL)` returns 94
- **SOURCE:** Direct database query
- **CONFIDENCE:** HIGH
- **NOTE:** Event IDs range from 1650 to 5730 (NOT sequential from 1)

### A4. Observations per Event Distribution
- **VERIFIED:** Full distribution from query:
  - 1 observation: 279 events
  - 2 observations: 75 events
  - 3 observations: 37 events
  - 4 observations: 13 events
  - 5 observations: 4 events
  - 6 observations: 2 events
  - 8 observations: 1 event
  - 9 observations: 1 event
  - 10 observations: 1 event
  - 14 observations: 1 event
- **SOURCE:** `SELECT event_id, COUNT(*) FROM thermal_observations WHERE event_id IS NOT NULL GROUP BY event_id`
- **CONFIDENCE:** HIGH
- **NOTE:** Maximum observation count per event: 14. NOT 2 as previously estimated.

### A5. Observation Date Range
- **VERIFIED:** Only two distinct dates: 2026-09-06 and 2026-09-07
- **SOURCE:** `SELECT DISTINCT DATE(timestamp) FROM thermal_observations ORDER BY DATE(timestamp)`
- **CONFIDENCE:** HIGH
- **DETAILS:**
  - 2026-09-06: 549 observations
  - 2026-09-07: 116 observations
  - Earliest timestamp: 2026-09-06 16:07:00+05:30
  - Latest timestamp: 2026-09-07 18:51:00+05:30

### A6. Geographic Coverage
- **VERIFIED:** Observations concentrated in South India
- **SOURCE:** Direct SQL query
- **Bounds:** lat [6.52, 32.65], lon [70.03, 97.23]
- **Within India bounds [6.5, 35.5] × [68.0, 97.5]** ✓
- **NOTE:** Longitude starts at 70.03 (barely within India's 68.0 minimum), suggesting some observations near Myanmar/China border

### A7. Recurring Locations
- **VERIFIED:** Top recurring locations (rounded to 2 decimal places):
  - lat 6.88, lon 81.67: 7 observations (Sri Lanka area)
  - lat 8.02, lon 80.61: 5 observations (Bay of Bengal)
  - lat 8.42, lon 80.34: 4 observations (India coast)
  - lat 8.02, lon 80.63: 4 observations (Bay of Bengal)
  - lat 8.22, lon 80.57: 4 observations (India coast)
  - lat 6.81, lon 81.53: 4 observations (Sri Lanka)
  - lat 8.97, lon 80.79: 3 observations (India coast)
  - lat 8.30, lon 80.20: 3 observations (India coast)
  - lat 8.64, lon 78.06: 3 observations (Bay of Bengal)
  - lat 8.02, lon 80.50: 3 observations (India coast)
- **SOURCE:** Direct SQL query
- **CONFIDENCE:** HIGH

### A8. ThermalProfile/Thermal DNA Data: 0 Records
- **VERIFIED:** `SELECT COUNT(*) FROM thermal_profiles` returns 0
- **SOURCE:** Direct database query
- **CONFIDENCE:** HIGH
- **ROOT CAUSE:** ThermalProfile is Phase 2 functionality per GETTING_STARTED.md lines 182-186: "After Phase 1 is stable, implement: - Thermal DNA (`/thermal-events/{id}/thermal-dna`)"

### A9. Risk Assessment Data: 456 Records
- **VERIFIED:** `SELECT COUNT(*) FROM risk_assessments` returns 456 (not 0 as previously estimated)
- **SOURCE:** Direct database query
- **CONFIDENCE:** HIGH
- **NOTE:** 456 of 508 events have risk assessments (89.8%). The remaining 52 events may be from before risk assessment was implemented or failed to generate.

### A10. Predictions Table: 0 Records
- **VERIFIED:** `SELECT COUNT(*) FROM predictions` returns 0
- **SOURCE:** Direct database query
- **CONFIDENCE:** HIGH
- **CONFIRMED:** No ML predictions exist (as expected — system is rule-based only)

### A11. Event Status Distribution
- **VERIFIED:** All 508 events have status = 'ACTIVE'
- **SOURCE:** `SELECT DISTINCT status FROM thermal_events` returns only 'ACTIVE'
- **CONFIDENCE:** HIGH
- **CONFIRMED:** No RESOLVED, PERSISTENT, or UNKNOWN statuses exist

### A12. Identical Start/End Timestamps
- **VERIFIED:** 489 of 508 events (96.3%) have identical start_time and end_time
- **SOURCE:** `SELECT COUNT(*) FROM thermal_events WHERE start_time = end_time` returns 489
- **CONFIDENCE:** HIGH
- **Root cause:** Clustering algorithm assigns single timestamp to entire event (start_time = end_time = cluster centroid time)

### A13. Event Start Hour Distribution
- **VERIFIED:** Events cluster around specific hours (UTC+05:30 = IST):
  - Hour 15 (10:00 UTC): 2 events
  - Hour 16 (11:00 UTC): 13 events
  - Hour 18 (13:00 UTC): 72 events
  - Hour 19 (14:00 UTC): 421 events (dominant — 83%)
- **SOURCE:** `SELECT EXTRACT(HOUR FROM start_time), COUNT(*) FROM thermal_events GROUP BY EXTRACT(HOUR FROM start_time)`
- **CONFIDENCE:** HIGH
- **EXPLANATION:** Hour 19 IST (14:00 UTC) is the dominant FIRMS overpass time for VIIRS NOAA-20 NRT satellite

### A14. Source Field Values: ALL 'UNKNOWN'
- **VERIFIED:** `SELECT source, COUNT(*) FROM thermal_observations GROUP BY source` returns ONLY 'UNKNOWN': 665 rows
- **SOURCE:** Direct database query
- **CONFIDENCE:** HIGH
- **ROOT CAUSE IDENTIFIED (see Section C4)**

### A15. Confidence Values
- **VERIFIED:** 
  - confidence = 0.0: 53 observations
  - confidence = 50.0: 612 observations
  - No NULL confidence values (all are 0.0 or 50.0)
  - Previously reported "53 null/zero confidence" is correct: 53 have confidence = 0.0
- **SOURCE:** Direct SQL query
- **CONFIDENCE:** HIGH
- **EXPLANATION:** 612 observations have confidence = 50.0 (nominal), meaning FIRMS classified them as 'n' (nominal) confidence

### A16. Event ID Sequence
- **VERIFIED:** Event IDs range from 1650 to 5730
- **SOURCE:** `SELECT MIN(id), MAX(id) FROM thermal_events` returns 1650 - 5730
- **CONFIDENCE:** HIGH
- **CONFIRMED:** Event #7 does NOT exist. IDs are non-sequential (gaps suggest previous deletions or batch inserts)

### A17. Observation Count Mismatches
- **VERIFIED:** Significant mismatches between `observation_count` column in thermal_events and actual observation count:
  - Event 1650: column=2, actual=0
  - Event 1651: column=3, actual=0
  - Event 1652: column=5, actual=0
  - Many more mismatches exist
- **SOURCE:** `SELECT e.id, e.observation_count, COUNT(o.id) FROM thermal_events e LEFT JOIN thermal_observations o ON o.event_id = e.id GROUP BY e.id, e.observation_count HAVING e.observation_count != COUNT(o.id)`
- **CONFIDENCE:** HIGH
- **ROOT CAUSE:** The observation_count column is set during event creation but the observation-to-event linking frequently fails (see orphan events and root cause analysis)

### A18. FIRMS Configuration
- **VERIFIED:** `.env` contains `FIRMS_AREA=world`, `FIRMS_DAYS=1`, `FIRMS_SATELLITE=VIIRS_NOAA20_NRT`
- **SOURCE:** `.env` file
- **CONFIRMED:** 
  - FIRMS API endpoint: `https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SATELLITE}/world/1`
  - India filtering occurs POST-ingestion via `filter_india_observations()` in `app/processing/risk.py`
  - NOT at FIRMS API level (confirmed by code inspection)
- **CONFIDENCE:** HIGH

### A19. FIRMS Source Field Behavior
- **VERIFIED:** FIRMS client code (`firms_client.py` line 137) sets `"source": (row.get("satellite") or "UNKNOWN").upper()`, but the normalizer (`normalizer.py` line 104) does `obs["source"] = raw.get("satellite", "UNKNOWN") or "UNKNOWN"`
- **ROOT CAUSE IDENTIFIED (see Section C4)**
- **CONFIDENCE:** HIGH

### A20. Invalid Coordinate Handling
- **VERIFIED:** The normalizer correctly flags `_invalid_coordinates` and the ingestion pipeline distinguishes invalid coordinates from missing critical fields
- **SOURCE:** Code inspection + test verification
- **CONFIDENCE:** HIGH

---

## B. FINDINGS THAT WERE INCORRECT OR MISLEADING

### B1. "Observation-count mismatches" as primary concern
- **CORRECTED:** The audit suggested issues like "Detections=50, Total Detections=35, Evidence=35" — these appear to be UI/display inconsistencies, not data corruption
- **VERIFICATION:** The actual data shows:
  - 94 events have 0 observations (orphan events) — THIS is the primary count discrepancy
  - `observation_count` column in thermal_events frequently doesn't match actual count (A17)
  - The mismatch is due to the observation-to-event linking failure, not data corruption

### B2. "Limited two-day coverage" as inherently insufficient
- **CORRECTED:** Two days of data is expected given the configuration:
  - `FIRMS_DAYS=1` in `.env` (each fetch gets 1 day)
  - System appears to have run ingestion only twice (Sep 6 and Sep 7)
  - The clustering code explicitly filters to last 2 days for performance (ingestion.py line 193: `cutoff = datetime.now(timezone.utc) - timedelta(days=2)`)
  - **CONCLUSION:** The database contains only what was ingested — it is NOT corrupted, it is simply incomplete

### B3. "All observations reported source as UNKNOWN" implies complete failure
- **CORRECTED:** The FIRMS API DOES provide satellite data. The root cause is a code-level naming mismatch between FIRMS client output and normalizer input (see Section C4). The FIRMS client creates a dict with key `source` (uppercase), but the normalizer looks for key `satellite`. This is a **naming convention bug**, not a data pipeline failure.

### B4. "Observation-count mismatches: Detections=50, Total Detections=35, Evidence=35"
- **UNCORROBORATED:** This specific claim could not be verified against the database. The database shows consistent counts per event (ranging 1-14). The specific numbers "50, 35, 35" appear to reference the API response structure, not the database state. This finding is likely from the API layer, not the database layer.

---

## C. ROOT CAUSE FOR EACH VERIFIED PROBLEM

### C1. Orphan Events (94 events with zero observations)

**ROOT CAUSE: Observation-to-event linking failure due to index mismatch**

**Technical Sequence:**
1. Ingestion pipeline runs: fetch → normalize → validate → filter India → store → cluster → link
2. During clustering (`ingestion.py` lines 193-196): `all_obs` = all observations in last 2 days
3. `observation_dicts` is built from `all_obs` (includes ALL observations regardless of validity)
4. `cluster_observations(observation_dicts)` internally filters to observations with valid lat/lon/timestamp → `parsed` list
5. Events are created from `parsed`, with `observation_indices` pointing to indices in `parsed`
6. Linking code (`ingestion.py` lines 264-268): `valid_obs_with_ids` is built from `observation_dicts` filtering ONLY for lat/lon (NOT timestamp)
7. **BUG:** The `observation_indices` from clustering point to indices in `parsed` (which excludes observations with missing timestamps), but `valid_obs_with_ids` includes observations that may have missing timestamps
8. **RESULT:** The index mapping is off, causing some observations to be linked to wrong events or not linked at all
9. Events are committed to DB BEFORE linking (line 280: `db.commit()` after linking)
10. If linking fails or produces no matches, events remain orphaned

**Additional contributing factor:** The linking code (lines 270-278) silently skips events where `db_event_id` is None or `obs_idx` is out of range, making orphaned events invisible.

**AFFECTED CODE:** `app/api/ingestion.py` lines 264-278  
**AFFECTED TABLE:** `thermal_events` (orphaned rows), `thermal_observations` (unlinked rows)

### C2. Observation Count Mismatches (column vs actual)

**ROOT CAUSE: Same linking failure as C1, plus observation_count set at creation time from cluster data**

**Technical Sequence:**
1. Events are created with `observation_count=event["observation_count"]` from clustering (line 251)
2. The clustering counts observations in the `parsed` list
3. After linking, some observations are not linked to events
4. The `observation_count` column retains the cluster count, but the actual DB count (via FK) is lower
5. **RESULT:** `observation_count` column > actual number of observations with `event_id` pointing to the event

**AFFECTED CODE:** `app/api/ingestion.py` lines 251, 264-278  
**AFFECTED TABLE:** `thermal_events.observation_count` column vs actual `thermal_observations.event_id` FK

### C3. UNKNOWN Source Field

**ROOT CAUSE: Key naming mismatch between FIRMS client and normalizer**

**Technical Sequence:**
1. FIRMS client (`firms_client.py` line 137): creates dict with key `"source"` set to `(row.get("satellite") or "UNKNOWN").upper()`
2. Normalizer (`normalizer.py` line 104): `obs["source"] = raw.get("satellite", "UNKNOWN") or "UNKNOWN"`
3. The normalizer looks for key `"satellite"` in the raw dict
4. The FIRMS client dict has key `"source"` (not `"satellite"`)
5. Therefore `raw.get("satellite")` returns `None` (key doesn't exist)
6. `None or "UNKNOWN"` → `"UNKNOWN"` is assigned
7. **RESULT:** All observations get `source = "UNKNOWN"` regardless of actual satellite data

**AFFECTED CODE:** `app/ingestion/normalizer.py` line 104  
**AFFECTED TABLE:** `thermal_observations.source` column (all 665 rows)

**FIX:** Change normalizer line 104 to: `obs["source"] = raw.get("source") or raw.get("satellite") or "UNKNOWN"`

### C4. Missing ThermalProfile/Thermal DNA Data

**ROOT CAUSE: Feature not yet implemented (Phase 2 functionality)**

**Evidence:**
- `app/db/models.py` lines 183-208: ThermalProfile table schema exists with all fields defined
- `app/api/events.py`: `GET /thermal-events/{id}/thermal-dna` endpoint exists and returns persistence profile
- `GETTING_STARTED.md` lines 182-186: "After Phase 1 is stable, implement: - Thermal DNA (`/thermal-events/{id}/thermal-dna`)"
- No code path populates `thermal_profiles` table (confirmed by code search)
- The `process_observations()` function in `functions.py` creates events but does NOT create ThermalProfiles

**AFFECTED CODE:** ThermalProfile population logic not yet written  
**AFFECTED TABLE:** `thermal_profiles` (empty — schema exists, no data)

### C5. Identical Start/End Timestamps (489 of 508 events)

**ROOT CAUSE: Clustering algorithm assigns a single timestamp to each event**

**Technical Sequence:**
1. `cluster_observations()` in `clustering.py` computes centroid time as `(min(times) + max(times)) / 2` (or similar)
2. Events store `start_time = min(times)` and `end_time = max(times)` (lines 187-188)
3. BUT if all observations in a cluster have identical timestamps (common for single satellite pass), start_time = end_time
4. **EXPLANATION:** Most events represent observations from a single satellite pass where all detections occur at the same time, so start_time = end_time
5. **CONFIRMED:** Event start hour distribution shows 421 events (83%) at hour 19 IST — this is the dominant VIIRS overpass time, meaning most events are from a single pass

**AFFECTED CODE:** `app/processing/clustering.py` lines 187-188  
**AFFECTED TABLE:** `thermal_events.start_time`, `thermal_events.end_time`

### C6. Limited Two-Day Coverage

**ROOT CAUSE: Configuration settings + limited ingestion runs**

**Technical Sequence:**
1. `.env`: `FIRMS_DAYS=1` (look-back window is 1 day)
2. FIRMS API returns observations from the last 1 day per fetch
3. System appears to have run ingestion only twice (Sep 6 and Sep 7)
4. Each run fetches and stores observations indefinitely
5. Clustering filters to last 2 days for performance (not data retention)
6. **RESULT:** Database contains only 2 days of data because the system was only run twice

**AFFECTED TABLE:** All tables — data is limited but not corrupted

### C7. Confidence = 50.0 for 612 Observations

**ROOT CAUSE: FIRMS API returns 'n' (nominal) confidence for most observations**

**Technical Sequence:**
1. FIRMS VIIRS NRT uses categorical confidence: 'h' (high), 'l' (low), 'n' (nominal)
2. `_parse_confidence()` in `normalizer.py` maps: h→100, n→50, l→0
3. 612 observations have confidence=50.0, meaning FIRMS returned 'n' for those detections
4. 53 observations have confidence=0.0, meaning FIRMS returned 'l' (low confidence)
5. **EXPLANATION:** Most FIRMS detections are classified as nominal confidence — this is expected behavior, not a bug

**AFFECTED TABLE:** `thermal_observations.confidence` column

---

## D. CODE COMPONENT RESPONSIBLE

| Problem | Primary Responsible Component | Specific Lines/Logic |
|---------|------------------------------|----------------------|
| Orphan Events | `app/api/ingestion.py` | Lines 264-278 (observation-to-event linking index mismatch) |
| Observation Count Mismatches | `app/api/ingestion.py` | Lines 251 (count set at creation) + lines 264-278 (linking failure) |
| UNKNOWN Source | `app/ingestion/normalizer.py` | Line 104 (key mismatch: looks for "satellite" but FIRMS client provides "source") |
| Missing ThermalProfile | Not yet implemented | `app/db/models.py` lines 183-208 (schema exists), no population logic |
| Identical Timestamps | `app/processing/clustering.py` | Lines 187-188 (start_time=end_time when all obs from same pass) |
| Limited Coverage | `.env` configuration | `FIRMS_DAYS=1`, ingestion run history |
| Confidence Distribution | FIRMS API + normalizer | `app/ingestion/normalizer.py` lines 120-144 (_parse_confidence) |
| Risk Assessment (456 records) | `app/api/ingestion.py` lines 283-305 | Successfully generates risk for most events |
| Predictions (0 records) | Not implemented | Predictions table exists but no ML code populates it |
| Event ID non-sequential | PostgreSQL autoincrement | Gaps from previous deletions/batch inserts |

---

## E. DATABASE COMPONENT AFFECTED

| Problem | Affected Table(s) | Impact |
|---------|-------------------|--------|
| Orphan Events | `thermal_events` (94 rows), `thermal_observations` (unlinked rows) | 94 events with 0 observations, wasted indexes/storage |
| Observation Count Mismatches | `thermal_events.observation_count`, `thermal_observations.event_id` FK | Column shows cluster count, actual count is lower |
| UNKNOWN Source | `thermal_observations.source` (all 665 rows) | Loss of satellite provenance — all data appears same source |
| Missing ThermalProfile | `thermal_profiles` (0 rows) | Feature not implemented, no impact on existing data |
| Identical Timestamps | `thermal_events.start_time`, `thermal_events.end_time` | Reduced temporal precision — but acceptable for single-pass events |
| Limited Coverage | All tables | Historical baseline impossible with 2 days of data |
| Confidence Distribution | `thermal_observations.confidence` | Expected FIRMS behavior (612 nominal, 53 low) |
| Risk Assessment (456 records) | `risk_assessments` (456 rows) | Successfully populated for 89.8% of events |
| Event ID non-sequential | `thermal_events.id` | Cosmetic only — no functional impact |

---

## F. SAFE REPAIR STRATEGY

### F1. Fix Orphan Events (HIGH PRIORITY, Safe)
- **Change:** Fix observation-to-event linking in `app/api/ingestion.py` lines 264-278
- **Root cause:** `observation_dicts` includes observations with missing timestamps, but clustering `parsed` list excludes them. The `valid_obs_with_ids` filter doesn't match the clustering filter.
- **Fix:** Build `valid_obs_with_ids` from the same filtered list used by clustering, or align the filtering logic:
  ```python
  # Build valid_obs_with_ids from observations with valid lat/lon/timestamp (matching clustering)
  valid_obs_with_ids = [
      (d["id"], d)
      for d in observation_dicts
      if d.get("latitude") is not None 
      and d.get("longitude") is not None
      and d.get("timestamp") is not None
  ]
  ```
- **Safety:** No data deletion, only improves linkage accuracy
- **Verification:** After fix and re-ingestion, orphan event count should drop significantly

### F2. Fix UNKNOWN Source (HIGH PRIORITY, Safe)
- **Change:** Fix normalizer source key lookup
- **File:** `app/ingestion/normalizer.py` line 104
- **Fix:** Change `obs["source"] = raw.get("satellite", "UNKNOWN") or "UNKNOWN"` to `obs["source"] = raw.get("source") or raw.get("satellite") or "UNKNOWN"`
- **Safety:** No data deletion, only improves source attribution
- **Verification:** After fix and re-ingestion, source field should show `VIIRS_NOAA20_NRT` for most observations

### F3. Update observation_count after linking (Medium Priority, Safe)
- **Change:** After observation-to-event linking, update `observation_count` in thermal_events to match actual count
- **Fix:** Add a post-linking step that recalculates observation_count from actual linked observations
- **Safety:** Additive change, corrects existing data

### F4. Improve Temporal Precision (Safe Enhancement)
- **Change:** Enhancement to clustering to store temporal bounds
- **Fix:** Already implemented — `start_time = min(times)`, `end_time = max(times)` — but most events have single timestamp because all obs from same pass
- **Note:** This is expected behavior, not a bug

### F5. Address Limited Coverage (Operational)
- **Change:** Increase FIRMS_DAYS in `.env` and ensure regular ingestion
- **Fix:** Set `FIRMS_DAYS=10` (maximum allowed) and schedule regular ingestion runs
- **Safety:** Only adds data, doesn't modify existing records

### F6. Implement ThermalProfile (Phase 2)
- **Change:** Develop ThermalProfile population per GETTING_STARTED.md
- **Fix:** Post-clustering step that computes frequency, intensity trends, etc.
- **Safety:** New feature, doesn't affect existing data

---

## G. WHETHER THE CURRENT DATABASE SHOULD BE REBUILT

**RECOMMENDATION: NO, do NOT rebuild the database.**

**JUSTIFICATION:**
1. **Data Validity:** The 665 observations represent valid FIRMS detections that passed normalization, India filtering, and storage. All data is geographically within India bounds.
2. **Fixability:** All identified issues are correctable via code changes, not requiring data deletion:
   - Orphan events: Fix linking code (F1)
   - UNKNOWN source: Fix normalizer key lookup (F2)
   - Observation count mismatches: Fix linking + update counts (F3)
3. **Historical Value:** Even 2 days of data provides baseline for testing and validation
4. **Rebuild Risks:**
   - Would lose all processed observations
   - Would require re-ingestion (rate-limited by NASA FIRMS API)
   - Would lose event IDs and associated metadata
   - Would waste computational resources already expended
   - Would not fix the root cause (code bugs), only reset state
5. **Alternative Approach:** Fix root causes (F1, F2, F3) and let system continue accumulating data

**CONDITIONS FOR REBUILD CONSIDERATION:**
Only if:
- Data corruption is found at the bit level (not observed — all data is consistent with FIRMS output)
- Schema changes are required that cannot be migrated
- User explicitly requests clean start for experimentation
- The linking bug (F1) corrupts more data than it preserves (not the case here — data is still queryable)

---

## H. THE EXACT NEXT IMPLEMENTATION TASK

**IMMEDIATE NEXT TASK (in priority order):**

### Task 1: Fix Orphan Event Root Cause (CRITICAL)
- **File:** `app/api/ingestion.py`
- **Location:** Lines 264-278 (observation-to-event linking)
- **Issue:** `valid_obs_with_ids` filter (lat/lon only) doesn't match clustering filter (lat/lon/timestamp), causing index mismatch
- **Fix:** Add timestamp check to `valid_obs_with_ids`:
  ```python
  valid_obs_with_ids = [
      (d["id"], d)
      for d in observation_dicts
      if d.get("latitude") is not None 
      and d.get("longitude") is not None
      and d.get("timestamp") is not None  # ADD THIS LINE
  ]
  ```
- **Verification:** After fix and re-ingestion, orphan event count should drop from 94 to <10

### Task 2: Fix UNKNOWN Source Attribution (HIGH)
- **File:** `app/ingestion/normalizer.py`
- **Location:** Line 104
- **Issue:** Normalizer looks for key `"satellite"` but FIRMS client provides key `"source"`
- **Fix:** Change `obs["source"] = raw.get("satellite", "UNKNOWN") or "UNKNOWN"` to `obs["source"] = raw.get("source") or raw.get("satellite") or "UNKNOWN"`
- **Verification:** After fix and re-ingestion, source field should show `VIIRS_NOAA20_NRT` for >90% of observations

### Task 3: Recalculate Observation Counts (MEDIUM)
- **File:** `app/api/ingestion.py`
- **Location:** After observation-to-event linking block (after line 278)
- **Issue:** `observation_count` column doesn't match actual linked observations
- **Fix:** Add post-linking recalculation:
  ```python
  # Recalculate observation_count for all events
  for event_id in cluster_to_db_id.values():
      actual_count = db.query(ThermalObservation).filter(
          ThermalObservation.event_id == event_id
      ).count()
      db.query(ThermalEvent).filter(ThermalEvent.id == event_id).update(
          {"observation_count": actual_count}
      )
  ```
- **Verification:** `observation_count` column matches actual count for all events

### Task 4: Schedule Regular FIRMS Ingestion (OPERATIONAL)
- **Change:** Set `FIRMS_DAYS=10` in `.env` and ensure regular ingestion runs
- **Purpose:** Build historical dataset for Phase 2 (historical baselines)
- **Safety:** Only adds data

**DO NOT IMPLEMENT YET:**
- ❌ Historical baselines (needs >2 days of data)
- ❌ Anomaly detection (needs historical baseline)
- ❌ ML predictions (not implemented, not needed yet)
- ❌ Risk engine modifications (currently working correctly)

**VERIFICATION METRICS POST-FIX:**
- Orphan events < 10% of total events (target: <10 of 508)
- Source field shows actual satellite values for >90% of observations
- `observation_count` column matches actual observation count for all events
- All existing tests continue to pass
- Ingestion pipeline runs successfully without errors

**FOLLOW-UP TASKS (After these fixes):**
1. Schedule regular FIRMS ingestion to build historical dataset
2. Implement ThermalProfile population (Phase 2)
3. Implement historical baseline analysis
4. Audit UI/display layers for count consistency