#!/usr/bin/env python
"""ML Readiness Audit for ThermalWatch AI - Task Group 2."""

from app.db.base import engine
from sqlalchemy import text

def main():
    with engine.connect() as e:
        obs = e.execute(text('SELECT COUNT(*) FROM thermal_observations')).fetchone()[0]
        events = e.execute(text('SELECT COUNT(*) FROM thermal_events')).fetchone()[0]

        print('=== ML READINESS AUDIT ===')
        print(f'\n1. DATA VOLUME')
        print(f'   Total observations: {obs}')
        print(f'   Total thermal events: {events}')
        r = e.execute(text('SELECT COUNT(*) FROM thermal_events WHERE observation_count >= 3'))
        print(f'   Events with >=3 obs (potential ML samples): {r.fetchone()[0]}')
        r = e.execute(text('SELECT COUNT(*) FROM thermal_events WHERE observation_count >= 5'))
        print(f'   Events with >=5 obs (ML-ready samples): {r.fetchone()[0]}')
        r = e.execute(text('SELECT COUNT(*) FROM thermal_events WHERE observation_count >= 10'))
        print(f'   Events with >=10 obs (strong ML samples): {r.fetchone()[0]}')

        r = e.execute(text('SELECT MIN(timestamp), MAX(timestamp), COUNT(DISTINCT DATE(timestamp)) FROM thermal_observations'))
        temporal = r.fetchone()
        print(f'\n2. TEMPORAL COVERAGE')
        print(f'   Range: {temporal[0]} to {temporal[1]}')
        print(f'   Unique days: {temporal[2]}')

        r = e.execute(text('SELECT latitude, longitude FROM thermal_observations LIMIT 1'))
        row = r.fetchone()
        r = e.execute(text('SELECT MIN(latitude), MAX(latitude), MIN(longitude), MAX(longitude) FROM thermal_observations'))
        s = r.fetchone()
        print(f'\n3. SPATIAL COVERAGE')
        print(f'   Lat: [{s[0]}, {s[1]}], Lon: [{s[2]}, {s[3]}]')

        r = e.execute(text('SELECT source, COUNT(*) FROM thermal_observations GROUP BY source ORDER BY COUNT(*) DESC'))
        sources = r.fetchall()
        print(f'\n4. SOURCE ATTRIBUTION')
        for src, count in sources:
            print(f'   {src}: {count} ({count/obs*100:.1f}%)')

        r = e.execute(text('SELECT confidence, COUNT(*) FROM thermal_observations GROUP BY confidence ORDER BY confidence'))
        conf = r.fetchall()
        print(f'\n5. CONFIDENCE DISTRIBUTION')
        for c, count in conf:
            print(f'   {c}: {count}')

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

        r = e.execute(text('SELECT COUNT(*) FROM thermal_profiles'))
        profiles = r.fetchone()[0]
        print(f'\n7. FEATURE COMPLETENESS')
        print(f'   Thermal profiles persisted: {profiles}')
        print(f'   ThermalProfile schema: 40+ feature columns')
        print(f'   Thermal DNA: 5 feature categories (temporal, intensity, spatial, persistence, data quality)')
        print(f'   Baseline: Statistical (non-ML), 3 deviation metrics')

        r = e.execute(text('SELECT COUNT(*) FROM predictions'))
        pred_count = r.fetchone()[0]
        r = e.execute(text('SELECT DISTINCT classification FROM predictions'))
        preds = r.fetchall()
        r = e.execute(text('SELECT COUNT(*) FROM risk_assessments'))
        risk_count = r.fetchone()[0]
        r = e.execute(text('SELECT severity, COUNT(*) FROM risk_assessments GROUP BY severity'))
        sev_dist = r.fetchall()
        r = e.execute(text('SELECT MIN(score), MAX(score), AVG(score) FROM risk_assessments'))
        score_range = r.fetchone()

        print(f'\n8. LABELS / CLASSIFICATIONS')
        print(f'   ML predictions table: {pred_count} rows')
        print(f'   Distinct prediction labels: {len(preds)} (None)' if not preds else f'   Distinct prediction labels: {len(preds)}')
        print(f'   Rule-based classification (risk.py): 4 classes')
        print(f'   Risk assessments: {risk_count}')
        print(f'   Risk severity distribution: {[(s[0], s[1]) for s in sev_dist]}')
        print(f'   Risk score range: min={score_range[0]}, max={score_range[1]}, avg={score_range[2]:.1f}')

        print(f'\n9. POTENTIAL LEAKAGE RISKS')
        print(f'   - Temporal leakage: Only 3 days of data, same events span train/test splits')
        print(f'   - Spatial leakage: Events clustered by proximity, risk factors use same features as Thermal DNA')
        print(f'   - Target leakage: Rule-based classification in risk.py uses same features ML would use')
        print(f'   - Source leakage: 84% UNKNOWN source, 16% N20 - not useful as feature')
        print(f'   - Event ID leakage: Persistence metrics computed per event, could leak future info')

        print(f'\n10. CAN RULE-BASED CLASSIFICATIONS BE USED AS ML LABELS?')
        print(f'   NO - classify_event() in risk.py:')
        print(f'     - Uses persistence_score, active_days, avg_intensity, trend (same features ML needs)')
        print(f'     - Heuristic thresholds (e.g., persistence_score >= 5.0 -> INDUSTRIAL)')
        print(f'     - Confidence capped at 0.9 with note "rule-based"')
        print(f'     - Not human-verified ground truth')
        print(f'     - Circular if used to train ML on same features')

        print(f'\n11. ANOMALY DETECTION APPROACH')
        print(f'   Current: Statistical baseline comparison (compare_current_vs_baseline)')
        print(f'   - Computes expected frequency/intensity/duration from historical data')
        print(f'   - Flags ELEVATED_RELATIVE_TO_BASELINE if current > 1.5x baseline')
        print(f'   - is_ml: False, methodology: "Statistical baseline comparison (not ML anomaly detection)"')
        print(f'   - Requires >=5 obs in 50km radius for SUFFICIENT_HISTORY')
        print(f'   - Most locations: INSUFFICIENT_HISTORY or NO_HISTORY')

        print(f'\n12. RISK ENGINE INTEGRATION')
        print(f'   Current risk.py: 5-factor weighted scoring (detection freq 25%, persistence 25%, duration 15%, trend 20%, intensity 15%)')
        print(f'   Outputs: score (0-100), severity (LOW/MEDIUM/HIGH/CRITICAL), contributing_factors, explanation, classification, persistence_prediction, escalation_probability')
        print(f'   Classification: Rule-based heuristic, not ML')
        print(f'   ML integration point: Could augment risk score with ML anomaly score, ML classification probabilities')
        print(f'   Should NOT replace rule-based engine yet (per CLAUDE.md)')

if __name__ == '__main__':
    main()
