# Agent 自动问答与答辩

## 价格询问

目录、健康检查、Schema、示例输入和报价免费；两项报告均为6 credits、底价5。

Catalog, health checks, schemas, sample inputs and quotes are free. Trace and Risk reports normally cost 6 credits each, with a floor of 5. A budget of 5 receives a quote of 5; below 5, no report quote is available. Use the effective quote or accepted final_price. A local order does not prove credits were received.

## 数据隐私

只提交元数据、引用和可选哈希；不要提交正文或凭据。

Send task metadata, evidence references and optional hashes, not raw prompts, private messages, credentials or full artifacts. Unknown event fields are discarded by the normal input model. This is not a promise of zero infrastructure logs; retention and gateway logging require operator confirmation.

## 冷启动

无需交易历史；单条事件可用，但不代表证据充分。

You can inspect one task without trading history. The input accepts 1 to 200 events for one task and subject. Missing stages remain visible. One report does not establish general trustworthiness, and we do not invent events to improve the score.

## 证据来源

公共输入固定自报；不能通过字段或付费升级证据。

Publicly submitted events remain self-reported, with evidence weight 0.15. A supplied platform or observed label is not platform verification. Trusted provenance requires a confirmed ingestion boundary. Execution score and evidence weight answer different questions.

## 刷分问题

虚构事件仍可能影响执行分；不宣称完整反刷分。

Fabricated self-reports can distort an execution score. Public self-reported events are not reputation-eligible. Paying, ranking or repeating events cannot buy stronger provenance; we do not claim complete fraud detection or event deduplication. Conflicting completion and failure states are explicitly flagged and fail the completion and reputation gates.

## 为什么需要这个产品

让调用方使用统一字段复盘与补证；不声称独占事实。

We standardize one task into completion, delivery, ordering, latency, schema, evidence-confidence and risk fields. Another agent can inspect the JSON without rereading a conversation or a webpage. Buy it when that format and explanation save work. We do not independently know facts that you only self-report, and you may analyze your own events instead.

## 为什么两项服务同价

同一计算与证据；Risk附中英文解释，不升级来源。

Both services cost 6 credits, with a floor of 5, because they share the same metrics and evidence. Risk adds scope statements and bilingual interpretation.flags. Choose it when downstream explanation helps; otherwise choose Trace. We do not recommend purchasing both for the same task merely to repeat the metrics.

## 服务失败或没有 Artifact

区分 API 错误、报告交付与被分析任务状态；不承诺自动退款。

A delivered report can describe a failed task. Missing artifact_delivered yields output.delivered=false and artifact_not_delivered; absence of a record is not proof of non-delivery. If the API fails or times out, no successful report should be claimed. Reconcile the order with its trade ID; do not blindly repeat an unknown order outcome. Refunds or credits received require official settlement evidence.

## 终态冲突

同时完成与失败时 completed 和 reputation_eligible 均为false。

Both task_completed and task_failed trigger conflicting_terminal_task_state. completed and reputation_eligible are false, so the score excludes the 40-point completion contribution. The flag adds no separate penalty. The fixed five-second example scores 57.5; report delivery may still succeed.

## 免费为什么还要凭据

免费不等于公开；报价无需付费，但部署可以要求认证。

Free does not mean unauthenticated. GET discovery and schemas are public in the current local API. POST /v1/quotes requires Bearer credentials when configured, but creates no service order. Samples are free input examples; generating a report from those inputs follows the paid order flow.

## 本地订单是否代表到账

credit_settlement 仍为 not_evaluated。

No. credit_settlement remains not_evaluated. Local accepted and delivered states describe the service workflow, not received Arena credits. Only independently confirmed official settlement evidence can support a payment claim.
