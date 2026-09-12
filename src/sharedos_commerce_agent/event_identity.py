"""Canonical logical event identity, independent of room transport identity."""
from __future__ import annotations

import hashlib
import json
import logging

from .models import InteractionEvent


class EventConflictError(ValueError):
    def __init__(self, key: str, previous: str, incoming: str) -> None:
        self.key, self.previous, self.incoming = key, previous, incoming
        # Hashes only: do not log untrusted bodies, identifiers or credentials.
        logging.getLogger(__name__).warning(
            "event_identity_conflict key_hash=%s previous=%s incoming=%s",
            hashlib.sha256(key.encode()).hexdigest(), previous, incoming,
        )
        super().__init__("event_identity_conflict: same logical event ID has different content")


def identity(event: InteractionEvent) -> tuple[str, str]:
    content = event.model_dump(mode="json", exclude={"event_id", "source_id"})
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    # Legacy callers get stable exact-content identity, never a random ID per retry.
    token = ["explicit", event.event_id] if event.event_id is not None else ["legacy-sha256", digest]
    key = json.dumps([event.source_id, event.task_id, event.subject_agent_id, token], separators=(",", ":"))
    return key, digest


def deduplicate_events(events: list[InteractionEvent]) -> list[InteractionEvent]:
    seen: dict[str, str] = {}
    unique = []
    for event in events:
        key, digest = identity(event)
        if key in seen:
            if seen[key] != digest:
                raise EventConflictError(key, seen[key], digest)
            continue
        seen[key] = digest
        unique.append(event)
    return unique
