import sqlite3

import pytest
from cryptography.exceptions import InvalidTag

from app.secrets import SecretStore, decrypt, encrypt

MASTER = b"M" * 32


@pytest.fixture
def store(tmp_path):
    return SecretStore(str(tmp_path / "secrets.db"), MASTER)


def test_round_trip(store):
    store.put("oauth", "google", b'{"refresh_token": "1//0abc"}', {"email": "me@x.com"})
    assert store.get("oauth", "google") == b'{"refresh_token": "1//0abc"}'


def test_missing_returns_none(store):
    assert store.get("oauth", "nope") is None


def test_overwrite_and_delete(store):
    store.put("oauth", "google", b"one")
    store.put("oauth", "google", b"two")
    assert store.get("oauth", "google") == b"two"
    store.delete("oauth", "google")
    assert store.get("oauth", "google") is None


def test_file_never_contains_plaintext(tmp_path, store):
    store.put("site", "discord", b"hunter2-super-secret")
    raw = (tmp_path / "secrets.db").read_bytes()
    wal = tmp_path / "secrets.db-wal"
    if wal.exists():
        raw += wal.read_bytes()
    assert b"hunter2" not in raw


def test_wrong_master_key_fails(tmp_path, store):
    store.put("oauth", "google", b"value")
    other = SecretStore(str(tmp_path / "secrets.db"), b"X" * 32)
    with pytest.raises(InvalidTag):
        other.get("oauth", "google")


def test_tampered_ciphertext_fails(tmp_path, store):
    store.put("oauth", "google", b"value")
    db = sqlite3.connect(tmp_path / "secrets.db")
    ct = bytearray(db.execute("SELECT value_enc FROM secrets").fetchone()[0])
    ct[-1] ^= 1
    db.execute("UPDATE secrets SET value_enc = ?", (bytes(ct),))
    db.commit()
    with pytest.raises(InvalidTag):
        store.get("oauth", "google")


def test_row_copied_to_another_name_fails(tmp_path, store):
    store.put("site", "a", b"secret-a")
    db = sqlite3.connect(tmp_path / "secrets.db")
    db.execute("INSERT INTO secrets SELECT kind, 'b', value_enc, data_key_enc, meta, updated_at FROM secrets WHERE key = 'a'")
    db.commit()
    with pytest.raises(InvalidTag):
        store.get("site", "b")


def test_same_value_encrypts_differently():
    a = encrypt(b"same", MASTER)
    b = encrypt(b"same", MASTER)
    assert a != b
    assert decrypt(*a, MASTER) == decrypt(*b, MASTER) == b"same"


def test_values_of_kind(store):
    store.put("site", "a", b"pw-a")
    store.put("site", "b", b"pw-b")
    store.put("oauth", "google", b"tok")
    assert sorted(store.values_of_kind("site")) == [b"pw-a", b"pw-b"]
