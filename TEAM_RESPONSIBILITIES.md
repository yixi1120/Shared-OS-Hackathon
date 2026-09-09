# SharedOS Hackathon 四人分工与交付计划

> 版本：根据官方 Arena 形式重新校准  
> 团队成员：子洋、雅婷、冠盛、思棋  
> 官方页面：https://www.mentor-mates.com/events/shared-os-hackathon/overview

## 1. 比赛目标

这次比赛没有人类评委和人类客户。产品由其他参赛者的个人 Agent 试用、评价、排名和购买。

我们必须同时满足三类目标：

1. **资格合规**：Agent 和产品全程在线，完成两个 Arena round，期间无人手动操作。
2. **Agents' Choice**：让其他 Agent 认为我们的产品最有用，并给出较高排名。
3. **Top Earner**：让其他 Agent 购买我们的服务，尽可能赚取更多 Arena credits。

我们的比赛版产品定位为：

> **Verified A2A Interaction Intelligence**
> 其他 Agent 通过我方节点执行 A2A Task；我方基于可观察的任务状态、Artifact、延迟、schema 和证据来源生成 trace 与风险标记，不自行声称验证付款。

长期可以发展为 Verified Agent Reputation Network，但本次 Arena 优先出售能够立即产生价值的风险分析和购买决策服务。

## 2. Arena 硬性要求

以下要求优先级高于所有产品功能：

- 加入官方 Discord，并在提交中填写 Discord username。
- 将个人 Agent 注册到 SharedNet，并在提交中填写 node ID。
- 截止前提交一个构建在 SharedOS 上、至少提供一项可调用服务的产品。
- Agent 和产品在完整 Arena 时段持续在线、可发现、可调用。
- Round 1 至少试用 3 个其他产品。
- 对每个试用产品至少发布 1 条具体 disagreement。
- Round 1 提交最终 ranking。
- Round 2 在 100 credits 中至少消费 80 credits。
- Round 2 至少购买 3 个不同产品。
- Arena 中不能由人手动发送消息、排名、购买、销售、交付或修复 Agent。

任何新功能都不能影响这些要求。

## 3. Agent 功能拆分

Agent 功能分成两个方向，但不构建两个互相用自然语言沟通的复杂 Agent：

```text
                     SharedNet / Arena
                            │
             ┌──────────────┴──────────────┐
             │                             │
             ▼                             ▼
   Outbound Competitor Agent       Inbound Seller Runtime
        子洋负责决策                  雅婷负责执行
                                     冠盛负责销售策略
                                     思棋负责情报产品
             │                             │
             └──────── 固定数据协议 ────────┘
```

- **Outbound**：主动体验、评价、排名和购买其他产品。
- **Inbound**：让其他 Agent 经我方节点执行 A2A Task，采集最小化的可观察事件，并自动交付 interaction trace/risk report。
- 两个方向在 Market Round 必须并发运行，不能因为我方 Agent 正在购物而停止接单。

---

## 4. 子洋：Competitor Agent Brain 与 Harness Engineering

### 最终责任

保证我方 Agent 能在无人干预的情况下完成整个 Arena，并作出高质量购买和排名决策。

### 必须完成

#### LangGraph Agent Brain

- 维护完整 LangGraph 状态机。
- 实现 Round 识别和流程切换。
- 实现产品发现、筛选和去重。
- Round 1 自动介绍我方产品。
- 选择至少 3 个不同产品进行真实调用。
- 将“执行探测”和“赛制要求的 critique”拆成不同节点：先记录成功、延迟、schema 和 receipt，再生成具体 disagreement。
- 对其他产品进行评分并提交 ranking。
- 保证主观 critique 不进入我方 interaction execution score。
- 与思棋共同冻结 InteractionEvent 输入、provenance 和 InteractionTraceReport 输出协议。
- Round 2 生成 80–100 credits 的购买计划。
- 保证至少购买 3 个不同产品。
- 根据价格、证据、信誉、延迟和任务价值计算 Expected Utility。
- 处理服务失败、超时、无效 JSON 和不可达产品。
- 使用 DeepSeek V4 处理文本判断，并保留低成本 fallback。
- 将预算、合规、交易状态等硬规则保留在确定性代码中。

#### Harness Engineering

- 建立正常成功场景。
- 建立服务调用失败场景。
- 建立 Critique 发布失败场景。
- 建立 Ranking 提交失败场景。
- 建立购买未结算场景。
- 建立可用卖家不足场景。
- 建立错误价格、重复 receipt 和 API 超时场景。
- 建立 Seller Harness，模拟多个 Agent 同时询价和购买。
- 建立两小时 Soak Harness，验证持续运行和故障恢复。
- 统计合规率、购买多样性、支出、收入、成交率和模型成本。

### 代码所有权

- `src/sharedos_commerce_agent/graph.py`
- `src/sharedos_commerce_agent/arena.py`
- `src/sharedos_commerce_agent/strategy.py`
- `src/sharedos_commerce_agent/model_client.py`
- `src/sharedos_commerce_agent/harness.py`
- `tests/test_graph.py`
- `tests/test_harness.py`
- Agent Brain 相关策略测试

### 完成标准

- 没有模型 API key 时，确定性 fallback 仍能完成最低合规动作。
- 所有正常和预期失败场景都能自动判断结果是否正确。
- Agent 不会购买自己、超预算或重复执行已完成副作用。
- Graph 可以流式输出当前节点和状态。
- 入站服务运行时，Outbound Agent 可以同时完成购买。
- 完整 dry run 不需要人工点击。

### 不负责

- 不直接维护生产数据库。
- 不负责 SharedOS Cloud 部署。
- 不自行修改已经冻结的 API 字段。
- 不负责最终产品定价和信誉权重。

---

## 5. 雅婷：SharedOS、SharedNet 与 Production Runtime

### 最终责任

保证产品被其他 Agent 找得到、调得通、买得到、收得到交付，并在整个 Arena 期间无需人工修复。

### 必须完成

#### SharedOS 与 SharedNet

- 将个人 Agent 注册到 SharedNet。
- 获取并验证 node ID。
- 将产品部署到 SharedOS Cloud。
- 实现最小权限 capability grant。
- 验证 discovery 和 invoke 分别受到授权控制。
- 保存必要的 authorization decision 和 audit reference。
- 对接官方最终 Arena endpoint 和 payload schema。
- 第一优先确认 SharedOS/A2A 是否提供 Task lifecycle hook、callback、认证身份或可信事件来源。
- 第一优先确认 Arena 是否独立提供 credits 结算 API、receipt 和幂等语义；我方不自建余额或托管系统。
- 明确数据可信度优先级：平台事件/签名 receipt > 双方共同确认 > 单方自报；输出中必须保留 provenance。

#### Commerce Runtime

- 实现服务目录和机器可读 description。
- 按官方合同适配 Quote、Order、Delivery 和 Receipt；没有官方字段时不得自行伪造已付款状态。
- A2A 层实现 task_created、request_received、task_started、artifact_delivered、task_completed、task_failed、disputed。
- 对官方支持幂等的副作用传递稳定 idempotency key，防止重复发布、购买或交付。
- 维护 SQLite；如果并发需要，再迁移 PostgreSQL。
- 实现 A2A Interaction Session 与可信 Event Ingestion，使经过我方节点的 Task 留下结构化证据。
- 对事件执行身份、授权、去重、阶段顺序和幂等校验。
- 实现 A2A Interaction Trace，并保存原始证据引用、hash 和 provenance。
- 实现 Reputation 查询接口。
- 只采集评分所需元数据，不默认保存 prompt、商业秘密或完整交付内容。
- 实现 health check、结构化日志和错误记录。
- 保证 Inbound Seller Runtime 与 Outbound Agent 并发运行。

#### 上线与无人值守

- 进行启动前配置检查。
- 自动检测模型、数据库、SharedNet 和服务端点状态。
- 对可安全重试的操作执行有上限的自动重试。
- 对付款和发布等副作用使用幂等恢复。
- 完成两小时持续运行测试。
- 准备 Arena 开始前执行的单条启动命令。
- Arena 开始后不依赖人工重启或手动修复。

### 代码所有权

- `src/sharedos_commerce_agent/api.py`
- `src/sharedos_commerce_agent/sharednet_adapter.py`
- `src/sharedos_commerce_agent/ledger.py`
- `src/sharedos_commerce_agent/seller.py`
- 数据库 schema 和 migration
- 部署、环境变量和运行配置
- Runtime/API 相关测试

### 完成标准

- 其他 Agent 可以发现并调用至少一项服务。
- 相同 idempotency key 不会重复产生我方副作用。
- 每个 Reputation 事件都能追溯到唯一 task、evidence ID 和 provenance。
- 能区分平台验证、双方确认和单方自报事件，不能把三者当作同等级证据。
- 重复、伪造或乱序 event 不会进入有效 trace。
- 未授权、超时和交付失败都有明确状态。
- 服务重启后已完成交易不会丢失或重复执行。
- Outbound Agent 只通过接口访问 Runtime，不直接访问数据库。
- 连续运行两小时没有阻断性错误。

### 不负责

- 不编写我方购买、排名和 Critique 策略。
- 不使用 LLM 决定付款、授权或最终交易状态。
- 不自行改变信誉评分和定价政策。
- 不负责营销话术。

---

## 6. 冠盛：Autonomous Seller、产品包装与提交

### 最终责任

让其他 Agent 在很短时间内理解为什么要让 A2A Task 经过我方观测节点、愿意购买，并能低摩擦地获得证据化报告。

### 必须完成

#### Agent-facing 产品设计

- 明确每项服务解决什么 Agent 痛点。
- 编写机器可读的服务名称、描述、输入 schema 和输出 schema。
- 确保 Agent 无需查看网页就能理解如何购买。
- 明确说明调用方需要提交哪些事件、哪些数据不会被采集，以及不同 provenance 对置信度的影响。
- 将长期 Reputation Network 愿景与 Arena 当晚服务区分开。

#### 自动销售策略

- 编写 20 秒以内的自动产品介绍。
- 编写不同买家目标对应的 Pitch 模板。
- 编写常见问题的自动回答。
- 编写针对价格、数据量、冷启动、刷分、隐私和“为什么要经你们节点”的 FAQ/Critique Defense。
- 定义首购优惠、套餐、Upsell 和拒绝不合理报价的话术。
- 与子洋一起把销售和答辩规则接入 Agent Brain。
- 与雅婷一起确认所有承诺都能由 Runtime 自动交付。
- 不宣称单笔 trace 等于全局信誉，也不宣称单方自报数据已经被平台验证。

#### 产品展示与比赛提交

- 制作最小 Dashboard，仅用于调试、截图和展示真实数据。
- 准备成功、失败和未授权交易各一个可复现示例。
- 负责最终产品介绍、截图和提交内容。
- 检查 Discord username、SharedNet node ID 和服务地址已经写入提交。
- 准备简短 Demo Script 和备用录屏，但 Arena 本身不依赖人工演示。

### 文件所有权

- 产品服务目录和描述
- Pitch、FAQ、Critique Defense 模板
- `catalog.json` 或对应服务配置
- Dashboard / Frontend
- 提交文案、截图和 Demo Script
- 最终提交检查表

### 完成标准

- 其他 Agent 仅阅读服务描述即可知道输入、输出、价格和价值。
- 所有宣传承诺都有实际 API 输出支持。
- 其他 Agent 能在一次机器可读交互内理解并提交合法 InteractionEvent。
- Agent 能自动回应至少五类常见 Critique。
- 每项服务的交付时间适合一小时 Market Round。
- 提交资料包含所有官方必填标识。
- 前端开发不会延误 Agent 服务上线。

### 不负责

- 不自行修改 Reputation 公式。
- 不把广告或付费会员包装成信誉结果。
- 不直接修改交易账本。
- 不在功能冻结后增加大型页面或新业务。

---

## 7. 思棋：Interaction Intelligence、Reputation 与商业机制

### 最终责任

保证我们的服务只根据可观察、可追溯的 A2A Task 事实生成可靠性结论，并正确表达样本量、来源和不确定性。

### 必须完成

#### 单次交互证据

- 冻结 InteractionEvent、InteractionTraceReport 和风险标记定义。
- 定义 task_created、request_received、task_started、artifact_delivered、task_completed、task_failed、disputed 的合法顺序。
- 定义完成度、Artifact 交付、延迟、schema 合规和争议的确定性计算。
- 区分平台验证、双方确认和单方自报证据，并定义不同证据权重。
- 明确单次报告只说明该次交互，不能代表全局信誉或 credits 结算。

#### Reputation 机制

- 新 Agent 可以显示 50 分，但必须同时显示 `Unrated` 和低置信度。
- 使用带先验的成功率，避免一次交易造成极端波动。
- 定义成功、失败、超时、争议和复购的影响。
- 定义样本量和置信度等级。
- 禁止自买自卖计分。
- 对重复低金额交易降权。
- 保证付费和排名完全分离，不能付费买高分。
- 为雅婷提供可直接编码的公式，为子洋提供可直接测试的样例。
- 定义 trace 纳入 ReputationSnapshot 的最低证据与去重条件。

#### 定价与收入策略

- 确定各项服务的基础价、底价和首购优惠。
- 优先提高成交数量和总收入，不只提高单笔价格。
- 保证价格适合其他 Agent 的 100-credit 总预算。
- 定义何时接受报价、何时反报价和何时拒绝。
- 对比不同价格策略在 Harness 中的成交率和收入。

### 具体交付物

- Reputation V1 公式和指标定义。
- Interaction Trace V1 公式和风险标记定义。
- 证据来源等级与置信度映射。
- 至少 10 个评分测试案例及预期结果。
- 基础反刷分规则。
- 三到四项 Arena 服务的定价表。
- 风险报告示例输出。
- 对外解释：评分代表什么、不代表什么。

### 完成标准

- 相同数据始终得到相同分数。
- 评分同时展示样本量和置信度。
- 0、1、10、100 次交互时的变化合理。
- 一次自报或重复交互不能显著提高信誉。
- 单次 trace 能产生有用结果，但必须显示 `single-interaction` 和 provenance。
- 每个推荐结果都能解释使用了哪些证据。

### 不负责

- 不直接修改 LangGraph 控制流。
- 不直接设计数据库表。
- 不通过 LLM 随机生成最终评分。
- 不负责 SharedNet 部署。

---

## 8. Arena MVP 服务目录

| 服务 | 解决的问题 | 建议价格 |
|---|---|---:|
| A2A Interaction Trace | 对方经我方节点执行 Task；验证阶段顺序、Artifact、延迟、schema 与 provenance | 5–7 credits |
| A2A Interaction Risk Report | 基于同一 trace 输出机器可读风险标记和证据引用 | 7–9 credits |
| Reputation Snapshot | 聚合多笔已验证 trace，输出分数、样本量和置信度 | 8–12 credits |

比赛期间优先保证前两项。Reputation Snapshot 必须在已有多笔 trace 时才生成；长期 Reputation Network 不得阻塞可出售服务上线。

## 9. 四人共同冻结的数据协议

### InteractionEvent

```json
{
  "task_id": "string",
  "subject_agent_id": "string",
  "stage": "task_created|request_received|task_started|artifact_delivered|buyer_acknowledged|task_completed|task_failed|disputed",
  "occurred_at": "ISO-8601 timestamp",
  "schema_valid": true,
  "evidence_id": "string",
  "request_hash": "string|null",
  "artifact_hash": "string|null",
  "provenance": "platform|observed|bilateral|self_reported"
}
```

### InteractionTraceReport

```json
{
  "task_id": "string",
  "subject_agent_id": "string",
  "completed": true,
  "delivered": true,
  "ordered": true,
  "schema_valid_rate": 1.0,
  "disputed": false,
  "end_to_end_latency_ms": 850,
  "execution_score": 93.2,
  "evidence_weight": 0.9,
  "confidence": "service-observed-single-interaction",
  "reputation_eligible": true,
  "credit_settlement": "not_evaluated",
  "provenance_counts": {"observed": 4},
  "evidence_ids": ["string"],
  "risk_flags": []
}
```

### ServiceEvaluation

```json
{
  "seller_id": "string",
  "service_id": "string",
  "listed_price": 10,
  "success": true,
  "latency_ms": 850,
  "evidence": ["string"],
  "limitations": ["string"],
  "receipt_id": "string"
}
```

### ArenaSettlementReceipt（仅在主办方提供时使用）

```json
{
  "trade_id": "string",
  "buyer_id": "string",
  "seller_id": "string",
  "service_id": "string",
  "amount": 10,
  "authorized": true,
  "status": "delivered",
  "latency_ms": 850,
  "schema_valid": true,
  "disputed": false,
  "created_at": "ISO-8601 timestamp"
}
```

### ReputationSnapshot

```json
{
  "agent_id": "string",
  "trust_score": 78.5,
  "confidence": "medium",
  "verified_interactions": 12,
  "success_rate": 0.917,
  "median_latency_ms": 1200,
  "repeat_buyer_rate": 0.33,
  "dispute_rate": 0.083,
  "updated_at": "ISO-8601 timestamp"
}
```

字段冻结后，新增字段可以，但删除和改名必须四人同步确认。

## 10. 开发顺序

### 阶段 A：先满足资格

- 雅婷完成 SharedNet 注册、node ID、SharedOS Cloud 基础部署。
- 子洋完成两个 round 的最低合规状态机。
- 冠盛完成至少一项可发现、可理解的服务描述。
- 思棋提供最小可运行的 Interaction Trace 评分、provenance 和风险标记规则。

### 阶段 B：跑通买卖闭环

```text
其他 Agent 发现服务
→ 自动询价
→ 自动下单
→ SharedOS 授权
→ A2A Task 事件经我方节点记录
→ 自动生成 Interaction Trace / Risk Report
→ 交付报告
→ 若 Arena 提供结算 receipt，再关联官方 receipt
→ 记录收入
```

同时跑通：

```text
我方 Agent 发现其他产品
→ 试用和 Critique
→ 排名
→ 规划消费
→ 购买至少三个产品
```

### 阶段 C：提高获胜概率

- 优化服务说明和自动 Pitch。
- 聚合多次 reputation-eligible trace，验证 Reputation Snapshot 的样本量和置信度。
- 对多个价格运行 Harness。
- 加入 Critique Defense 和 Upsell。

### 阶段 D：冻结与无人值守

- 停止增加新功能。
- 运行 Seller 并发测试。
- 运行两小时 Soak Harness。
- 运行完整无人干预 dry run。
- 完成最终提交和备用录屏。

## 11. Arena 开始前检查表

### 冠盛检查提交

- [ ] 已加入官方 Discord。
- [ ] 提交中包含正确 Discord username。
- [ ] 提交中包含正确 SharedNet node ID。
- [ ] 产品名称、描述、服务地址和价格正确。
- [ ] 在截止时间前完成提交。

### 雅婷检查运行环境

- [ ] Agent 已在 SharedNet 注册并可发现。
- [ ] 产品已在 SharedOS Cloud 运行。
- [ ] 至少一项服务可以由外部 Agent 成功调用。
- [ ] 已确认可信 Task 事件来自 lifecycle hook、认证请求、双方确认还是单方自报。
- [ ] 已确认 credits 结算是否由 Arena 提供，且我方没有伪造付款状态。
- [ ] 重复、乱序和伪造事件测试已通过。
- [ ] 数据库、模型和网络连接正常。
- [ ] Inbound 和 Outbound 可以并发运行。
- [ ] 自动恢复和幂等机制已启用。
- [ ] 两小时 soak test 已通过。

### 子洋检查 Agent

- [ ] Round 1 最少三个产品的流程已通过。
- [ ] Critique 是具体且基于真实输出的。
- [ ] Ranking 可以自动提交。
- [ ] Round 2 消费计划为 80–100 credits。
- [ ] 至少覆盖三个不同产品。
- [ ] 失败时会自动选择替代产品。
- [ ] 全流程不需要人工操作。

### 思棋检查产品机制

- [ ] Interaction Trace 评分和风险标记可以逐项解释。
- [ ] 单次交互只显示 `single-interaction`，不冒充全局信誉。
- [ ] provenance 和置信度规则已冻结。
- [ ] 没有付费买高分机制。
- [ ] 价格适合 100-credit 市场。
- [ ] InteractionEvent、InteractionTraceReport 和 ReputationSnapshot schema 已冻结。

## 12. 必须向主办方确认

官方页面目前存在信息不一致，应在 Discord 中确认：

1. 页面写“六项有效性要求”，但展开后只显示五项，第六项是什么。
2. 页面顶部显示 Friday, September 11, 2026，正文却写 Wednesday, September 11。
3. 最终提交截止时间和准确时区。
4. SharedNet 注册、node ID 和 Arena API 的正式说明。
5. Market Round 是否允许同一买家重复购买同一产品。
6. Credits 的报价、转移、退款和失败交易规则。
7. SharedOS 是否提供可信的交易 lifecycle event、callback 或签名 receipt；第三方节点是否允许参与或代理双方交易。

在得到答复前，以更早的截止时间和更严格的规则实现。

## 13. 协作规则

1. 每个文件只有一个主要负责人。
2. 所有跨模块通信使用冻结的结构化协议。
3. 子洋负责 Buyer/Competitor 策略；冠盛和思棋负责 Seller 策略；不得重复实现。
4. 雅婷负责所有真实外部副作用和幂等保障。
5. 模型不能直接决定付款、授权或最终信誉分。
6. 前端不阻塞 Agent 服务上线。
7. 任何阻塞超过 30 分钟的问题立即同步全组。
8. Arena 前完成无人干预测试，不把人工修复当作 fallback。
9. 不依赖多账号、自买自卖或未经确认的规则漏洞。
10. 优先级固定为：资格合规 > 服务可卖 > 自动交付 > 策略优化 > 页面美化。

## 14. 最终一句话定位

> **SharedOS controls what an agent is authorized to do. We help agents decide who is worth paying—and prove what happened after the trade.**

中文：

> **SharedOS 决定 Agent 是否有权执行；我们帮助 Agent 判断谁值得付费，并证明交易之后真实发生了什么。**
