"""Tests for the credential store (PLAN T1.2).

All tests are hermetic: KeychainStore is exercised against an in-memory keyring
backend (no real OS keychain is touched), and EncryptedFileStore writes to a
tmp_path. No network, no real secrets.
"""

from __future__ import annotations

from pathlib import Path

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from codingkit.core.credential_store import (
    EncryptedFileStore,
    KeychainStore,
    get_credential_store,
)


class InMemoryKeyring(KeyringBackend):
    """A keyring backend that keeps secrets in a plain dict — for tests only."""

    priority = 1  # higher than the default OS backends so set_keyring picks it

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, servicename: str, username: str, password: str) -> None:
        self._store[(servicename, username)] = password

    def get_password(self, servicename: str, username: str) -> str | None:
        return self._store.get((servicename, username))

    def delete_password(self, servicename: str, username: str) -> None:
        key = (servicename, username)
        if key not in self._store:
            raise PasswordDeleteError("not found")
        del self._store[key]


@pytest.fixture
def in_memory_keyring() -> InMemoryKeyring:
    backend = InMemoryKeyring()
    keyring.set_keyring(backend)
    return backend


# --- KeychainStore -----------------------------------------------------------


def test_keychain_store_write_then_read(in_memory_keyring: InMemoryKeyring) -> None:
    """PLAN T1.2 ① — write a key, read it back, assert the value matches."""
    store = KeychainStore(service_name="codingkit")
    store.set("anthropic_api_key", "sk-test-12345")
    assert store.get("anthropic_api_key") == "sk-test-12345"


def test_keychain_store_missing_key_returns_none(in_memory_keyring) -> None:
    store = KeychainStore()
    assert store.get("does_not_exist") is None
    assert store.exists("does_not_exist") is False


def test_keychain_store_delete_makes_exists_false(in_memory_keyring) -> None:
    """PLAN T1.2 ③ — after delete, exists() must return False."""
    store = KeychainStore()
    store.set("openai_api_key", "sk-abc")
    assert store.exists("openai_api_key") is True
    store.delete("openai_api_key")
    assert store.exists("openai_api_key") is False
    assert store.get("openai_api_key") is None


def test_keychain_store_delete_missing_is_idempotent(in_memory_keyring) -> None:
    """Deleting a key that was never set must not raise (CLI shows '未配置')."""
    store = KeychainStore()
    store.delete("never_set")  # must not raise


# --- EncryptedFileStore ------------------------------------------------------


def test_encrypted_file_store_write_then_read(tmp_path: Path) -> None:
    """PLAN T1.2 ② — round-trip a secret through the encrypted file store."""
    store = EncryptedFileStore(
        master_password="correct-horse-battery-staple",
        file_path=tmp_path / "credentials.enc",
    )
    store.set("anthropic_api_key", "sk-encrypted-999")
    assert store.get("anthropic_api_key") == "sk-encrypted-999"


def test_encrypted_file_store_persists_across_instances(tmp_path: Path) -> None:
    """A second store instance with the same password must reload saved secrets."""
    path = tmp_path / "credentials.enc"
    EncryptedFileStore(master_password="master-pw", file_path=path).set(
        "openai_api_key", "sk-persist"
    )
    reloaded = EncryptedFileStore(master_password="master-pw", file_path=path)
    assert reloaded.get("openai_api_key") == "sk-persist"


def test_encrypted_file_store_delete_makes_exists_false(tmp_path: Path) -> None:
    """PLAN T1.2 ③ — delete then exists() is False for the encrypted store."""
    store = EncryptedFileStore(
        master_password="pw", file_path=tmp_path / "credentials.enc"
    )
    store.set("tmp_key", "value")
    assert store.exists("tmp_key") is True
    store.delete("tmp_key")
    assert store.exists("tmp_key") is False


def test_encrypted_file_store_wrong_password_raises(tmp_path: Path) -> None:
    """A wrong master password must fail to decrypt (GCM auth tag mismatch)."""
    path = tmp_path / "credentials.enc"
    EncryptedFileStore(master_password="right-pw", file_path=path).set("k", "v")
    with pytest.raises(Exception):
        EncryptedFileStore(master_password="wrong-pw", file_path=path).get("k")


def test_encrypted_file_store_ciphertext_is_not_plaintext(tmp_path: Path) -> None:
    """SPEC §4.2 — the secret must never appear in cleartext on disk."""
    path = tmp_path / "credentials.enc"
    secret = "sk-never-plaintext-on-disk"
    EncryptedFileStore(master_password="pw", file_path=path).set("k", secret)
    on_disk = path.read_bytes()
    assert secret.encode() not in on_disk


# --- Factory -----------------------------------------------------------------


def test_factory_creates_keychain_store(in_memory_keyring) -> None:
    store = get_credential_store("keychain")
    assert isinstance(store, KeychainStore)


def test_factory_creates_encrypted_file_store(tmp_path: Path) -> None:
    store = get_credential_store(
        "file", master_password="pw", file_path=tmp_path / "credentials.enc"
    )
    assert isinstance(store, EncryptedFileStore)


def test_factory_rejects_unknown_method() -> None:
    with pytest.raises(ValueError, match="Unsupported credential method"):
        get_credential_store("unknown-method")
