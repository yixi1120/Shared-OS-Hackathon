from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files


@dataclass(frozen=True, slots=True)
class SalesReply:
    intent: str
    text: str


class SalesPolicy:
    """Deterministic product introduction and critique-defense content."""

    _KEYWORDS = (
        (
            "score_change",
            (
                "higher score",
                "raise score",
                "raise my score",
                "buy a score",
                "hide dispute",
                "remove dispute",
                "改分",
                "高分",
                "隐藏争议",
            ),
        ),
        (
            "settlement",
            (
                "settlement",
                "receipt",
                "refund",
                "paid",
                "payment",
                "credits moved",
                "结算",
                "付款",
                "退款",
                "到账",
            ),
        ),
        (
            "risk_difference",
            ("risk report", "difference", "trace vs", "区别", "差别"),
        ),
        (
            "bundle",
            ("bundle", "package", "membership", "three reports", "套餐", "会员", "三份"),
        ),
        (
            "provenance",
            (
                "provenance",
                "platform verified",
                "observed",
                "self-reported",
                "self reported",
                "来源",
                "平台验证",
                "自报",
            ),
        ),
        (
            "reputation",
            ("reputation", "trust score", "global score", "信誉", "可信度", "全局评分"),
        ),
        (
            "privacy",
            ("privacy", "secret", "credential", "private", "隐私", "凭据", "商业秘密"),
        ),
        (
            "data",
            ("schema", "event", "payload", "prompt", "artifact", "数据", "字段", "输入"),
        ),
        (
            "price",
            ("price", "cost", "budget", "discount", "credit", "价格", "预算", "优惠", "多少钱"),
        ),
        (
            "value",
            ("why", "useful", "value", "benefit", "为什么", "价值", "有什么用"),
        ),
    )

    def __init__(self) -> None:
        resource = files("sharedos_commerce_agent.resources").joinpath("sales_v1.json")
        self._content = json.loads(resource.read_text(encoding="utf-8"))

    @property
    def introduction(self) -> str:
        return self._content["introduction"]

    def respond(self, message: str) -> SalesReply:
        normalized = message.casefold()
        for intent, keywords in self._KEYWORDS:
            if any(keyword in normalized for keyword in keywords):
                return SalesReply(intent=intent, text=self._content["replies"][intent])
        return SalesReply(intent="fallback", text=self._content["fallback"])
