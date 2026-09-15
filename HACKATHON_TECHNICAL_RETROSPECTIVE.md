# SharedOS Hackathon：Agent 与后端技术复盘

更新时间：2026-09-14

> 正式 Arena 的身份、消息 sequence、credits 账本、故障和证据缺口已独立归档在 [2026-09-13 正式运行记录](docs/LIVE_RUN_2026-09-13.md)。本复盘解释设计与过程，正式运行事实以该记录为准。

## 1. 项目最终定位

我们的项目最终收敛为 **A2A Interaction Intelligence**：它不是依靠主观打分评价 Agent，而是读取真实 A2A 任务事件，把一次交互还原为可审计的执行记录，并检查完成状态、交付物、事件顺序、时延、Schema、重复事件、争议和证据来源。

对外提供两项付费服务：

- **A2A Interaction Trace**：6 credits，底价 5；生成结构化交互轨迹。
- **A2A Interaction Risk Report**：6 credits，底价 5；生成确定性风险标记及中英文解释。

Health、Catalog、Schema、Contract、示例和报价查询免费。信用结算与报告分析严格分离：报告不会因为发生过付款，就把买家自报的数据升级成平台验证证据。

## 2. 遇到的主要难题

### 2.1 比赛规则和平台接口不断澄清

早期材料让我们以为平台可能提供统一的发现、调用和交易 API；正式讲解后才确认：产品发现主要依靠 SharedNet Room 的 roster 和消息，产品调用依靠每队自己公开的 MCP、CLI 或 HTTPS 接口，credits 则由 SharedNet 官方账本独立结算。系统中也没有我们一开始设想的全局产品注册表和统一 `buy` 路由。

这迫使我们把架构拆成三个边界：

1. SharedNet 负责房间、身份、消息和 credits。
2. 我们的 Seller API 负责报价、订单、分析和交付。
3. LangGraph/Harness 负责编排、策略、恢复和验证。

### 2.2 身份语义容易混淆

比赛现场出现了 seat ID、Agent address、principal ID、tenant/owner 等多个叫法。最后确认：

- `i_...` 是房间内可寻址的 seat/instance；
- `a_...` 是角色或 tag 地址；
- `p_...` 是真正收取 credits 的账户 principal；
- seat ID 是公开路由信息，member token 才是秘密凭据。

因此，我们改成使用官方 CLI 登录并加入房间，保存账户绑定的 seat 凭据，并将凭据文件设为 owner-only `0600`。代码和公开消息只展示 seat、principal 和服务地址，不暴露 token。

### 2.3 Checkpoint 不能单独保证交易安全

最关键的可靠性问题是：如果远程付款已经发生，但进程在写入下一个 LangGraph checkpoint 前中断，重启后可能误以为付款未发生并再次付款。

我们最终采用“双层持久化”：

- LangGraph SQLite checkpoint 保存工作流状态；
- 独立 SQLite operation journal 在外部付款前先记录交易意图。

付款状态按 `PREPARED → SUBMITTED → SETTLED` 推进。超时或断联后不自动重付，而是复用同一个幂等键，并查询官方 receipt、付款方 debit 和收款方 credit。双方账本一致时记为 `BILATERALLY_CONFIRMED`；不一致记为 `DISPUTED`；证据不足保持 `UNKNOWN` 并阻止自动重付。

### 2.4 “消息发送成功”和“付款成功”不是一回事

SharedNet 的 transfer 与房间公开回执是两个动作。比赛中多次出现 `service_unavailable`：付款可能已经最终成功，但公开消息没有发出去。因此我们为付款和 room announcement 使用不同的稳定幂等键，并以官方 ledger 为唯一结算依据，绝不因为房间里没看到回执就重复付款。

### 2.5 LLM 余额、网络和供应商稳定性

部署初期遇到了环境变量未注入、OpenRouter 连接超时和 402 余额不足。我们的修复思路不是让整个 Agent 依赖模型，而是把模型降为“可选语言层”：

- 定价、预算、幂等、风险标记、合规检查和交易状态全部由确定性代码控制；
- 模型只负责基于已有证据生成 critique、建议和自然语言应答；
- 使用 OpenAI-compatible client，主模型和备用模型可通过环境变量替换；
- 输出限制为结构化 JSON，并设置 800-token 上限和总超时；
- 主模型和备用模型都失败时，记录失败并回退到确定性输出。

我们现场尝试了低成本模型路线，以 GLM 系列为主、DeepSeek 系列为备用，但当前仓库默认配置仍以 `MODEL_BASE_URL`、`MODEL_NAME` 和 `MODEL_FALLBACK_NAME` 为准，部署时应以服务器实际注入值为最终事实。

### 2.6 公网部署和进程边界

Dashboard 能打开并不等于 Agent 已经在房间工作。最终部署明确拆成两个长期进程：

- Seller FastAPI 与 Dashboard：托管公开产品和订单交付接口；
- SharedNet listener：监听房间、恢复身份、处理 discovery/query，并发布应答。

我们在 ModelScope 实例上运行代码，通过公网 HTTPS 地址暴露 Dashboard、Catalog、Agent Card 和 API；同时保持 listener 连接正式 Arena 房间。ModelScope 实例有剩余时长限制，因此它适合比赛部署，但长期产品仍应迁移到可自动重启、持久磁盘稳定的服务环境。

## 3. Agent 的搭建思路

### 3.1 LangGraph 只负责编排，不掌握事实真相

Arena 工作流大致为：

```text
prepare
  → discover
  → evaluate_services（有限并发调用）
  → publish_required_feedback
  → rank
  → plan_market
  → prepare_purchase
  → execute_purchase / reconcile_purchase
  → record_purchase
  → audit
```

Graph state 保存 listings、评测结果、排名、购买计划、当前购买位置、模型调用统计和违规项。每个有副作用的操作都使用由 `run_id + service_id + plan position` 派生的稳定幂等键。这样节点重跑不等于重新付款或重复发言。

### 3.2 Harness 负责把“会跑”变成“可证明”

我们建立了两类 Harness：

- Arena Harness：测试发现、并发评测、critique、排名、预算规划、失败重试和恢复；
- Seller Harness：模拟多个买家并发下单，重放相同请求，修改已使用的幂等键，并尝试伪造可信 provenance。

两小时 Seller soak 的结果为：

- 持续 7,755.5 秒；
- 并发数 16；
- 32,272 笔唯一交易全部 `delivered`；
- 未完成交易 0；
- SQLite 完整性检查通过；
- 同时验证了 32,272 次安全重放、32,272 次幂等冲突拒绝和 32,272 次来源降级。

测试也发现报价逻辑每次扫描完整账本，造成 O(n²) 性能衰减。加入 `buyer_id` 索引和 `has_buyer` 查询后，30 秒磁盘基准达到平均 28.15 笔/秒，消除了原来的明显衰减。

### 3.3 房间 Listener 的恢复设计

收到消息时，listener 会在同一个 SQLite 事务中保存消息和 cursor，处理成功后才 acknowledge。每条回复带 `reply_to` 标记；如果发送成功后本地尚未确认就崩溃，重启会先搜索房间里是否已经存在相同回复，找到后只确认原消息，不重复发送。

Listener 只响应版本化 discovery/query 消息，或明确点名本产品、Agent 名称、服务 ID 的自然语言，避免对共享房间每句话都回复造成刷屏和模型费用浪费。

## 4. 后端搭建过程

### 4.1 冻结合同和产品边界

我们先统一服务名称、价格、输入 Schema、输出 Schema、风险标记和证据含义；明确 Reputation Snapshot 未实现，不对外销售。思棋负责的事件身份、去重和 evidence contract 被合入核心实现；冠盛将 Catalog、Pitch、FAQ、销售规则和 Dashboard 交付物拆成 JSON/Markdown 并与代码对齐。

### 4.2 实现 Seller API

后端采用 FastAPI，核心流程为：

```text
GET  /v1/catalog
GET  /v1/contracts/interaction-v1
POST /v1/quotes
POST /v1/quotes/{quote_id}/negotiate
POST /v1/orders
POST /v1/orders/{trade_id}/deliver
```

Catalog、Schema 和示例公开；报价、议价、订单、交付和查询需要认证。系统使用 SQLite 保存订单账本，订单创建使用幂等键；同一个键配同一个请求返回同一结果，同一个键配不同请求则拒绝。

### 4.3 处理 provenance 和隐私

调用方提交的事件统一标记为 `self_reported`，不能自行宣称为平台验证。系统只保存分析所需的最小元数据、哈希和证据引用，排除原始 prompt 和私有 payload。报告输出包含来源和置信度，并将 credits settlement 固定为独立核验项。

### 4.4 增加临时鉴权

正式 SharedOS capability 合同尚未完全确认时，我们增加了过渡层：每个 principal/buyer 使用独立 bearer token，服务器启动时只保存其哈希，并强制 quote、order、delivery 与认证身份一致；运维 token 仅用于故障恢复。该方案能阻止买家身份冒用，但不能冒充官方 capability 鉴权，材料中也明确保留这一限制。

### 4.5 Dashboard 与真实 API 对接

Dashboard 不再读取静态报告快照。它只加载示例输入，展示的报告必须经过真实 `Catalog → Quote → Order → Deliver` API 链路生成。我们同时提供 Agent-facing CLI，让其他 Agent 无需人工打开网页也能调用服务。

### 4.6 正式接入 SharedNet

现场完成了官方 CLI 登录、房间加入、seat 恢复、消息发送/读取、长轮询、balance 和 ledger 查询。Agent 在 Arena 中发布产品介绍、免费/付费边界、价格、产品链接和调用说明，并持续监听新请求。

## 5. 比赛现场结果

正式账本确认项目累计获得 **36 credits 收入**。其中一笔 30-credit 试购保存了完整交易明细，之后收入汇总又增加 6 credits。Agent 持续进行产品宣传、催买家提交事件数据并准备交付，同时遵守用户设定的预算约束。

公开服务曾成功提供以下入口：

- Dashboard：`https://modelscope-sharedos-1.tail81043f.ts.net/dashboard/`
- Catalog：`https://modelscope-sharedos-1.tail81043f.ts.net/v1/catalog`
- Agent Card：`https://modelscope-sharedos-1.tail81043f.ts.net/.well-known/agent.json`
- GitHub：`https://github.com/yixi1120/Shared-OS-Hackathon`

这些结果证明正式房间消息、账户 credits 和公网 Seller 服务能够接通，但不代表所有付款方都已经提供输入并完成对应 artifact 交付。

## 6. 仍然存在的缺口

1. 正式 SharedOS capability/tenant 鉴权合同仍需官方最终确认；当前 per-Agent token 是安全过渡方案。
2. 本地两小时 soak 没有覆盖真实 SharedNet 故障、公网隧道中断和进程级强杀的完整组合。
3. SharedNet API 曾间歇性返回 `service_unavailable`，生产环境应加入指数退避、熔断和更明确的运营告警。
4. ModelScope 临时实例存在到期风险，正式产品需要持久托管、自动拉起和外部健康监控。
5. 收到 credits 后，还需要把“付款核验 → 输入收集 → artifact 交付 → 房间回执”进一步做成自动闭环。
6. 比赛规则要求、商业策略和用户预算保护之间需要显式优先级，不能让 Agent 仅凭房间 prompt 自主耗尽余额。

## 7. 最重要的经验

- **先验证平台真实合同，再设计抽象。** 文档、讲解和现场协议可能不同，代码必须对未知接口 fail closed。
- **LLM 不应控制钱和事实。** 模型负责表达，确定性规则负责预算、评分、风险、身份和状态迁移。
- **Checkpoint 不等于事务。** 只要存在外部副作用，就必须有 write-ahead journal、稳定幂等键和远端对账。
- **付款、交付和证据是三条独立链。** 任何一条都不能替另外两条背书。
- **Harness 是产品的一部分。** 它不仅跑测试，还产生能向评委证明可靠性、幂等性和性能的数据。
- **自动化必须受预算护栏约束。** 无论房间 prompt 如何要求，Agent 都不应在缺少明确授权时自动花完 credits。

总体而言，我们完成的不只是一个会聊天的 Agent，而是一套具备产品发现、公开调用、确定性分析、订单交付、官方 credits 适配、故障恢复和审计证据的 Agent Commerce 原型。项目最有价值的部分不是语言模型本身，而是围绕真实 A2A 交易建立的可靠执行与证据基础设施。
