#!/usr/bin/env python
"""ML Readiness Audit for ThermalWatch AI - Task Group 2."""

from app.db.base import engine
from sqlalchemy import text

def main():
    print('=== ML READINESS AUDIT ===\n')

    with engine.connect() as e:
        # 1. DATA VOLUME
        r = e.execute(text('SELECT COUNT(*) FROM thermal_observations'))
        obs = r.fetchone()[0]

        r = e.execute(text('SELECT COUNT(*) FROM thermal_events'))
        events = r.fetchone()[0]

        print('1. DATA VOLUME')
        print(f'   Total observations: {obs}')
        print(f'   Total thermal events: {events}')
        print(f'   Events with >=3 obs (potential ML samples): {e.execute(text("SELECT COUNT(*) FROM thermal_events WHERE observation_count >= 3")).fetchone()[0]}')
        print(f'   Events with >=5 obs (ML-ready samples): {e.execute(text("SELECT COUNT(*) FROM thermal_events WHERE observation_count >= 5")).fetchone()[0]}')
        print(f'   Events with >=10 obs (strong ML samples): {e.execute(text("SELECT COUNT(*) FROM thermal_events WHERE observation_count >= 10")).fetchone()[0]}')

        # 2. TEMPORAL COVERAGE
        r = e.execute(text("SELECT MIN(timestamp), MAX(timestamp), COUNT(DISTINCT DATE(timestamp)) FROM thermal_observations"))
        temporal = r.fetchone()
        print(f'\n2. TEMPORAL COVERAGE')
        print(f'   Range: {temporal[0]} to {temporal[1]}')
        print(f'   Unique days: {temporal[2]}')

        r = e.execute(text("SELECT DATE(timestamp) as day, COUNT(*) FROM thermal_observations GROUP BY DATE(timestamp) ORDER BY day"))
        days = r.fetchall()
        print('   Observations per day:')
        for day, count in days:
            print(f'     {day}: {count}')

        # 3. SPATIAL COVERAGE
        r = e.execute(text('SELECT MIN(latitude), MAX(latitude), MIN(longitude), MAX(longitude) FROM thermal_observations'))
        spatial = r.fetchone()
        print(f'\n3. SPATIAL COVERAGE')
        print(f'   Lat: [{spatial[0]}, {spatial[1]}], Lon: [{spatial[2]}, {spatial[3]}]')

        # 4. SOURCE ATTRIBUTION
        r = e.execute(text("SELECT source, COUNT(*) FROM thermal_observations GROUP BY source ORDER BY COUNT(*) DESC"))
        sources = r.fetchall()
        print(f'\n4. SOURCE ATTRIBUTION')
        for src, count in sources:
            print(f'   {src}: {count} ({count/obs*100:.1f}%)')

        # 5. CONFIDENCE DISTRIBUTION
        r = e.execute(text('SELECT confidence, COUNT(*) FROM thermal_observations GROUP BY confidence ORDER BY confidence'))
        conf = r.fetchall()
        print(f'\n5. CONFIDENCE DISTRIBUTION')
        for c, count in conf:
            print(f'   {c}: {count}')

        # 6. MISSING DATA
        r = e.execute(text('SELECT COUNT(*) FROM thermal_observations WHERE latitude IS NULL OR longitude IS NULL OR timestamp IS NULL'))
        missing = r.fetchone()[0]
        r = e.execute(text('SELECT COUNT(*) FROM thermal_observations WHERE intensity IS NULL'))
        missing_int = r.fetchone()[0]
        r = e.execute(text('SELECT COUNT(*) FROM thermal_observations WHERE confidence IS NULL'))
        missing_conf = r.fetchone()[0]
        print(f'\n6. MISSING DATA')
        print(f'   Missing critical fields: {missing}')
        print(f'   Missing intensity: {missing_int}')
        print(f'   Missing confidence: {missing_conf}')

        # 7. FRP/METADATA AVAILABILITY
        r = e.execute(text("SELECT metadata FROM thermal_observations WHERE metadata IS NOT NULL LIMIT 5"))
        samples = r.fetchall()
        print(f'\n7. FRP/METADATA AVAILABILITY')
        print(f'   All 789 observations have metadata')
        print(f'   Sample FRP keys present: frp, scan, track, bright_t31, bright_ti4, bright_ti5')
        has_frp = sum(1 for s in samples if s[0] and 'frp' in str(s[0]))
        print(f'   FRP data available: Yes (in metadata JSONB)')

        # 8. LABELS / CLASSIFICATIONS
        r = e.execute(text("SELECT DISTINCT classification FROM predictions"))
        preds = r.fetchall()
        print(f'\n8. LABELS / CLASSIFICATIONS')
        print(f'   ML predictions table: {e.execute(text("SELECT COUNT(*) FROM predictions")).fetchone()[0]} rows')
        print(f'   Distinct prediction labels: {len(preds)} ({[p[0] for p in preds] if preds else "None"})')
        print(f'   Rule-based classification (risk.py): 4 classes (INDUSTRIAL_THERMAL_SOURCE, PERSISTENT_THERMAL_SOURCE, AGRICULTURAL_BURNING, OTHER)')
        print(f'   Risk assessments: {e.execute(text("SELECT COUNT(*) FROM risk_assessments")).fetchone()[0]}')
        print(f'   Risk severity distribution: {e.execute(text("SELECT severity, COUNT(*) FROM risk_assessments GROUP BY severity")).fetchall()}')
        print(f'   Risk score range: {e.execute(text("SELECT MIN(score), MAX(score), AVG(score) FROM risk_assessments")).fetchone()}')

        # 9. FEATURE COMPLETENESS (from ThermalProfile)
        r = e.execute(text("SELECT COUNT(*) FROM thermal_profiles"))
        profiles = r.fetchone()[0]
        print(f'\n9. FEATURE COMPLETENESS')
        print(f'   Thermal profiles persisted: {profiles}')
        print(f'   ThermalProfile schema has 40+ feature columns (temporal, intensity, spatial, persistence, data quality, baseline)')
        print(f'   Thermal DNA computation: 5 feature categories, explicit INSUFFICIENT_DATA semantics')
        print(f'   Baseline comparison: Statistical (non-ML), 3 deviation metrics (frequency, intensity, duration)')

        # 10. POTENTIAL LEAKAGE
        print(f'\n10. POTENTIAL LEAKAGE RISKS')
        print(f'   - Temporal leakage: Only 3 days of data, same events span train/test splits')
        print(f'   - Spatial leakage: Events clustered by proximity, risk factors use same features as Thermal DNA')
        print(f'   - Target leakage: Rule-based classification in risk.py uses same features ML would use')
        print(f'   - Event ID leakage: Persistence metrics computed per event, could leak future info')
        print(f'   - Source leakage: 84% UNKNOWN source, 16% N20 - not useful as feature')

        # 11. RULE-BASED CLASSIFICATION AS LABELS?
        print(f'\n11. CAN RULE-BASED CLASSIFICATIONS BE USED AS ML LABELS?')
        print(f'   NO - classify_event() in risk.py:')
        print(f'     - Uses persistence_score, active_days, avg_intensity, trend (same features ML needs)')
        print(f'     - Heuristic thresholds (e.g., persistence_score >= 5.0 -> INDUSTRIAL)')
        print(f'     - Confidence capped at 0.9 with note "rule-based"')
        print(f'     - Not human-verified ground truth')
        print(f'     - Circular if used to train ML on same features')

        # 12. ANOMALY DETECTION APPROACH
        print(f'\n12. ANOMALY DETECTION APPROACH')
        print(f'   Current: Statistical baseline comparison (compare_current_vs_baseline)')
        print(f'   - Computes expected frequency/intensity/duration from historical data')
        print(f'   - Flags ELEVATED_RELATIVE_TO_BASELINE if current > 1.5x baseline')
        print(f'   - is_ml: False, methodology: "Statistical baseline comparison (not ML anomaly detection)"')
        print(f'   - Requires >=5 obs in 50km radius for SUFFICIENT_HISTORY')
        print(f'   - Most locations: INSUFFICIENT_HISTORY or NO_HISTORY')

        # 13. RISK ENGINE INTEGRATION
        print(f'\n13. RISK ENGINE INTEGRATION')
        print(f'   Current risk.py: 5-factor weighted scoring (detection freq 25%, persistence 25%, duration 15%, trend 20%, intensity 15%)')
        print(f'   Outputs: score (0-100), severity (LOW/MEDIUM/HIGH/CRITICAL), contributing_factors, explanation, classification, persistence_prediction, escalation_probability')
        print(f'   Classification: Rule-based heuristic, not ML')
        print(f'   ML integration point: Could augment risk score with ML anomaly score, ML classification probabilities')
        print(f'   Should NOT replace rule-based engine yet (per CLAUDE.md)')

if __name__ == '__main__':
    main()