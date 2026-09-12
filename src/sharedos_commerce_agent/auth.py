from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from hmac import compare_digest


class AuthenticationConfigurationError(ValueError):
    """Raised when an authentication configuration would be ambiguous or unsafe."""


class InvalidCredentialError(ValueError):
    """Raised when a presented bearer credential is invalid."""


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    principal_id: str | None
    mode: str
    is_operator: bool = False


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
    ) -> None:
        self._operator_token = operator_token
        self._principal_by_digest = self._parse_principal_tokens(
            principal_tokens_json
        )

    @property
    def enabled(self) -> bool:
        return self._operator_token is not None or bool(self._principal_by_digest)

    def authenticate(self, authorization: str | None) -> AuthenticatedPrincipal:
        if not self.enabled:
            return AuthenticatedPrincipal(principal_id=None, mode="disabled-dev")
        scheme, separator, credential = (authorization or "").partition(" ")
        if not separator or scheme.lower() != "bearer" or not credential:
            raise InvalidCredentialError("missing_or_invalid_bearer")

        digest = self._digest(credential)
        principal_id = self._principal_by_digest.get(digest)
        if principal_id is not None:
            return AuthenticatedPrincipal(
                principal_id=principal_id, mode="scoped-agent-token"
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
