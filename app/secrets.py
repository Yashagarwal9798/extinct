"""Local encrypted secrets store (Google tokens; later website passwords).

Envelope encryption: every value gets its own random 256-bit data key (AES-GCM); the data key is itself
encrypted with MASTER_KEY. The SQLite file only ever holds ciphertext. Each ciphertext is bound to its
(kind, key) name, so a row copied onto another name won't decrypt.

    store = secret_store()
    store.put("oauth", "google", b'{"token": ...}')
    store.get("oauth", "google")  -> bytes | None
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from functools import cache
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings


def _seal(key: bytes, plain: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, plain, aad)


def _open(key: bytes, sealed: bytes, aad: bytes) -> bytes:
    return AESGCM(key).decrypt(sealed[:12], sealed[12:], aad)


def encrypt(plain: bytes, master_key: bytes, aad: bytes = b"") -> tuple[bytes, bytes]:
    """Returns (ciphertext, encrypted data key)."""
    data_key = AESGCM.generate_key(bit_length=256)
    return _seal(data_key, plain, aad), _seal(master_key, data_key, aad)


def decrypt(ciphertext: bytes, data_key_enc: bytes, master_key: bytes, aad: bytes = b"") -> bytes:
    """Raises cryptography.exceptions.InvalidTag if anything was tampered with or the key is wrong."""
    return _open(_open(master_key, data_key_enc, aad), ciphertext, aad)


class SecretStore:
    def __init__(self, path: str, master_key: bytes):
        # ponytail: master key from .env; OS keychain / KMS if this ever leaves your PC
        self._key = master_key
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS secrets (kind TEXT, key TEXT, value_enc BLOB, data_key_enc BLOB,"
            " meta TEXT, updated_at TEXT, PRIMARY KEY (kind, key))"
        )

    def put(self, kind: str, key: str, value: bytes, meta: dict | None = None) -> None:
        ct, dk = encrypt(value, self._key, f"{kind}:{key}".encode())
        self._db.execute(
            "INSERT OR REPLACE INTO secrets VALUES (?, ?, ?, ?, ?, ?)",
            (kind, key, ct, dk, json.dumps(meta or {}), datetime.now(timezone.utc).isoformat()),
        )

    def get(self, kind: str, key: str) -> bytes | None:
        row = self._db.execute(
            "SELECT value_enc, data_key_enc FROM secrets WHERE kind = ? AND key = ?", (kind, key)
        ).fetchone()
        return decrypt(row[0], row[1], self._key, f"{kind}:{key}".encode()) if row else None

    def delete(self, kind: str, key: str) -> None:
        self._db.execute("DELETE FROM secrets WHERE kind = ? AND key = ?", (kind, key))

    def values_of_kind(self, kind: str) -> list[bytes]:
        """All decrypted values of one kind (used by the outbound leak check)."""
        rows = self._db.execute("SELECT key FROM secrets WHERE kind = ?", (kind,)).fetchall()
        return [v for (k,) in rows if (v := self.get(kind, k))]


@cache
def secret_store() -> SecretStore:
    s = get_settings()
    return SecretStore(s.secrets_db_path, s.master_key)
