from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from dataclasses import dataclass
from hmac import compare_digest
from pathlib import Path
from threading import RLock
from uuid import uuid4


class AuthenticationConfigurationError(ValueError):
    """Raised when an authentication configuration would be ambiguous or unsafe."""


class InvalidCredentialError(ValueError):
    """Raised when a presented bearer credential is invalid."""


class RegistrationRateLimitError(ValueError):
    """Raised when anonymous registration exceeds its bounded allowance."""


class AgentRateLimitError(ValueError):
    """Raised when one registered caller exceeds its request allowance."""


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    principal_id: str | None
    mode: str
    is_operator: bool = False


@dataclass(frozen=True, slots=True)
class RegisteredAgent:
    agent_id: str
    name: str
    api_key: str = ""


class AgentRegistry:
    """Durable, revocable per-agent credentials and bounded request counters."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = RLock()
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._memory_connection = (
            sqlite3.connect(":memory:", check_same_thread=False)
            if path == ":memory:"
            else None
        )
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS registered_agents (
                    agent_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    token_digest TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL,
                    revoked_at REAL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS registration_attempts (
                    client_id TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_registration_attempts "
                "ON registration_attempts(client_id, created_at)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_request_attempts (
                    agent_id TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_request_attempts "
                "ON agent_request_attempts(agent_id, created_at)"
            )

    def _connect(self):
        registry = self

        class _ConnectionContext:
            def __enter__(self):
                registry._lock.acquire()
                self.connection = registry._memory_connection or sqlite3.connect(
                    registry.path
                )
                self.connection.row_factory = sqlite3.Row
                return self.connection

            def __exit__(self, exc_type, exc, traceback):
                try:
                    if exc_type is None:
                        self.connection.commit()
                    else:
                        self.connection.rollback()
                finally:
                    if registry._memory_connection is None:
                        self.connection.close()
                    registry._lock.release()

        return _ConnectionContext()

    def register(
        self, name: str, *, client_id: str, limit_per_hour: int
    ) -> RegisteredAgent:
        now = time.time()
        cutoff = now - 3600
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM registration_attempts WHERE created_at < ?", (cutoff,)
            )
            count = connection.execute(
                "SELECT COUNT(*) FROM registration_attempts WHERE client_id = ?",
                (client_id,),
            ).fetchone()[0]
            if count >= limit_per_hour:
                raise RegistrationRateLimitError("registration_rate_limit_exceeded")
            connection.execute(
                "INSERT INTO registration_attempts(client_id, created_at) VALUES (?, ?)",
                (client_id, now),
            )
            agent_id = f"agt_{uuid4().hex}"
            api_key = f"sca_{secrets.token_urlsafe(32)}"
            connection.execute(
                """
                INSERT INTO registered_agents(
                    agent_id, name, token_digest, created_at, revoked_at
                ) VALUES (?, ?, ?, ?, NULL)
                """,
                (agent_id, name, self._digest(api_key), now),
            )
        return RegisteredAgent(agent_id=agent_id, name=name, api_key=api_key)

    def resolve(self, credential: str) -> RegisteredAgent | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT agent_id, name FROM registered_agents
                WHERE token_digest = ? AND revoked_at IS NULL
                """,
                (self._digest(credential),),
            ).fetchone()
        if row is None:
            return None
        return RegisteredAgent(agent_id=row["agent_id"], name=row["name"])

    def revoke(self, credential: str) -> bool:
        with self._connect() as connection:
            changed = connection.execute(
                """
                UPDATE registered_agents SET revoked_at = ?
                WHERE token_digest = ? AND revoked_at IS NULL
                """,
                (time.time(), self._digest(credential)),
            ).rowcount
        return changed == 1

    def consume_request(self, agent_id: str, *, limit_per_minute: int) -> None:
        now = time.time()
        cutoff = now - 60
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM agent_request_attempts WHERE created_at < ?", (cutoff,)
            )
            count = connection.execute(
                "SELECT COUNT(*) FROM agent_request_attempts WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()[0]
            if count >= limit_per_minute:
                raise AgentRateLimitError("agent_rate_limit_exceeded")
            connection.execute(
                "INSERT INTO agent_request_attempts(agent_id, created_at) VALUES (?, ?)",
                (agent_id, now),
            )

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SellerAuthenticator:
    """Authenticate either an operator token or a per-agent scoped bearer token.

    Per-agent tokens are hashed immediately at application startup. The raw JSON is
    expected to come from a secret environment variable and is never returned by the
    API. This is an interim boundary until SharedOS publishes capability verification.
    """

    def __init__(
        self,
        *,
        operator_token: str | None,
        principal_tokens_json: str | None,
        registry: AgentRegistry | None = None,
        allow_insecure_dev: bool = False,
    ) -> None:
        self._operator_token = operator_token
        self._principal_by_digest = self._parse_principal_tokens(principal_tokens_json)
        self.registry = registry
        self.allow_insecure_dev = allow_insecure_dev

    @property
    def enabled(self) -> bool:
        return (
            self._operator_token is not None
            or bool(self._principal_by_digest)
            or self.registry is not None
        )

    def authenticate(self, authorization: str | None) -> AuthenticatedPrincipal:
        if not authorization and self.allow_insecure_dev:
            return AuthenticatedPrincipal(principal_id=None, mode="disabled-dev")
        if not self.enabled:
            raise InvalidCredentialError("authentication_not_configured")
        scheme, separator, credential = (authorization or "").partition(" ")
        if not separator or scheme.lower() != "bearer" or not credential:
            raise InvalidCredentialError("missing_or_invalid_bearer")

        digest = self._digest(credential)
        principal_id = self._principal_by_digest.get(digest)
        if principal_id is not None:
            return AuthenticatedPrincipal(
                principal_id=principal_id, mode="scoped-agent-token"
            )
        if self.registry is not None:
            registered = self.registry.resolve(credential)
            if registered is not None:
                return AuthenticatedPrincipal(
                    principal_id=registered.agent_id,
                    mode="registered-agent-token",
                )
        if self._operator_token is not None and compare_digest(
            credential, self._operator_token
        ):
            return AuthenticatedPrincipal(
                principal_id=None, mode="operator-token", is_operator=True
            )
        raise InvalidCredentialError("missing_or_invalid_bearer")

    @classmethod
    def _parse_principal_tokens(cls, raw: str | None) -> dict[str, str]:
        if raw is None:
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AuthenticationConfigurationError(
                "SELLER_AGENT_TOKENS_JSON must be valid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise AuthenticationConfigurationError(
                "SELLER_AGENT_TOKENS_JSON must map principal IDs to tokens"
            )
        result: dict[str, str] = {}
        for principal_id, token in payload.items():
            if not isinstance(principal_id, str) or not principal_id.strip():
                raise AuthenticationConfigurationError(
                    "Every seller principal ID must be a non-empty string"
                )
            if not isinstance(token, str) or len(token) < 24:
                raise AuthenticationConfigurationError(
                    "Every seller agent token must contain at least 24 characters"
                )
            digest = cls._digest(token)
            if digest in result:
                raise AuthenticationConfigurationError(
                    "Seller agent tokens must be unique per principal"
                )
            result[digest] = principal_id
        return result

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
