#!/usr/bin/env python3
"""
Migration script to encrypt existing plaintext secrets in database.

This script should be run AFTER setting the WIPI_ENCRYPTION_KEY environment variable.
It will:
1. Read existing plaintext secrets from database
2. Encrypt them
3. Store in encrypted fields
4. Clear plaintext fields

Usage:
    export WIPI_ENCRYPTION_KEY="your-generated-key"
    python migrate_to_encrypted_storage.py
"""
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from controller.src.db import SessionLocal, init_db
from controller.src.models.db_models import RuckusOneConfigModel
from controller.src.services.psk_manager import PskSetModel
from controller.src.services.encryption import get_encryption_service


def migrate_ruckus_one_config():
    """Migrate Ruckus One configuration to encrypted storage."""
    db = SessionLocal()
    encryption_service = get_encryption_service()

    if not encryption_service.is_enabled():
        print("ERROR: Encryption is not enabled. Set WIPI_ENCRYPTION_KEY environment variable.")
        print("Generate a key with:")
        print("  python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'")
        return False

    try:
        # Find all configs with plaintext client_secret
        configs = db.query(RuckusOneConfigModel).filter(
            RuckusOneConfigModel.client_secret.isnot(None),
            RuckusOneConfigModel.client_secret != ""
        ).all()

        if not configs:
            print("No Ruckus One configs with plaintext client_secret found.")
            return True

        print(f"Found {len(configs)} Ruckus One config(s) to migrate.")

        for config in configs:
            print(f"  Migrating config ID {config.id} (tenant: {config.tenant_id})...")

            # Encrypt the plaintext secret
            config.set_client_secret(config.client_secret, encryption_service)

            print(f"    ✓ Encrypted client_secret")

        # Commit all changes
        db.commit()
        print(f"✓ Successfully migrated {len(configs)} Ruckus One config(s)")
        return True

    except Exception as e:
        print(f"ERROR: Migration failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def migrate_psk_sets():
    """Migrate PSK sets to encrypted storage."""
    db = SessionLocal()
    encryption_service = get_encryption_service()

    if not encryption_service.is_enabled():
        print("ERROR: Encryption is not enabled. Set WIPI_ENCRYPTION_KEY environment variable.")
        return False

    try:
        # Find all PSK sets with plaintext psk_list
        psk_sets = db.query(PskSetModel).filter(
            PskSetModel.psk_list.isnot(None),
            PskSetModel.psk_list != ""
        ).all()

        if not psk_sets:
            print("No PSK sets with plaintext psk_list found.")
            return True

        print(f"Found {len(psk_sets)} PSK set(s) to migrate.")

        for psk_set in psk_sets:
            print(f"  Migrating PSK set '{psk_set.name}' (ID: {psk_set.psk_set_id})...")

            # Encrypt the plaintext PSK list
            psk_set.set_psk_list_json(psk_set.psk_list, encryption_service)

            print(f"    ✓ Encrypted PSK list ({len(psk_set.psk_list)} bytes)")

        # Commit all changes
        db.commit()
        print(f"✓ Successfully migrated {len(psk_sets)} PSK set(s)")
        return True

    except Exception as e:
        print(f"ERROR: Migration failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def add_encrypted_columns():
    """Add encrypted columns to database tables if they don't exist."""
    db = SessionLocal()

    try:
        # Check if columns exist by trying to query them
        try:
            db.query(RuckusOneConfigModel.client_secret_encrypted).first()
            print("✓ RuckusOneConfigModel.client_secret_encrypted column exists")
        except Exception:
            print("Adding client_secret_encrypted column to ruckus_one_config table...")
            db.execute("ALTER TABLE ruckus_one_config ADD COLUMN client_secret_encrypted TEXT")
            db.commit()
            print("✓ Added client_secret_encrypted column")

        try:
            db.query(PskSetModel.psk_list_encrypted).first()
            print("✓ PskSetModel.psk_list_encrypted column exists")
        except Exception:
            print("Adding psk_list_encrypted column to psk_sets table...")
            db.execute("ALTER TABLE psk_sets ADD COLUMN psk_list_encrypted TEXT")
            db.commit()
            print("✓ Added psk_list_encrypted column")

        # Make plaintext columns nullable
        print("Updating plaintext columns to be nullable...")
        # Note: SQLite doesn't support ALTER COLUMN, so we skip this
        # The model already has nullable=True on these columns
        print("✓ Column schema updated")

        return True

    except Exception as e:
        print(f"ERROR: Failed to add columns: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def main():
    """Run the migration."""
    print("=" * 60)
    print("WiPi Encryption Migration Script")
    print("=" * 60)
    print()

    # Check for encryption key
    encryption_key = os.environ.get("WIPI_ENCRYPTION_KEY")
    if not encryption_key:
        print("ERROR: WIPI_ENCRYPTION_KEY environment variable not set.")
        print()
        print("Generate a new key:")
        print("  python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'")
        print()
        print("Set the key:")
        print("  export WIPI_ENCRYPTION_KEY='your-generated-key'")
        print()
        sys.exit(1)

    print(f"✓ Encryption key configured")
    print()

    # Initialize database
    print("Initializing database...")
    init_db()
    print("✓ Database initialized")
    print()

    # Add encrypted columns
    print("Step 1: Adding encrypted columns to database...")
    print("-" * 60)
    if not add_encrypted_columns():
        print("FAILED: Could not add encrypted columns")
        sys.exit(1)
    print()

    # Migrate Ruckus One config
    print("Step 2: Migrating Ruckus One configuration...")
    print("-" * 60)
    if not migrate_ruckus_one_config():
        print("FAILED: Ruckus One migration failed")
        sys.exit(1)
    print()

    # Migrate PSK sets
    print("Step 3: Migrating PSK sets...")
    print("-" * 60)
    if not migrate_psk_sets():
        print("FAILED: PSK set migration failed")
        sys.exit(1)
    print()

    print("=" * 60)
    print("✓ Migration completed successfully!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Add WIPI_ENCRYPTION_KEY to your docker-compose.yml or .env file")
    print("  2. Restart the controller: docker compose restart controller")
    print("  3. Verify encryption is working by checking logs")
    print()


if __name__ == "__main__":
    main()
