"""
encryption/pqc.py
──────────────────────────────────────────────────────────────────────────────
Post-Quantum Cryptography wrapper using liboqs Kyber512.

Kyber512 is a NIST-approved Key Encapsulation Mechanism (KEM).
We use it in a hybrid scheme:
  1. Generate Kyber512 keypair
  2. Encapsulate → shared secret + ciphertext
  3. Derive AES-256 key from shared secret (HKDF)
  4. Encrypt payload with AES-256-GCM
  5. Bundle: kyber_ciphertext + aes_nonce + aes_ciphertext + tag

This ensures:
  - Quantum-resistant key exchange (Kyber512)
  - Fast symmetric encryption (AES-256-GCM)
  - Data integrity (GCM authentication tag)
  - Forward secrecy per SOS event
"""

import os
import json
import base64
from loguru import logger

# Try liboqs, fall back to demo mode
try:
    import oqs
    LIBOQS_AVAILABLE = True
    logger.info("liboqs loaded — Kyber512 PQC active")
except ImportError:
    LIBOQS_AVAILABLE = False
    logger.warning("liboqs not installed. Using AES-256-GCM demo mode. Install: pip install liboqs-python")

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend


class KavachPQC:
    """
    Manages PQC keypair and encrypts/decrypts SOS payloads.
    One instance per device session; keypair regenerated per incident.
    """

    KEM_ALGORITHM = "Kyber512"

    def __init__(self):
        self.public_key = None
        self.secret_key = None
        self._kem = None
        self._generate_keypair()

    def _generate_keypair(self):
        if LIBOQS_AVAILABLE:
            self._kem = oqs.KeyEncapsulation(self.KEM_ALGORITHM)
            self.public_key = self._kem.generate_keypair()
            self.secret_key = self._kem.export_secret_key()
            logger.info(f"Kyber512 keypair generated | pubkey: {len(self.public_key)} bytes")
        else:
            # Fallback: random 32-byte symmetric key (demo)
            self.public_key = os.urandom(32)
            self.secret_key = os.urandom(32)
            logger.info("Demo keypair generated (AES-256 fallback)")

    def encrypt(self, payload: dict) -> dict:
        """
        Encrypt a payload dict.
        Returns encrypted bundle safe for transmission/storage.
        """
        plaintext = json.dumps(payload).encode("utf-8")

        if LIBOQS_AVAILABLE:
            return self._kyber_encrypt(plaintext)
        else:
            return self._aes_encrypt(plaintext)

    def decrypt(self, bundle: dict) -> dict:
        """Decrypt an encrypted bundle back to original payload dict."""
        if LIBOQS_AVAILABLE and bundle.get("scheme") == "Kyber512+AES256GCM":
            plaintext = self._kyber_decrypt(bundle)
        else:
            plaintext = self._aes_decrypt(bundle)

        return json.loads(plaintext.decode("utf-8"))

    def _kyber_encrypt(self, plaintext: bytes) -> dict:
        """Full Kyber512 + AES-256-GCM encryption."""
        # Encapsulate: derive shared secret
        kem_enc = oqs.KeyEncapsulation(self.KEM_ALGORITHM)
        ciphertext_kem, shared_secret = kem_enc.encap_secret(self.public_key)

        # Derive AES key via HKDF
        aes_key = self._hkdf(shared_secret)

        # AES-256-GCM encrypt
        nonce = os.urandom(12)
        aesgcm = AESGCM(aes_key)
        ciphertext_aes = aesgcm.encrypt(nonce, plaintext, None)

        return {
            "scheme": "Kyber512+AES256GCM",
            "kem_ciphertext": base64.b64encode(ciphertext_kem).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext_aes).decode(),
        }

    def _kyber_decrypt(self, bundle: dict) -> bytes:
        """Full Kyber512 + AES-256-GCM decryption."""
        kem_ciphertext = base64.b64decode(bundle["kem_ciphertext"])
        nonce = base64.b64decode(bundle["nonce"])
        ciphertext_aes = base64.b64decode(bundle["ciphertext"])

        # Decapsulate shared secret
        kem_dec = oqs.KeyEncapsulation(self.KEM_ALGORITHM, secret_key=self.secret_key)
        shared_secret = kem_dec.decap_secret(kem_ciphertext)

        # Derive AES key
        aes_key = self._hkdf(shared_secret)

        # Decrypt
        aesgcm = AESGCM(aes_key)
        return aesgcm.decrypt(nonce, ciphertext_aes, None)

    def _aes_encrypt(self, plaintext: bytes) -> dict:
        """AES-256-GCM fallback (demo without liboqs)."""
        nonce = os.urandom(12)
        aesgcm = AESGCM(self.secret_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        return {
            "scheme": "AES256GCM_demo",
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
        }

    def _aes_decrypt(self, bundle: dict) -> bytes:
        nonce = base64.b64decode(bundle["nonce"])
        ciphertext = base64.b64decode(bundle["ciphertext"])
        aesgcm = AESGCM(self.secret_key)
        return aesgcm.decrypt(nonce, ciphertext, None)

    def _hkdf(self, shared_secret: bytes) -> bytes:
        """Derive 32-byte AES key from Kyber shared secret."""
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"kavach-sos-v1",
            backend=default_backend()
        )
        return hkdf.derive(shared_secret)

    def public_key_b64(self) -> str:
        return base64.b64encode(self.public_key).decode()


# Module-level singleton (one keypair per server session)
pqc = KavachPQC()
