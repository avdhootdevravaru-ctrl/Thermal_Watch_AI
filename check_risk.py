import sys
sys.path.insert(0, '/d/claude_config/backend')
from app.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.models import RiskAssessment

engine = create_engine(settings.DATABASE_URL)
db = Session(engine)
ras = db.query(RiskAssessment).all()
print('Total RiskAssessment records:', len(ras))
from collections import Counter
sevs = Counter(r.severity for r in ras)
print('Severity distribution:', dict(sevs))
scores = [r.score for r in ras]
if scores:
    print('Score range: %.1f - %.1f' % (min(scores), max(scores)))
    print('Sample scores:', sorted(scores)[:10])
db.close()