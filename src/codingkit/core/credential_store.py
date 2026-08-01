"""Credential storage (PLAN T1.2).

Strategy pattern with a single ``CredentialStore`` interface and two concrete
backends, selected by ``get_credential_store(method)``:

* ``KeychainStore``      — OS keychain via the ``keyring`` library
                          (macOS Keychain / Windows Credential Manager / Linux Secret Service).
* ``EncryptedFileStore`` — AES-256-GCM encrypted JSON file at ``~/.codingkit/credentials.enc``.

Threat-model notes (SPEC §4.2): secrets are never hard-coded, never printed by
``show`` commands (the CLI layer enforces that), and the encrypted-file backend
never writes the master password or any secret in cleartext — only the salt,
nonce and authenticated ciphertext.
"""

from __future__ import annotations

import base64
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

__all__ = [
    "CredentialStore",
    "KeychainStore",
    "EncryptedFileStore",
    "get_credential_store",
    "DEFAULT_SERVICE_NAME",
    "DEFAULT_CREDENTIALS_PATH",
]

DEFAULT_SERVICE_NAME = "codingkit"
DEFAULT_CREDENTIALS_PATH = Path.home() / ".codingkit" / "credentials.enc"


class CredentialStore(ABC):
    """Abstract credential store. Implementations must be secret-aware."""

    @abstractmethod
    def set(self, key_name: str, value: str) -> None:
        """Store ``value`` under ``key_name``, overwriting any existing value."""

    @abstractmethod
    def get(self, key_name: str) -> Optional[str]:
        """Return the stored value, or ``None`` if absent."""

    @abstractmethod
    def delete(self, key_name: str) -> None:
        """Remove ``key_name``. Must be idempotent (no error if absent)."""

    @abstractmethod
    def exists(self, key_name: str) -> bool:
        """Return ``True`` iff a value is currently stored for ``key_name``."""


class KeychainStore(CredentialStore):
    """OS keychain backend (Windows Credential Manager / macOS Keychain / Linux Secret Service)."""

    def __init__(self, service_name: str = DEFAULT_SERVICE_NAME) -> None:
        # Imported lazily so the rest of the package doesn't require keyring.
        import keyring  # noqa: PLC0415  — local import keeps the dependency optional-ish
        from keyring.errors import PasswordDeleteError  # noqa: PLC0415

        self._keyring = keyring
        self._PasswordDeleteError = PasswordDeleteError
        self._service_name = service_name

    def set(self, key_name: str, value: str) -> None:
        self._keyring.set_password(self._service_name, key_name, value)

    def get(self, key_name: str) -> Optional[str]:
        return self._keyring.get_password(self._service_name, key_name)

    def delete(self, key_name: str) -> None:
        try:
            self._keyring.delete_password(self._service_name, key_name)
        except self._PasswordDeleteError:
            # Idempotent: deleting a missing key is a no-op (CLI shows "未配置").
            return

    def exists(self, key_name: str) -> bool:
        return self.get(key_name) is not None


class EncryptedFileStore(CredentialStore):
    """AES-256-GCM encrypted JSON file backend.

    The file holds a JSON blob ``{"salt", "nonce", "ciphertext"}`` (all base64).
    The AES-256 key is derived from the user-supplied master password via
    scrypt. The master password itself is never persisted.
    """

    def __init__(
        self,
        master_password: str,
        file_path: Optional[Path] = None,
    ) -> None:
        if not master_password:
            raise ValueError("master_password must not be empty")

        self._file_path = Path(file_path) if file_path is not None else DEFAULT_CREDENTIALS_PATH
        self._master_password = master_password
        self._data: dict[str, str] = {}
        self._load()

    # -- crypto helpers ------------------------------------------------------

    def _derive_key(self, salt: bytes) -> bytes:
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt  # noqa: PLC0415

        kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
        return kdf.derive(self._master_password.encode("utf-8"))

    def _encrypt_blob(self, data: dict[str, str]) -> dict[str, str]:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415

        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = self._derive_key(salt)
        plaintext = json.dumps(data, ensure_ascii=False).encode("utf-8")
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, associated_data=None)
        return {
            "salt": base64.b64encode(salt).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }

    def _decrypt_blob(self, blob: dict) -> dict[str, str]:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415

        salt = base64.b64decode(blob["salt"])
        nonce = base64.b64decode(blob["nonce"])
        ciphertext = base64.b64decode(blob["ciphertext"])
        key = self._derive_key(salt)
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, associated_data=None)
        return json.loads(plaintext.decode("utf-8"))

    # -- persistence ---------------------------------------------------------

    def _load(self) -> None:
        if not self._file_path.exists():
            self._data = {}
            return
        raw = self._file_path.read_bytes()
        blob = json.loads(raw.decode("utf-8"))
        # A wrong password surfaces here as an InvalidTag / cryptographic error.
        self._data = self._decrypt_blob(blob)

    def _save(self) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        blob = self._encrypt_blob(self._data)
        # Write the JSON blob (no secret in cleartext — only salt/nonce/ciphertext).
        self._file_path.write_text(
            json.dumps(blob, ensure_ascii=False, indent=None),
            encoding="utf-8",
        )

    # -- CredentialStore interface ------------------------------------------

    def set(self, key_name: str, value: str) -> None:
        self._data[key_name] = value
        self._save()

    def get(self, key_name: str) -> Optional[str]:
        return self._data.get(key_name)

    def delete(self, key_name: str) -> None:
        if key_name in self._data:
            del self._data[key_name]
            self._save()

    def exists(self, key_name: str) -> bool:
        return key_name in self._data


def get_credential_store(method: str, **kwargs) -> CredentialStore:
    """Factory: build a credential store by name.

    ``method`` is case-insensitive and matches the ``codingkit config method``
    command. Extra ``kwargs`` are forwarded to the chosen backend.
    """
    normalized = method.strip().lower()
    if normalized == "keychain":
        return KeychainStore(**kwargs)
    if normalized in {"file", "encrypted"}:
        return EncryptedFileStore(**kwargs)
    raise ValueError(
        f"Unsupported credential method: {method!r}. "
        f"Supported methods: keychain, file"
    )
