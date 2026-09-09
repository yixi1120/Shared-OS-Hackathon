from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta

from .models import (
    Critique,
    NegotiationDecision,
    PurchaseIntent,
    Quote,
    QuoteRequest,
    RankingEntry,
    ServiceListing,
    ServiceResult,
    utc_now,
)


class ComplianceError(RuntimeError):
    """Raised when a proposed Arena action plan would violate a hard rule."""


@dataclass(frozen=True, slots=True)
class PricingPolicy:
    base_price: int = 12
    floor_ratio: float = 0.72
    first_purchase_discount: float = 0.10
    max_price: int = 40

    def quote(self, request: QuoteRequest, *, first_purchase: bool) -> Quote:
        risk_multiplier = 1.0 + max(0.0, 0.6 - request.buyer_reputation) * 0.25
        raw = self.base_price * request.complexity * request.urgency * risk_multiplier
        if first_purchase:
            raw *= 1.0 - self.first_purchase_discount
        ask = max(1, min(self.max_price, math.ceil(raw)))
        floor = max(1, min(ask, math.ceil(ask * self.floor_ratio)))
        return Quote(
            buyer_id=request.buyer_id,
            service_id=request.service_id,
            ask_price=ask,
            reservation_price=floor,
            pitch=(
                f"For {ask} credits, we validate a structured transaction trace and "
                "return deterministic reliability evidence and risk flags."
            ),
            expires_at=utc_now() + timedelta(minutes=10),
        )

    def negotiate(self, quote: Quote, buyer_offer: int) -> NegotiationDecision:
        if buyer_offer >= quote.ask_price:
            return NegotiationDecision(
                accepted=True,
                final_price=quote.ask_price,
                message="Accepted at the quoted price.",
            )
        if buyer_offer >= quote.reservation_price:
            return NegotiationDecision(
                accepted=True,
                final_price=buyer_offer,
                message="Accepted to close quickly and establish a trading history.",
            )
        counter = max(quote.reservation_price, math.ceil((quote.ask_price + buyer_offer) / 2))
        return NegotiationDecision(
            accepted=False,
            counter_price=counter,
            message=(
                f"We cannot deliver reliably at {buyer_offer}; {counter} credits is "
                "our best counteroffer with the full deliverable and receipt."
            ),
        )


class CritiqueStrategy:
    def select_targets(
        self, listings: list[ServiceListing], minimum: int = 3
    ) -> list[ServiceListing]:
        """Select one strong, reachable listing from each distinct seller."""

        best_by_seller: dict[str, ServiceListing] = {}
        for listing in sorted(
            (item for item in listings if item.reachable),
            key=lambda item: (item.reputation, len(item.evidence), -item.price),
            reverse=True,
        ):
            best_by_seller.setdefault(listing.seller_id, listing)
        targets = list(best_by_seller.values())[:minimum]
        if len(targets) < minimum:
            raise ComplianceError(
                f"Critique round needs {minimum} reachable products; found {len(targets)}"
            )
        return targets

    def create(self, listing: ServiceListing, result: ServiceResult) -> Critique:
        if result.success:
            evidence = (
                f"The service returned receipt {result.receipt_id} in "
                f"{result.latency_ms} ms with fields {sorted(result.output.keys())}."
            )
            weakness = result.output.get("limitation") or result.output.get("caveat")
            if weakness:
                disagreement = (
                    f"I disagree that the current listing fully supports its promise "
                    f"because the delivered result states this limitation: {weakness}."
                )
            else:
                disagreement = (
                    "I disagree that one successful response is enough evidence for the "
                    "listing's reliability claim; no failure-rate or repeatability metric was supplied."
                )
            suggestion = "Publish a three-run success rate and a machine-verifiable output schema."
        else:
            evidence = (
                f"The invocation failed after {result.latency_ms} ms and returned fields "
                f"{sorted(result.output.keys())}."
            )
            disagreement = (
                "I disagree with the listing's availability claim because the tested "
                "service invocation did not complete successfully."
            )
            suggestion = "Add a health check, bounded retry, and idempotent recovery path."
        return Critique(
            product_id=listing.seller_id,
            seller_id=listing.seller_id,
            tested_service_id=listing.service_id,
            evidence=evidence,
            disagreement=disagreement,
            suggestion=suggestion,
        )

    def rank(
        self,
        listings: list[ServiceListing],
        results: dict[str, ServiceResult],
    ) -> list[RankingEntry]:
        entries: list[RankingEntry] = []
        for listing in listings:
            result = results[listing.service_id]
            reliability = 35 if result.success else 0
            latency = max(0, 20 - result.latency_ms / 250)
            evidence = min(20, len(listing.evidence) * 5)
            value = max(0, 25 - listing.price / 2)
            score = min(100, reliability + latency + evidence + value)
            entries.append(
                RankingEntry(
                    product_id=listing.seller_id,
                    score=round(score, 2),
                    rationale=(
                        f"success={result.success}, latency={result.latency_ms}ms, "
                        f"price={listing.price}, evidence_items={len(listing.evidence)}"
                    ),
                )
            )
        return sorted(entries, key=lambda item: item.score, reverse=True)


class MarketStrategy:
    """Build a value-seeking purchase plan that also satisfies the Arena floor."""

    def plan_purchases(
        self,
        listings: list[ServiceListing],
        *,
        own_agent_id: str,
        budget: int = 100,
        minimum_spend: int = 80,
        minimum_products: int = 3,
    ) -> list[PurchaseIntent]:
        eligible = [
            item
            for item in listings
            if item.reachable and item.seller_id != own_agent_id and item.price <= budget
        ]
        unique_sellers = {item.seller_id for item in eligible}
        if len(unique_sellers) < minimum_products:
            raise ComplianceError(
                f"Need {minimum_products} reachable sellers; found {len(unique_sellers)}"
            )

        def expected_value(item: ServiceListing) -> float:
            tag_bonus = 12 if {"sales", "market", "strategy"} & set(item.tags) else 0
            evidence_bonus = min(15, len(item.evidence) * 4)
            return round(35 + item.reputation * 40 + tag_bonus + evidence_bonus, 2)

        ranked = sorted(
            eligible,
            key=lambda item: (expected_value(item) / item.price, expected_value(item)),
            reverse=True,
        )

        selected: list[PurchaseIntent] = []
        selected_sellers: set[str] = set()
        spent = 0

        # First guarantee product diversity using the best listing from each seller.
        for item in ranked:
            if item.seller_id in selected_sellers:
                continue
            if spent + item.price > budget:
                continue
            selected.append(
                PurchaseIntent(
                    product_id=item.seller_id,
                    service_id=item.service_id,
                    seller_id=item.seller_id,
                    price=item.price,
                    expected_value=expected_value(item),
                )
            )
            selected_sellers.add(item.seller_id)
            spent += item.price
            if len(selected_sellers) >= minimum_products:
                break

        # Add high-value services (including repeat sellers) until the spend floor is met.
        remaining = [item for item in ranked if item.service_id not in {x.service_id for x in selected}]
        for item in remaining:
            if spent >= minimum_spend:
                break
            if spent + item.price <= budget:
                selected.append(
                    PurchaseIntent(
                        product_id=item.seller_id,
                        service_id=item.service_id,
                        seller_id=item.seller_id,
                        price=item.price,
                        expected_value=expected_value(item),
                    )
                )
                spent += item.price

        if spent < minimum_spend:
            # Repeats are allowed; buy the best affordable service again to meet the floor.
            for item in ranked:
                while spent < minimum_spend and spent + item.price <= budget:
                    selected.append(
                        PurchaseIntent(
                            product_id=item.seller_id,
                            service_id=item.service_id,
                            seller_id=item.seller_id,
                            price=item.price,
                            expected_value=expected_value(item),
                        )
                    )
                    spent += item.price
                if spent >= minimum_spend:
                    break

        if spent < minimum_spend or len(selected_sellers) < minimum_products:
            raise ComplianceError(
                f"No valid plan: spend={spent}, products={len(selected_sellers)}, budget={budget}"
            )
        return selected
