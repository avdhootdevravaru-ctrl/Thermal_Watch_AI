# ThermalWatch AI — Project Instructions

## Current Development Phase

We are in **TASK GROUP 1 — HISTORICAL DATA + THERMAL INTELLIGENCE FOUNDATION** for the ThermalWatch AI project (SIH 2026, NTRO).

## Project Overview

ThermalWatch AI is a geospatial intelligence platform that combines NASA FIRMS satellite thermal detections, PostgreSQL/PostGIS, event clustering, and historical analysis to identify persistent thermal sources and provide historical context for industrial fire detection.

## Current State

- **Ingestion integrity phase completed**: 789 observations, 618 thermal events, 0 NEW orphan events, 0 NEW observation_count mismatches
- **Legacy data preserved**: 94 OLD orphan events and 665 historical UNKNOWN sources remain untouched
- **Task Group 1 Phases 1-12 completed**: All phases complete
- **Task Group 1 Phase 12 (Frontend Integration) complete**: Historical intelligence UI in Sidebar, DashboardPage, EventDetailPage
- **Task Group 1 Phase 13 (Documentation) complete**: CLAUDE.md, PROJECT_STATUS.md, GETTING_STARTED.md, README.md
- **Task Group 1 Phase 14 (Final Validation) complete**: Full backend test suite (67/71 passed, 4 pre-existing unrelated failures), frontend type-check and production build pass, comprehensive read-only database verification complete

## Core Concepts (Keep Separate)

1. **Thermal DNA** = What the thermal behavior looks like (frequency, active days, duration, intensity, variance, temporal trend, spatial spread/stability, recurrence/persistence, confidence/source info)
2. **Historical baseline** = What is normal for that location
3. **Baseline deviation** = How current behavior differs from normal

## Current Dataset Limitations

The current dataset has limited historical depth. Do NOT pretend it is sufficient for a statistically meaningful baseline. If insufficient history exists:
- Implement the infrastructure
- Mark the result as INSUFFICIENT_HISTORY
- Do not fabricate data
- Do not fabricate Thermal DNA
- Do not fabricate baselines

## Explicitly OUT OF SCOPE / DO NOT DO

- ML training
- Supervised classification
- ML anomaly detection (Isolation Forest, etc.)
- Replacement of the risk engine
- Synthetic labels/data
- Frontend redesign (only integrate historical intelligence into existing UI)
- Geographic search
- PDF reports
- Database rebuild
- Deleting the 94 legacy orphan events
- Rewriting the 665 historical UNKNOWN sources without evidence

## Task Group 1 Scope

Complete ONLY Task Group 1:
1. Sustained historical FIRMS data collection
2. Historical data-quality monitoring
3. ThermalProfile / Thermal DNA
4. Persistent and recurring thermal-source analysis
5. Historical thermal statistics
6. Location-specific historical baselines
7. Current-vs-historical baseline comparison
8. API integration
9. Tests and validation
10. Documentation
11. Frontend integration
12. Final validation

## Stop Before Task Group 2

After completing Task Group 1, run the full backend test suite and provide a final technical report. STOP before Task Group 2.
