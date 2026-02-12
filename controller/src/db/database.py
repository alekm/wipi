"""
Database setup and session management.
"""
import os
import logging
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# Database URL from environment or default to SQLite
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/wipi.db")

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """
    Dependency for getting database sessions.
    Use with FastAPI Depends.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database tables and run migrations.

    Creates all tables and adds any missing columns for schema updates.
    """
    # Create all tables (idempotent - only creates missing tables)
    Base.metadata.create_all(bind=engine)

    # Run migrations for schema changes (add missing columns)
    _migrate_add_encrypted_columns()


def _migrate_add_encrypted_columns():
    """
    Migration: Add encrypted columns to existing tables.

    This migration adds:
    - ruckus_one_config.client_secret_encrypted
    - psk_sets.psk_list_encrypted

    Safe to run multiple times (checks if columns exist first).
    """
    try:
        inspector = inspect(engine)

        # Check ruckus_one_config table
        if "ruckus_one_config" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("ruckus_one_config")]

            if "client_secret_encrypted" not in columns:
                logger.info("Adding client_secret_encrypted column to ruckus_one_config table")
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE ruckus_one_config ADD COLUMN client_secret_encrypted TEXT"))
                    conn.commit()
                logger.info("✓ Added client_secret_encrypted column")

            # Make client_secret nullable (SQLite limitation - can't alter column, but model already has nullable=True)

        # Check psk_sets table
        if "psk_sets" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("psk_sets")]

            if "psk_list_encrypted" not in columns:
                logger.info("Adding psk_list_encrypted column to psk_sets table")
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE psk_sets ADD COLUMN psk_list_encrypted TEXT"))
                    conn.commit()
                logger.info("✓ Added psk_list_encrypted column")

            if "psk_count" not in columns:
                logger.info("Adding psk_count column to psk_sets table")
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE psk_sets ADD COLUMN psk_count INTEGER DEFAULT 0 NOT NULL"))
                    conn.commit()
                logger.info("✓ Added psk_count column")

            # Backfill psk_count for existing records where it's 0
            from sqlalchemy.orm import Session as SQLASession
            from ..services.psk_manager import PskSetModel
            from ..services.encryption import get_encryption_service
            import json

            session = SQLASession(bind=engine)
            try:
                psk_sets = session.query(PskSetModel).filter(PskSetModel.psk_count == 0).all()
                if psk_sets:
                    logger.info(f"Backfilling psk_count for {len(psk_sets)} PSK sets...")
                    encryption_service = get_encryption_service()

                    for psk_set in psk_sets:
                        try:
                            # Get decrypted PSK list
                            psk_list_json = psk_set.get_psk_list_json(encryption_service)
                            psks = json.loads(psk_list_json) if psk_list_json else []
                            count = len(psks)

                            # Update count
                            psk_set.psk_count = count
                            logger.info(f"  {psk_set.psk_set_id}: {count} PSKs")
                        except Exception as e:
                            logger.warning(f"  Error backfilling {psk_set.psk_set_id}: {e}")

                    session.commit()
                    logger.info("✓ Backfilled psk_count")
            finally:
                session.close()

    except Exception as e:
        logger.warning(f"Migration warning (may be safe to ignore): {e}")
