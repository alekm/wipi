"""
Encryption service for protecting sensitive data at rest.

Uses Fernet symmetric encryption (AES-128 in CBC mode) from the cryptography library.
Encryption key must be set via WIPI_ENCRYPTION_KEY environment variable.
"""
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class EncryptionService:
    """
    Handles encryption and decryption of sensitive data.

    Uses Fernet symmetric encryption with key from environment variable.
    If no key is configured, operates in plaintext mode for backward compatibility.
    """

    def __init__(self):
        """Initialize encryption service with key from environment."""
        self._cipher: Optional[Fernet] = None
        self._encryption_enabled = False

        # Load encryption key from environment
        encryption_key = os.environ.get("WIPI_ENCRYPTION_KEY")

        if encryption_key:
            try:
                # Validate and initialize Fernet cipher
                self._cipher = Fernet(encryption_key.encode())
                self._encryption_enabled = True
                logger.info("Encryption enabled - secrets will be encrypted at rest")
            except Exception as e:
                logger.error(f"Invalid encryption key: {e}")
                logger.warning("Encryption disabled - secrets will be stored in plaintext")
        else:
            logger.warning(
                "WIPI_ENCRYPTION_KEY not set - encryption disabled. "
                "Secrets will be stored in plaintext. "
                "Generate a key with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

    def is_enabled(self) -> bool:
        """Check if encryption is enabled."""
        return self._encryption_enabled

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt plaintext string.

        Args:
            plaintext: String to encrypt

        Returns:
            Encrypted string (base64 encoded), or plaintext if encryption disabled
        """
        if not plaintext:
            return plaintext

        if not self._encryption_enabled:
            # Encryption disabled - return plaintext
            return plaintext

        try:
            # Encrypt and return as string
            encrypted_bytes = self._cipher.encrypt(plaintext.encode())
            return encrypted_bytes.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise RuntimeError(f"Failed to encrypt data: {e}")

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt ciphertext string.

        Args:
            ciphertext: Encrypted string (base64 encoded)

        Returns:
            Decrypted plaintext string

        Raises:
            RuntimeError: If decryption fails (wrong key, corrupted data)
        """
        if not ciphertext:
            return ciphertext

        if not self._encryption_enabled:
            # Encryption disabled - assume plaintext
            return ciphertext

        try:
            # Attempt decryption
            decrypted_bytes = self._cipher.decrypt(ciphertext.encode())
            return decrypted_bytes.decode()
        except InvalidToken:
            # Data might be plaintext from before encryption was enabled
            logger.warning("Decryption failed - data may be plaintext from before encryption was enabled")
            # Return as-is and let caller handle
            return ciphertext
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise RuntimeError(f"Failed to decrypt data: {e}")

    def try_decrypt(self, ciphertext: str) -> str:
        """
        Try to decrypt, but return plaintext if decryption fails.

        Useful for backward compatibility when migrating from plaintext to encrypted storage.

        Args:
            ciphertext: Encrypted string or plaintext

        Returns:
            Decrypted string if successful, original string if decryption fails
        """
        if not ciphertext:
            return ciphertext

        if not self._encryption_enabled:
            return ciphertext

        try:
            # Try decryption
            return self.decrypt(ciphertext)
        except Exception:
            # Decryption failed - probably plaintext
            logger.debug("try_decrypt: Returning plaintext (decryption failed)")
            return ciphertext


# Global singleton instance
_encryption_service: Optional[EncryptionService] = None


def get_encryption_service() -> EncryptionService:
    """
    Get or create the global encryption service instance.

    Returns:
        EncryptionService singleton
    """
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service


def generate_key() -> str:
    """
    Generate a new Fernet encryption key.

    Returns:
        Base64-encoded encryption key suitable for WIPI_ENCRYPTION_KEY
    """
    return Fernet.generate_key().decode()


# Convenience functions
def encrypt(plaintext: str) -> str:
    """Encrypt plaintext using global encryption service."""
    return get_encryption_service().encrypt(plaintext)


def decrypt(ciphertext: str) -> str:
    """Decrypt ciphertext using global encryption service."""
    return get_encryption_service().decrypt(ciphertext)


def try_decrypt(ciphertext: str) -> str:
    """Try to decrypt, return plaintext if decryption fails."""
    return get_encryption_service().try_decrypt(ciphertext)


def is_encryption_enabled() -> bool:
    """Check if encryption is enabled."""
    return get_encryption_service().is_enabled()
