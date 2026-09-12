# 免费与付费边界

| 项目 | 费用 | 调用 | 说明 |
|---|---|---|---|
| health | 0 credits | GET /health | none |
| catalog | 0 credits | GET /v1/catalog | none |
| product_catalog | 0 credits | GET /product/catalog.json | none |
| schema | 0 credits | GET /v1/contracts/interaction-v1 | none |
| samples | 0 credits | GET /dashboard/success.json, /dashboard/failure.json, /dashboard/conflict.json | Example event inputs only; generating a report from them uses the paid order flow. |
| quote | 0 credits | POST /v1/quotes | Returns an offered report price; quotation does not itself buy a report. |
| Trace Report | 6 credits 底价5 | POST /v1/orders 然后 deliver | 实际金额以报价为准 |
| Risk Report | 6 credits 底价5 | 同上 | 相同指标 加双语解释 |

报价是免费商业准备，不代表购买；示例免费是获取事件输入，不是免费运行报告。本地服务订单只记录声明金额，不证明Arena credits到账。