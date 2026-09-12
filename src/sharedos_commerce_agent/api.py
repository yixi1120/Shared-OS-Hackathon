from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Annotated, Any

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .auth import AuthenticatedPrincipal, InvalidCredentialError, SellerAuthenticator
from .config import Settings
from .ledger import Ledger
from .models import (
    InteractionTraceInput,
    NegotiationDecision,
    Quote,
    QuoteRequest,
    TradeReceipt,
)
from .seller import SellerService, interaction_contract
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


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()
    seller = SellerService(Ledger(active_settings.ledger_path))
    quotes: dict[str, Quote] = {}
    agreed_prices: dict[str, int] = {}
    low_offers: dict[str, int] = {}
    closed_negotiations: set[str] = set()
    negotiation_lock = RLock()
    authenticator = SellerAuthenticator(
        operator_token=active_settings.seller_api_token,
        principal_tokens_json=active_settings.seller_agent_tokens_json,
    )

    def require_seller_auth(
        authorization: Annotated[str | None, Header()] = None,
    ) -> AuthenticatedPrincipal:
        """Protect mutations and resolve a scoped caller identity when configured.

        Local tests remain keyless. A real SharedOS deployment should configure this
        token or replace the dependency with the organizer's advertised A2A scheme.
        """
        try:
            return authenticator.authenticate(authorization)
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

    app = FastAPI(
        title="SharedOS Agent Commerce Network",
        version="0.1.0",
        description="Machine-readable seller API for autonomous A2A service exchange.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

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
        quotes[quote.quote_id] = quote
        return quote

    @app.post(
        "/v1/quotes/{quote_id}/negotiate",
        response_model=NegotiationDecision,
    )
    def negotiate(
        quote_id: str,
        request: NegotiationRequest,
        principal: AuthenticatedPrincipal = Depends(require_seller_auth),
    ) -> NegotiationDecision:
        quote = quotes.get(quote_id)
        if quote is None:
            raise HTTPException(status_code=404, detail="Unknown quote")
        require_buyer_identity(principal, quote.buyer_id)
        if quote.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Quote expired")
        with negotiation_lock:
            if quote_id in closed_negotiations:
                return NegotiationDecision(
                    accepted=False,
                    message="Negotiation closed; request a new quote.",
                )
            if quote_id in agreed_prices:
                return NegotiationDecision(
                    accepted=True,
                    final_price=agreed_prices[quote_id],
                    message="Previously agreed price remains binding.",
                )
            decision = seller.pricing.negotiate(
                quote, request.buyer_offer, prior_low_offers=low_offers.get(quote_id, 0)
            )
            if decision.accepted and decision.final_price is not None:
                agreed_prices[quote_id] = decision.final_price
            elif request.buyer_offer < quote.reservation_price:
                low_offers[quote_id] = low_offers.get(quote_id, 0) + 1
                if decision.counter_price is None:
                    closed_negotiations.add(quote_id)
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
        quote = quotes.get(request.quote_id)
        if quote is None:
            raise HTTPException(status_code=404, detail="Unknown quote")
        if quote.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Quote expired")
        if request.buyer_id != quote.buyer_id or request.service_id != quote.service_id:
            raise HTTPException(status_code=409, detail="Order does not match quote")
        with negotiation_lock:
            if request.quote_id in closed_negotiations:
                raise HTTPException(
                    status_code=409,
                    detail="Negotiation closed; request a new quote",
                )
            expected_price = agreed_prices.get(request.quote_id, quote.ask_price)
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
        try:
            return seller.deliver(trade_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

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
