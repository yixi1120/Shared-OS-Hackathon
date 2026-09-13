from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from threading import RLock
from typing import Annotated, Any

import httpx
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from .auth import (
    AgentRateLimitError,
    AgentRegistry,
    AuthenticatedPrincipal,
    InvalidCredentialError,
    RegistrationRateLimitError,
    SellerAuthenticator,
)
from .config import Settings
from .ledger import Ledger
from .models import (
    InteractionTraceInput,
    NegotiationDecision,
    OrderStatus,
    Quote,
    QuoteRequest,
    TradeReceipt,
)
from .seller import SellerService, interaction_contract
from .sharednet_adapter import SharedNetProtocolError, SharedNetRoomClient
from .strategy import InsufficientBudget


class NegotiationRequest(BaseModel):
    buyer_offer: int = Field(ge=1, le=100)


class OrderRequest(BaseModel):
    quote_id: str
    buyer_id: str
    service_id: str
    amount: int = Field(ge=1, le=100)
    idempotency_key: str = Field(min_length=8, max_length=128)
    input: InteractionTraceInput


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)


class SettlementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transfer_id: str = Field(pattern=r"^txn_[0-9A-Za-z]{10}$")


def create_app(
    settings: Settings | None = None,
    *,
    sharednet_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    active_settings = settings or Settings.from_env()
    seller = SellerService(Ledger(active_settings.ledger_path))
    negotiation_lock = RLock()
    registry = (
        AgentRegistry(active_settings.ledger_path)
        if active_settings.seller_registration_enabled
        else None
    )
    authenticator = SellerAuthenticator(
        operator_token=active_settings.seller_api_token,
        principal_tokens_json=active_settings.seller_agent_tokens_json,
        registry=registry,
        allow_insecure_dev=active_settings.seller_allow_insecure_dev,
    )

    def require_seller_auth(
        authorization: Annotated[str | None, Header()] = None,
    ) -> AuthenticatedPrincipal:
        """Protect mutations and resolve a scoped caller identity when configured.

        Local tests remain keyless. A real SharedOS deployment should configure this
        token or replace the dependency with the organizer's advertised A2A scheme.
        """
        try:
            principal = authenticator.authenticate(authorization)
            if (
                registry is not None
                and principal.principal_id is not None
                and not principal.is_operator
            ):
                registry.consume_request(
                    principal.principal_id,
                    limit_per_minute=active_settings.seller_agent_requests_per_minute,
                )
            return principal
        except AgentRateLimitError as exc:
            raise HTTPException(
                status_code=429,
                detail="Agent request rate limit exceeded",
                headers={"Retry-After": "60"},
            ) from exc
        except InvalidCredentialError as exc:
            raise HTTPException(
                status_code=401,
                detail="Missing or invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    def require_buyer_identity(
        principal: AuthenticatedPrincipal, buyer_id: str
    ) -> None:
        if principal.principal_id is not None and principal.principal_id != buyer_id:
            raise HTTPException(
                status_code=403,
                detail="Authenticated principal does not match buyer_id",
            )

    def sharednet_member_token() -> str:
        if active_settings.sharednet_member_token:
            return active_settings.sharednet_member_token
        if (
            active_settings.sharednet_cli_credential_path
            and active_settings.sharednet_room_id
        ):
            from .production import load_cli_room_identity

            return load_cli_room_identity(
                active_settings.sharednet_cli_credential_path,
                room_id=active_settings.sharednet_room_id,
                sharednet_base_url=active_settings.sharednet_base_url,
            ).member_token
        raise HTTPException(
            status_code=503,
            detail="SharedNet settlement credential is not configured",
        )

    app = FastAPI(
        title="SharedOS Agent Commerce Network",
        version="0.1.0",
        description="Machine-readable seller API for autonomous A2A service exchange.",
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": app.version,
            "build_sha": active_settings.build_sha,
            "authentication": "enabled" if authenticator.enabled else "disabled",
            "registration": bool(registry),
        }

    @app.get("/.well-known/agent.json")
    def agent_card() -> dict[str, Any]:
        workflow = ["register", "quote", "order"]
        if active_settings.require_sharednet_payment:
            workflow.append("settlement")
        workflow.append("deliver")
        return {
            "name": "A2A Interaction Intelligence Seller",
            "authentication": {
                "type": "bearer",
                "registration": "/v1/agents/register",
                "registration_method": "POST",
                "registration_body": {"name": "your-agent-name"},
                "token_field": "api_key",
                "buyer_id_field": "buyer_id",
                "identity_scope": (
                    "local Seller identity, not a verified SharedNet principal"
                ),
            },
            "openapi": "/openapi.json",
            "catalog": "/v1/catalog",
            "contract": "/v1/contracts/interaction-v1",
            "workflow": workflow,
            "registration_limit_per_hour": (
                active_settings.seller_registration_limit_per_hour
            ),
            "agent_requests_per_minute": (
                active_settings.seller_agent_requests_per_minute
            ),
            "credit_settlement": "not_evaluated",
        }

    @app.post("/v1/agents/register", status_code=status.HTTP_201_CREATED)
    def register(request: RegistrationRequest, connection: Request) -> dict[str, Any]:
        if registry is None:
            raise HTTPException(status_code=404, detail="Registration is disabled")
        client_id = connection.client.host if connection.client else "unknown"
        try:
            registered = registry.register(
                request.name,
                client_id=client_id,
                limit_per_hour=active_settings.seller_registration_limit_per_hour,
            )
        except RegistrationRateLimitError as exc:
            raise HTTPException(
                status_code=429,
                detail="Registration rate limit exceeded",
                headers={"Retry-After": "3600"},
            ) from exc
        return {
            "agent_id": registered.agent_id,
            "buyer_id": registered.agent_id,
            "api_key": registered.api_key,
            "token_type": "Bearer",
            "identity_verified": False,
            "credit_settlement": "not_evaluated",
        }

    @app.delete("/v1/agents/me/key", status_code=status.HTTP_204_NO_CONTENT)
    def revoke_key(
        authorization: Annotated[str | None, Header()] = None,
    ) -> Response:
        if registry is None:
            raise HTTPException(status_code=404, detail="Registration is disabled")
        try:
            principal = authenticator.authenticate(authorization)
        except InvalidCredentialError as exc:
            raise HTTPException(
                status_code=401,
                detail="Missing or invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        if principal.mode != "registered-agent-token":
            raise HTTPException(
                status_code=403, detail="Only registered keys can revoke themselves"
            )
        _, _, credential = (authorization or "").partition(" ")
        if not registry.revoke(credential):
            raise HTTPException(status_code=401, detail="Key is already revoked")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/v1/catalog")
    def catalog() -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in seller.catalog()]

    @app.get("/v1/contracts/interaction-v1")
    def contract() -> dict[str, Any]:
        return interaction_contract()

    @app.get("/v1/auth/whoami")
    def whoami(
        principal: AuthenticatedPrincipal = Depends(require_seller_auth),
    ) -> dict[str, Any]:
        return {
            "principal_id": principal.principal_id,
            "mode": principal.mode,
            "is_operator": principal.is_operator,
        }

    @app.post(
        "/v1/quotes",
        response_model=Quote,
    )
    def create_quote(
        request: QuoteRequest,
        principal: AuthenticatedPrincipal = Depends(require_seller_auth),
    ) -> Quote:
        require_buyer_identity(principal, request.buyer_id)
        if request.service_id not in {item.service_id for item in seller.catalog()}:
            raise HTTPException(status_code=404, detail="Unknown service")
        try:
            quote = seller.quote(request)
        except InsufficientBudget as exc:
            raise HTTPException(status_code=409, detail="insufficient_budget") from exc
        return seller.ledger.record_quote(quote)

    @app.post(
        "/v1/quotes/{quote_id}/negotiate",
        response_model=NegotiationDecision,
    )
    def negotiate(
        quote_id: str,
        request: NegotiationRequest,
        principal: AuthenticatedPrincipal = Depends(require_seller_auth),
    ) -> NegotiationDecision:
        quote = seller.ledger.get_quote(quote_id)
        if quote is None:
            raise HTTPException(status_code=404, detail="Unknown quote")
        require_buyer_identity(principal, quote.buyer_id)
        if quote.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Quote expired")
        with negotiation_lock:
            agreed_price, low_offer_count, closed = seller.ledger.quote_negotiation(
                quote_id
            )
            if closed:
                return NegotiationDecision(
                    accepted=False,
                    message="Negotiation closed; request a new quote.",
                )
            if agreed_price is not None:
                return NegotiationDecision(
                    accepted=True,
                    final_price=agreed_price,
                    message="Previously agreed price remains binding.",
                )
            decision = seller.pricing.negotiate(
                quote, request.buyer_offer, prior_low_offers=low_offer_count
            )
            if decision.accepted and decision.final_price is not None:
                agreed_price = decision.final_price
            elif request.buyer_offer < quote.reservation_price:
                low_offer_count += 1
                if decision.counter_price is None:
                    closed = True
            seller.ledger.update_quote_negotiation(
                quote_id,
                agreed_price=agreed_price,
                low_offers=low_offer_count,
                closed=closed,
            )
            return decision

    @app.post(
        "/v1/orders",
        response_model=TradeReceipt,
    )
    def create_order(
        request: OrderRequest,
        principal: AuthenticatedPrincipal = Depends(require_seller_auth),
    ) -> TradeReceipt:
        require_buyer_identity(principal, request.buyer_id)
        quote = seller.ledger.get_quote(request.quote_id)
        if quote is None:
            raise HTTPException(status_code=404, detail="Unknown quote")
        if quote.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Quote expired")
        if request.buyer_id != quote.buyer_id or request.service_id != quote.service_id:
            raise HTTPException(status_code=409, detail="Order does not match quote")
        with negotiation_lock:
            agreed_price, _, closed = seller.ledger.quote_negotiation(request.quote_id)
            if closed:
                raise HTTPException(
                    status_code=409,
                    detail="Negotiation closed; request a new quote",
                )
            expected_price = agreed_price or quote.ask_price
        if request.amount != expected_price:
            raise HTTPException(
                status_code=409,
                detail=f"Expected declared amount of {expected_price} credits",
            )
        try:
            return seller.accept_order(
                buyer_id=request.buyer_id,
                service_id=request.service_id,
                amount=request.amount,
                idempotency_key=request.idempotency_key,
                input_payload=request.input.model_dump(mode="json"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/v1/orders/{trade_id}/deliver",
    )
    def deliver(
        trade_id: str,
        principal: AuthenticatedPrincipal = Depends(require_seller_auth),
    ) -> dict[str, Any]:
        receipt = seller.ledger.get(trade_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail=f"Unknown trade: {trade_id}")
        require_buyer_identity(principal, receipt.buyer_id)
        if active_settings.require_sharednet_payment and receipt.status not in {
            OrderStatus.PAID,
            OrderStatus.DELIVERED,
        }:
            raise HTTPException(
                status_code=402,
                detail="A verified SharedNet settlement is required before delivery",
            )
        try:
            return seller.deliver(trade_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/orders/{trade_id}/settlement")
    async def verify_settlement(
        trade_id: str,
        request: SettlementRequest,
        principal: AuthenticatedPrincipal = Depends(require_seller_auth),
    ) -> dict[str, Any]:
        receipt = seller.ledger.get(trade_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail=f"Unknown trade: {trade_id}")
        require_buyer_identity(principal, receipt.buyer_id)
        if not active_settings.sharednet_room_id:
            raise HTTPException(
                status_code=503, detail="SHAREDNET_ROOM_ID is not configured"
            )
        if not active_settings.sharednet_principal_id:
            raise HTTPException(
                status_code=503,
                detail="SHAREDNET_PRINCIPAL_ID is not configured",
            )
        client = SharedNetRoomClient(
            base_url=active_settings.sharednet_base_url,
            room_id=active_settings.sharednet_room_id,
            member_token=sharednet_member_token(),
            transport=sharednet_transport,
        )
        try:
            transfer = await client.verify_received_transfer(
                request.transfer_id,
                recipient_principal_id=active_settings.sharednet_principal_id,
                amount=receipt.amount,
                room_id=active_settings.sharednet_room_id,
                memo_contains=trade_id,
            )
        except SharedNetProtocolError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            await client.close()
        if transfer is None:
            raise HTTPException(
                status_code=404, detail="Transfer not found in SharedNet ledger"
            )
        stored = seller.ledger.record_verified_settlement(
            trade_id, transfer=asdict(transfer)
        )
        return {
            "trade_id": trade_id,
            "status": stored.status.value,
            "transfer_id": transfer.transfer_id,
            "credit_settlement": "verified_separately",
        }

    @app.get(
        "/v1/orders/{trade_id}",
        response_model=TradeReceipt,
    )
    def get_order(
        trade_id: str,
        principal: AuthenticatedPrincipal = Depends(require_seller_auth),
    ) -> TradeReceipt:
        receipt = seller.ledger.get(trade_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail="Unknown trade")
        require_buyer_identity(principal, receipt.buyer_id)
        return receipt

    return app


app = create_app()


def run() -> None:
    uvicorn.run("sharedos_commerce_agent.api:app", host="0.0.0.0", port=8000)
