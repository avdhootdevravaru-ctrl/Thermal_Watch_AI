import os
import sys
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def main():
    logger.info("Setting up database...")
    
    # Check connection
    engine = create_engine(settings.DATABASE_URL)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as e:
        logger.error("PostgreSQL is not reachable; check backend DATABASE_URL and database service.")
        sys.exit(1)
        
    logger.info("PostgreSQL is reachable.")
    
    # Create PostGIS
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        logger.info("PostGIS extension ensured.")
    except Exception as e:
        logger.error("Failed to enable PostGIS (%s); check extension installation and privileges.", type(e).__name__)
        sys.exit(1)
        
    # Run alembic upgrade head
    try:
        from alembic.config import Config
        from alembic import command
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic upgrade head completed successfully.")
    except Exception as e:
        logger.error("Alembic upgrade failed (%s).", type(e).__name__)
        sys.exit(1)

if __name__ == "__main__":
    main()
