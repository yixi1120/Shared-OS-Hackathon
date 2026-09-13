from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import logging
import os
import re
import signal
import stat
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from .arena import persistent_arena_runner
from .config import Settings
from .ledger import Ledger
from .models import ArenaRunMode
from .model_client import OpenAICompatibleModel
from .reasoning import StructuredReasoningModel, enhance_room_product_answer
from .sales import SalesPolicy
from .seller import SellerService
from .sharednet_adapter import (
    HttpArenaClient,
    SharedNetJoinResult,
    SharedNetMessage,
    SharedNetProtocolError,
    SharedNetRoomClient,
    SharedNetRoutes,
)


LOGGER = logging.getLogger("sharedos_commerce_agent.production")
ROOM_PROTOCOL = "a2a-interaction-intelligence.room.v1"
IDENTITY_VERSION = 1


class RuntimeConfigurationError(RuntimeError):
    """Raised when a production runtime cannot fail closed safely."""


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    room_id: str
    member_id: str
    member_token: str = field(repr=False)
    version: int = IDENTITY_VERSION


class RuntimeIdentityStore:
    """Small, private, atomic credential store for one SharedNet room identity."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def load(self, room_id: str) -> RuntimeIdentity | None:
        if not self.path.exists():
            return None
        info = self.path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise RuntimeConfigurationError(
                f"SharedNet identity path must be a regular file: {self.path}"
            )
        if info.st_mode & 0o077:
            self.path.chmod(0o600)
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeConfigurationError(
                f"Cannot read SharedNet runtime identity: {self.path}"
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeConfigurationError("SharedNet runtime identity must be an object")
        try:
            identity = RuntimeIdentity(
                room_id=str(payload.get("room_id", "")),
                member_id=str(payload.get("member_id", "")),
                member_token=str(payload.get("member_token", "")),
                version=int(payload.get("version", 0)),
            )
        except (TypeError, ValueError) as exc:
            raise RuntimeConfigurationError(
                "SharedNet runtime identity fields are invalid"
            ) from exc
        if identity.version != IDENTITY_VERSION:
            raise RuntimeConfigurationError("Unsupported SharedNet identity version")
        if identity.room_id != room_id:
            raise RuntimeConfigurationError(
                "Saved SharedNet identity belongs to a different room"
            )
        self._validate(identity)
        return identity

    def save(self, identity: RuntimeIdentity) -> None:
        self._validate(identity)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            descriptor = os.open(temporary, flags, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(asdict(identity), stream, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.path.chmod(0o600)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _validate(identity: RuntimeIdentity) -> None:
        if not identity.room_id.startswith("rom_"):
            raise RuntimeConfigurationError("Saved room_id is not a SharedNet room")
        if not identity.member_id:
            raise RuntimeConfigurationError("Saved SharedNet member_id is empty")
        if not identity.member_token.startswith("sni_"):
            raise RuntimeConfigurationError("Saved member token is invalid")


def load_cli_room_identity(
    path: str, *, room_id: str, sharednet_base_url: str
) -> RuntimeIdentity:
    """Import an account-bound seat created by the official SharedNet CLI.

    The CLI file remains the source credential. We require its owner-only mode and
    never log or return its token outside the redacted RuntimeIdentity object.
    """

    target = Path(path)
    try:
        info = target.lstat()
    except OSError as exc:
        raise RuntimeConfigurationError(
            f"Cannot read SharedNet CLI credential: {target}"
        ) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RuntimeConfigurationError(
            "SharedNet CLI credential must be a regular file"
        )
    if info.st_mode & 0o077:
        raise RuntimeConfigurationError(
            "SharedNet CLI credential must be owner-only (0600)"
        )
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise RuntimeConfigurationError(
            "SharedNet CLI credential must be owned by the current user"
        )
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeConfigurationError(
            "SharedNet CLI credential is not valid JSON"
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RuntimeConfigurationError(
            "SharedNet CLI credential has an unsupported schema"
        )
    if str(payload.get("base_url", "")).rstrip("/") != sharednet_base_url.rstrip(
        "/"
    ):
        raise RuntimeConfigurationError(
            "SharedNet CLI credential belongs to a different origin"
        )
    identity = RuntimeIdentity(
        room_id=str(payload.get("room_id", "")),
        member_id=str(payload.get("member_id", "")),
        member_token=str(payload.get("member_token", "")),
    )
    if identity.room_id != room_id:
        raise RuntimeConfigurationError(
            "SharedNet CLI credential belongs to a different room"
        )
    RuntimeIdentityStore._validate(identity)
    return identity


class RuntimeProcessLock:
    """Prevent concurrent joins/listeners for one persisted room identity."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._descriptor: int | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        os.chmod(self.path, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(descriptor)
            raise RuntimeConfigurationError(
                "Another SharedNet listener already owns this runtime identity"
            ) from exc
        self._descriptor = descriptor

    def release(self) -> None:
        if self._descriptor is None:
            return
        fcntl.flock(self._descriptor, fcntl.LOCK_UN)
        os.close(self._descriptor)
        self._descriptor = None


class RoomMessageRouter:
    """Deterministic, machine-readable room replies without guessed payment logic."""

    _DISCOVERY_TYPES = {"discover", "service_discovery", "catalog"}
    _QUERY_TYPES = {"product_query", "question", "inquiry"}
    _HEALTH_TYPES = {"health", "ping"}

    def __init__(
        self,
        *,
        agent_name: str,
        service_base_url: str,
        payment_target: str | None = None,
        sales_policy: SalesPolicy | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.service_base_url = self._normalize_base_url(service_base_url)
        if payment_target is not None and not re.fullmatch(
            r"(?:p|a|i)_[0-9A-Za-z]{10}", payment_target
        ):
            raise RuntimeConfigurationError(
                "payment_target must be a SharedNet p_, a_, or i_ identifier"
            )
        self.payment_target = payment_target
        self.sales_policy = sales_policy or SalesPolicy()
        self.services = [
            {
                "service_id": item.service_id,
                "name": item.name,
                "price": item.price,
                "floor_price": item.floor_price,
            }
            for item in SellerService(Ledger(":memory:")).catalog()
        ]
        self._aliases = {
            agent_name.casefold(),
            "a2a interaction intelligence",
            "agent-commerce-network",
            *(service["service_id"].casefold() for service in self.services),
        }

    def reply(self, message: SharedNetMessage) -> str | None:
        payload = self._object(message.content)
        if payload is not None:
            message_type = str(payload.get("type", "")).casefold()
            if message_type in self._DISCOVERY_TYPES and self._addressed(payload):
                return self._service_offer(message.message_id)
            if message_type in self._HEALTH_TYPES and self._addressed(payload):
                return self._encoded(
                    message.message_id,
                    "agent_status",
                    status="online",
                    service_base_url=self.service_base_url,
                    credit_settlement="not_evaluated",
                )
            if message_type in self._QUERY_TYPES and self._addressed(payload):
                question = next(
                    (
                        value
                        for key in ("question", "message", "content")
                        if isinstance((value := payload.get(key)), str) and value.strip()
                    ),
                    "",
                )
                return self._answer(message.message_id, question)
            return None

        if not self._free_text_addressed(message.content):
            return None
        return self._answer(message.message_id, message.content)

    def announcement(self) -> str:
        return self._service_offer(None, announcement=True)

    def reply_marker(self, message_id: str) -> str:
        return f'"reply_to":"{message_id}"'

    def announcement_marker(self) -> str:
        return '"announcement":true'

    def _answer(self, reply_to: str | None, question: str) -> str:
        sales_reply = self.sales_policy.respond(question)
        return self._encoded(
            reply_to,
            "product_answer",
            intent=sales_reply.intent,
            answer=sales_reply.text,
            service_base_url=self.service_base_url,
            catalog_url=self._url("v1/catalog"),
            contract_url=self._url("v1/contracts/interaction-v1"),
            credit_settlement="not_evaluated",
        )

    def _service_offer(
        self, reply_to: str | None, *, announcement: bool = False
    ) -> str:
        payment: dict[str, Any]
        if self.payment_target is None:
            payment = {"status": "unavailable"}
        else:
            payment = {
                "status": "available",
                "target": self.payment_target,
                "currency": "credits",
                "settlement": "sharednet-ledger",
                "instruction": (
                    f"pay {self.payment_target} <agreed_amount> "
                    '--memo "<service_id> order=<stable_order_id>" --room'
                ),
            }
        return self._encoded(
            reply_to,
            "service_offer",
            announcement=announcement,
            product="A2A Interaction Intelligence",
            service_base_url=self.service_base_url,
            catalog_url=self._url("v1/catalog"),
            contract_url=self._url("v1/contracts/interaction-v1"),
            services=self.services,
            authentication=(
                "Use the organizer-authorized identity channel. Credentials are never "
                "published in room messages."
            ),
            payment=payment,
            credit_settlement="not_evaluated",
        )

    def _encoded(self, reply_to: str | None, message_type: str, **body: Any) -> str:
        payload: dict[str, Any] = {
            "protocol": ROOM_PROTOCOL,
            "type": message_type,
            "from": self.agent_name,
        }
        if reply_to is not None:
            payload["reply_to"] = reply_to
        payload.update(body)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def _addressed(self, payload: dict[str, Any]) -> bool:
        target = payload.get("to")
        if target is None:
            return True
        if not isinstance(target, str):
            return False
        normalized = target.casefold()
        return normalized in self._aliases or normalized in {"*", "broadcast"}

    def _free_text_addressed(self, content: str) -> bool:
        normalized = content.casefold()
        return any(alias in normalized for alias in self._aliases)

    def _url(self, relative: str) -> str:
        return urljoin(f"{self.service_base_url}/", relative)

    @staticmethod
    def _object(content: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _normalize_base_url(value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeConfigurationError("SERVICE_BASE_URL must be an HTTP(S) URL")
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise RuntimeConfigurationError(
                "SERVICE_BASE_URL cannot contain credentials, query, or fragment"
            )
        return value.rstrip("/")


@dataclass(slots=True)
class SharedNetProductionAgent:
    client: SharedNetRoomClient
    inbox: Ledger
    router: RoomMessageRouter
    room_id: str
    member_id: str
    reasoning_model: StructuredReasoningModel | None = None
    model_attempts: int = 0
    model_successes: int = 0
    model_fallbacks: int = 0

    async def process_once(self, *, timeout_seconds: int = 25) -> int:
        messages = await self.client.receive_pending(
            self.inbox, timeout_seconds=timeout_seconds
        )
        processed = 0
        for message in messages:
            if message.message_id is None:
                raise RuntimeConfigurationError(
                    "SharedNet room message has no stable message_id"
                )
            if message.sender_instance_id == self.member_id:
                self.inbox.acknowledge_message(self.room_id, message.message_id)
                processed += 1
                continue

            reply = self.router.reply(message)
            if reply is not None:
                composition = await enhance_room_product_answer(
                    model=self.reasoning_model,
                    original_message=message.content,
                    deterministic_reply=reply,
                )
                reply = composition.reply
                self.model_attempts += int(composition.model_attempted)
                self.model_successes += int(composition.model_succeeded)
                self.model_fallbacks += int(
                    composition.model_attempted and not composition.model_succeeded
                )
                if composition.model_attempted and not composition.model_succeeded:
                    LOGGER.warning(
                        "Room answer model fell back to deterministic policy: %s",
                        composition.fallback_reason,
                    )
            if reply is not None and not await self._remote_reply_exists(
                self.router.reply_marker(message.message_id)
            ):
                await self.client.say(reply)
            self.inbox.acknowledge_message(self.room_id, message.message_id)
            processed += 1
        return processed

    async def announce(self) -> bool:
        marker = self.router.announcement_marker()
        if await self._remote_reply_exists(marker):
            return False
        await self.client.say(self.router.announcement())
        return True

    async def serve_forever(
        self,
        *,
        stop: asyncio.Event | None = None,
        timeout_seconds: int = 25,
        retry_seconds: float = 2.0,
    ) -> None:
        active_stop = stop or asyncio.Event()
        while not active_stop.is_set():
            try:
                await self.process_once(timeout_seconds=timeout_seconds)
            except (
                httpx.HTTPError,
                RuntimeConfigurationError,
                SharedNetProtocolError,
            ):
                LOGGER.exception("SharedNet receive/dispatch failed; pending input retained")
                try:
                    await asyncio.wait_for(active_stop.wait(), timeout=retry_seconds)
                except TimeoutError:
                    pass

    async def _remote_reply_exists(self, marker: str) -> bool:
        page = await self.client.read(
            grep=marker,
            from_instance=self.member_id,
            order="desc",
            limit=100,
        )
        return any(marker in item.content for item in page.items)


@dataclass(slots=True)
class BootstrappedRuntime:
    agent: SharedNetProductionAgent
    identity: RuntimeIdentity
    process_lock: RuntimeProcessLock = field(repr=False)

    async def close(self) -> None:
        try:
            await self.agent.client.close()
        finally:
            self.process_lock.release()


async def bootstrap_room_runtime(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> BootstrappedRuntime:
    room_id = settings.sharednet_room_id
    if room_id is None:
        raise RuntimeConfigurationError("SHAREDNET_ROOM_ID is required")
    if settings.service_base_url is None:
        raise RuntimeConfigurationError("SERVICE_BASE_URL is required")

    process_lock = RuntimeProcessLock(f"{settings.sharednet_state_path}.lock")
    process_lock.acquire()
    client: SharedNetRoomClient | None = None
    try:
        store = RuntimeIdentityStore(settings.sharednet_state_path)
        saved = store.load(room_id)
        cli_identity = (
            load_cli_room_identity(
                settings.sharednet_cli_credential_path,
                room_id=room_id,
                sharednet_base_url=settings.sharednet_base_url,
            )
            if saved is None and settings.sharednet_cli_credential_path is not None
            else None
        )
        if cli_identity is not None:
            store.save(cli_identity)
            saved = cli_identity
        configured_token = settings.sharednet_member_token
        configured_member_id = settings.sharednet_member_id
        if saved is not None and configured_token not in {None, saved.member_token}:
            raise RuntimeConfigurationError(
                "Configured member token conflicts with the persisted room identity"
            )
        if saved is not None and configured_member_id not in {None, saved.member_id}:
            raise RuntimeConfigurationError(
                "Configured member ID conflicts with the persisted room identity"
            )

        member_token = configured_token or (saved.member_token if saved else None)
        member_id = configured_member_id or (saved.member_id if saved else None)
        if (member_token is None) != (member_id is None):
            raise RuntimeConfigurationError(
                "SHAREDNET_MEMBER_TOKEN and SHAREDNET_MEMBER_ID must be configured together"
            )
        if member_token is None and not settings.sharednet_allow_anonymous_join:
            raise RuntimeConfigurationError(
                "Refusing an anonymous invite join. Run the official SharedNet CLI "
                "under the credited account, then set SHAREDNET_CLI_CREDENTIAL_PATH."
            )

        inbox = _private_inbox(settings.sharednet_inbox_path)
        client = SharedNetRoomClient(
            room_id=room_id,
            invite_token=(
                settings.sharednet_invite_token if member_token is None else None
            ),
            member_token=member_token,
            last_sequence=inbox.message_cursor(room_id),
            agent_name=settings.sharednet_agent_name,
            runtime_kind=settings.sharednet_runtime_kind,
            base_url=settings.sharednet_base_url,
            transport=transport,
        )
        if member_token is None:
            result = await client.join()
            identity = _identity_from_join(result)
            # Persist the credential immediately after join, before doing any work.
            store.save(identity)
            _ingest_join_history(inbox, result)
        else:
            identity = RuntimeIdentity(
                room_id=room_id,
                member_id=member_id or "",
                member_token=member_token,
            )
            store.save(identity)
        router = RoomMessageRouter(
            agent_name=settings.sharednet_agent_name,
            service_base_url=settings.service_base_url,
            payment_target=identity.member_id,
        )
        reasoning_model = (
            OpenAICompatibleModel(settings) if settings.model_api_key else None
        )
        return BootstrappedRuntime(
            agent=SharedNetProductionAgent(
                client=client,
                inbox=inbox,
                router=router,
                room_id=room_id,
                member_id=identity.member_id,
                reasoning_model=reasoning_model,
            ),
            identity=identity,
            process_lock=process_lock,
        )
    except BaseException:
        if client is not None:
            await client.close()
        process_lock.release()
        raise


def configured_arena_routes(settings: Settings) -> SharedNetRoutes:
    required = {
        "ARENA_DISCOVER_ROUTE": settings.arena_discover_route,
        "ARENA_INVOKE_ROUTE": settings.arena_invoke_route,
        "ARENA_CRITIQUE_ROUTE": settings.arena_critique_route,
        "ARENA_RANKING_ROUTE": settings.arena_ranking_route,
        "ARENA_BUY_ROUTE": settings.arena_buy_route,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise RuntimeConfigurationError(
            "Organizer Arena routes are incomplete: " + ", ".join(missing)
        )
    return SharedNetRoutes(
        discover=required["ARENA_DISCOVER_ROUTE"] or "",
        invoke=required["ARENA_INVOKE_ROUTE"] or "",
        critique=required["ARENA_CRITIQUE_ROUTE"] or "",
        ranking=required["ARENA_RANKING_ROUTE"] or "",
        buy=required["ARENA_BUY_ROUTE"] or "",
        reconcile=settings.arena_reconcile_route,
    )


async def run_arena_graph(
    settings: Settings, *, mode: ArenaRunMode, run_id: str | None
) -> dict[str, Any]:
    if settings.arena_base_url is None or settings.arena_api_token is None:
        raise RuntimeConfigurationError(
            "ARENA_BASE_URL and ARENA_API_TOKEN are required for Arena graph mode"
        )
    if settings.agent_node_id is None:
        raise RuntimeConfigurationError("AGENT_NODE_ID is required for Arena graph mode")
    client = HttpArenaClient(
        base_url=settings.arena_base_url,
        api_token=settings.arena_api_token,
        routes=configured_arena_routes(settings),
    )
    try:
        async with persistent_arena_runner(client, settings=settings) as runner:
            report = await runner.run_round(
                settings.agent_node_id, mode, run_id=run_id
            )
            return report.model_dump(mode="json")
    finally:
        await client.close()


def _identity_from_join(result: SharedNetJoinResult) -> RuntimeIdentity:
    return RuntimeIdentity(
        room_id=result.room_id,
        member_id=result.member_id,
        member_token=result.member_token,
    )


def _private_inbox(path: str) -> Ledger:
    if path == ":memory:":
        return Ledger(path)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.parent.chmod(0o700)
    inbox = Ledger(path)
    target.chmod(0o600)
    return inbox


def _ingest_join_history(inbox: Ledger, result: SharedNetJoinResult) -> None:
    history = result.history
    cursor = max(
        [history.next_cursor or 0, *(message.sequence for message in history.items)],
        default=0,
    )
    inbox.receive_messages(
        result.room_id, [asdict(message) for message in history.items], cursor
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Production SharedNet listener and organizer-route Arena runner."
    )
    parser.add_argument("--log-level", default="INFO")
    subparsers = parser.add_subparsers(dest="command", required=True)

    listen = subparsers.add_parser(
        "listen", help="Join or resume a room and answer addressed product messages."
    )
    listen.add_argument("--announce", action="store_true")
    listen.add_argument("--once", action="store_true")
    listen.add_argument("--poll-timeout", type=int, default=25, choices=range(0, 26))

    arena = subparsers.add_parser(
        "arena", help="Run the LangGraph workflow against organizer-published routes."
    )
    arena.add_argument(
        "--mode", choices=["critique", "market", "full"], required=True
    )
    arena.add_argument("--run-id")
    return parser


async def _run(arguments: argparse.Namespace) -> int:
    settings = Settings.from_env()
    if arguments.command == "arena":
        report = await run_arena_graph(
            settings, mode=ArenaRunMode(arguments.mode), run_id=arguments.run_id
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    runtime = await bootstrap_room_runtime(settings)
    try:
        LOGGER.info(
            "SharedNet identity ready: room=%s member=%s service=%s",
            runtime.identity.room_id,
            runtime.identity.member_id,
            settings.service_base_url,
        )
        if arguments.announce:
            announced = await runtime.agent.announce()
            LOGGER.info("Service announcement sent=%s", announced)
        if arguments.once:
            processed = await runtime.agent.process_once(
                timeout_seconds=arguments.poll_timeout
            )
            LOGGER.info("Processed room messages=%d", processed)
            return 0

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signum, stop.set)
            except NotImplementedError:
                pass
        await runtime.agent.serve_forever(
            stop=stop, timeout_seconds=arguments.poll_timeout
        )
        return 0
    finally:
        await runtime.close()


def main() -> None:
    arguments = _parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, arguments.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        raise SystemExit(asyncio.run(_run(arguments)))
    except RuntimeConfigurationError as exc:
        LOGGER.error("%s", exc)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
