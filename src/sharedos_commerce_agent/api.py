from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from importlib.resources import files

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from .config import Settings
from .ledger import Ledger
from .models import NegotiationDecision, Quote, QuoteRequest, TradeReceipt
from .seller import SellerService
from .sales import answer, catalog_for_agents, introduction, templates


class SalesQuestion(BaseModel):
    topic: str = Field(default="why_node", max_length=80)
    goal: str | None = Field(default=None, max_length=80)


class NegotiationRequest(BaseModel):
    buyer_offer: int = Field(ge=1, le=100)


class OrderRequest(BaseModel):
    quote_id: str
    buyer_id: str
    service_id: str
    amount: int = Field(ge=1, le=100)
    idempotency_key: str = Field(min_length=8, max_length=128)
    input: dict[str, Any] = Field(default_factory=dict)


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()
    seller = SellerService(Ledger(active_settings.ledger_path))
    quotes: dict[str, Quote] = {}
    agreed_prices: dict[str, int] = {}

    app = FastAPI(
        title="SharedOS Agent Commerce Network",
        version="0.1.0",
        description="Machine-readable seller API for autonomous agent-to-agent trade.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/catalog")
    def catalog() -> list[dict[str, Any]]:
        return catalog_for_agents(seller)

    @app.get("/v1/sales")
    def sales_description() -> dict[str, Any]:
        return {"intro": introduction(), "faq": templates()["faq"],
                "offers": templates()["offers"], "side_effects": False}

    @app.post("/v1/sales/respond")
    def sales_response(request: SalesQuestion) -> dict[str, Any]:
        return answer(request.topic, request.goal)

    app.mount("/dashboard", StaticFiles(
        directory=str(files("sharedos_commerce_agent").joinpath("dashboard")), html=True
    ), name="dashboard")

    @app.post("/v1/quotes", response_model=Quote)
    def create_quote(request: QuoteRequest) -> Quote:
        if request.service_id not in {item.service_id for item in seller.catalog()}:
            raise HTTPException(status_code=404, detail="Unknown service")
        quote = seller.quote(request)
        quotes[quote.quote_id] = quote
        return quote

    @app.post(
        "/v1/quotes/{quote_id}/negotiate", response_model=NegotiationDecision
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

    @app.post("/v1/orders", response_model=TradeReceipt)
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
                detail=f"Expected payment of {expected_price} credits",
            )
        try:
            return seller.settle(
                buyer_id=request.buyer_id,
                service_id=request.service_id,
                amount=request.amount,
                idempotency_key=request.idempotency_key,
                input_payload=request.input,
            )
        except ValidationError as exc:
            # Never echo rejected raw input (which can contain private content).
            errors = [{"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
            raise HTTPException(status_code=422, detail=errors) from exc

    @app.post("/v1/orders/{trade_id}/deliver")
    def deliver(trade_id: str) -> dict[str, Any]:
        try:
            return seller.deliver(trade_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v1/orders/{trade_id}", response_model=TradeReceipt)
    def get_order(trade_id: str) -> TradeReceipt:
        receipt = seller.ledger.get(trade_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail="Unknown trade")
        return receipt

    return app


app = create_app()


def run() -> None:
    uvicorn.run("sharedos_commerce_agent.api:app", host="0.0.0.0", port=8000)
