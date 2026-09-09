from __future__ import annotations

from datetime import datetime, timezone
from hmac import compare_digest
from typing import Annotated, Any

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .config import Settings
from .ledger import Ledger
from .models import (
    InteractionTraceInput,
    NegotiationDecision,
    Quote,
    QuoteRequest,
    TradeReceipt,
)
from .seller import SellerService


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

    def require_seller_auth(
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        """Protect mutations when a deployment token is configured.

        Local tests remain keyless. A real SharedOS deployment should configure this
        token or replace the dependency with the organizer's advertised A2A scheme.
        """
        expected = active_settings.seller_api_token
        if expected is None:
            return
        scheme, separator, credential = (authorization or "").partition(" ")
        if (
            not separator
            or scheme.lower() != "bearer"
            or not compare_digest(credential, expected)
        ):
            raise HTTPException(
                status_code=401,
                detail="Missing or invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
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

    @app.post(
        "/v1/quotes",
        response_model=Quote,
        dependencies=[Depends(require_seller_auth)],
    )
    def create_quote(request: QuoteRequest) -> Quote:
        if request.service_id not in {item.service_id for item in seller.catalog()}:
            raise HTTPException(status_code=404, detail="Unknown service")
        quote = seller.quote(request)
        quotes[quote.quote_id] = quote
        return quote

    @app.post(
        "/v1/quotes/{quote_id}/negotiate",
        response_model=NegotiationDecision,
        dependencies=[Depends(require_seller_auth)],
    )
    def negotiate(quote_id: str, request: NegotiationRequest) -> NegotiationDecision:
        quote = quotes.get(quote_id)
        if quote is None:
            raise HTTPException(status_code=404, detail="Unknown quote")
        if quote.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Quote expired")
        decision = seller.pricing.negotiate(quote, request.buyer_offer)
        if decision.accepted and decision.final_price is not None:
            agreed_prices[quote_id] = decision.final_price
        return decision

    @app.post(
        "/v1/orders",
        response_model=TradeReceipt,
        dependencies=[Depends(require_seller_auth)],
    )
    def create_order(request: OrderRequest) -> TradeReceipt:
        quote = quotes.get(request.quote_id)
        if quote is None:
            raise HTTPException(status_code=404, detail="Unknown quote")
        if quote.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Quote expired")
        if request.buyer_id != quote.buyer_id or request.service_id != quote.service_id:
            raise HTTPException(status_code=409, detail="Order does not match quote")
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
        dependencies=[Depends(require_seller_auth)],
    )
    def deliver(trade_id: str) -> dict[str, Any]:
        try:
            return seller.deliver(trade_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get(
        "/v1/orders/{trade_id}",
        response_model=TradeReceipt,
        dependencies=[Depends(require_seller_auth)],
    )
    def get_order(trade_id: str) -> TradeReceipt:
        receipt = seller.ledger.get(trade_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail="Unknown trade")
        return receipt

    return app


app = create_app()


def run() -> None:
    uvicorn.run("sharedos_commerce_agent.api:app", host="0.0.0.0", port=8000)
