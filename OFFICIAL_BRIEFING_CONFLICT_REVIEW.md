# 官方 Office Hour 与当前方案冲突检查

> 日期：2026-09-10  
> 来源：《智能纪要：黑客松活动规则与工具讲解 2026年9月10日》  
> 用途：团队内部对齐，不替代主办方最终规则

## 1. 结论

官方讲解没有推翻我们的产品方向，当前的 **Verified A2A Interaction Intelligence**、LangGraph 策略控制、幂等恢复和 Harness 都可以保留。

但有两处需要调整：

1. 进入 Arena 的应当是团队唯一的代表 Agent。我们的 Python LangGraph 应定位为该 Agent 背后的策略与合规引擎，不能注册成第二个参赛 Agent。
2. 最终产品不能要求客户手工构造完整 InteractionEvent 列表。其他 Agent 应只需提交普通任务；事件应由经过我方节点的真实 SharedOS/SharedNet 执行过程自动生成。

此外，需要补充明确的免费/收费边界，并尽快确认准确比赛时间、SharedNet 房间接入方式和 credits 结算协议。

## 2. 本次官方讲解确认的规则

- 黑客松从周五上午开始，到周日晚上 11 点结束。
- 周六晚上 9 点安排 Office Hour。
- 竞技场暂定周日晚上 9 点至 11 点：
  - 9:00-10:00：Agent 互评产品；
  - 10:00-11:00：Agent 消费和 credits 竞争。
- 每支队伍只能派 1 个 Agent 进入竞技场。
- 参赛邮箱绑定后获得 100 个初始 Arena credits。
- 一个 Agent 可以对应多个产品，数量没有上限。
- SharedNet 类似 Agent 之间的线上会议系统，官方会提供房间链接。
- 产品应当可以被其他 Agent 直接使用，并尽量降低调用门槛。
- 产品开发初期应明确免费和收费的边界。
- 建议优先部署到云端，可使用 SharedOS Cloud 或其他云端部署方式。
- 官方计划给每位参赛者提供 100 美元 SharedOS Cloud 额度。
- 大模型 token 和额外算力合作仍待官方后续确认。

注意：纪要末尾注明部分内容可能由 AI 生成。涉及日期、时区、产品名称和网站名称时，应以官方群最新公告、官网规则或主办方书面答复为准。

## 3. 与当前方案一致的部分

| 官方要求 | 当前状态 | 判断 |
|---|---|---|
| Round 1 体验并评价其他产品 | 已实现真实调用、证据记录、Critique 和 Ranking | 一致 |
| Round 2 使用 100 credits 消费 | 已按 100 credits 生成购买计划 | 一致 |
| 产品从第一天考虑收费 | Interaction Trace 和 Risk Report 已有 6/8 credits 定价 | 基本一致 |
| 产品可以被 Agent 调用 | 已有机器可读 API 和结构化输出 | 基本一致，最终入口仍需简化 |
| 一个 Agent 可提供多个产品/服务 | 当前提供两个主要服务 | 一致 |
| 竞技期间无需人工操作 | LangGraph、checkpoint、幂等恢复和 Harness 已实现 | 一致 |
| 产品部署到云端 | 已分配给雅婷负责 | 尚未完成，不是方向冲突 |
| 失败和超时应可恢复 | 已覆盖超时、回包丢失、重复 Receipt 等场景 | 一致 |

## 4. 必须调整的地方

### 4.1 参赛 Agent 身份

官方要求每队只能有一个 Agent 进入 Arena。团队应使用子洋现有的 Codex 作为唯一代表 Agent。

正确结构：

```text
团队唯一参赛 Codex
        |
        v
LangGraph Strategy & Compliance Engine
        |
        +-- 产品发现与真实试用
        +-- Critique 与 Ranking
        +-- 购买计划与预算检查
        +-- checkpoint 与幂等恢复
```

禁止结构：

```text
Codex 进入 Arena
+
另一个 Python Agent 也作为独立身份进入 Arena
```

因此不需要删除 LangGraph，但对外应将它描述为 **Arena Strategy & Compliance Engine**，而不是第二个参赛 Agent。

### 4.2 最终 Seller 调用方式

当前临时 API 让调用方提交完整事件列表：

```json
{
  "events": [
    {"stage": "request_received"},
    {"stage": "task_started"},
    {"stage": "artifact_delivered"},
    {"stage": "task_completed"}
  ]
}
```

这种方式适合 Harness、schema 测试和 fallback，但不适合作为最终 Arena 主入口：

- 其他 Agent 的调用成本过高；
- 调用方自己提交的事件只能被标记为 `self_reported`；
- 无法体现“任务经过我方节点，我们自动得到执行证据”的核心价值。

最终主流程应为：

```text
其他 Agent 提交普通任务
        |
        v
任务经过我方 SharedOS 节点执行
        |
        v
节点自动记录最小化的可信事件
        |
        v
生成 Interaction Trace / Risk Report
        |
        v
向调用方交付 Artifact
```

目标是让调用方通过一句 prompt 或一次服务调用完成整个过程，而不需要理解内部事件协议。

### 4.3 免费与收费边界

官方要求在产品开发初期明确免费与收费机制。建议冻结为：

**免费部分**

- 服务发现和 Catalog；
- 产品说明、输入输出 schema 和示例；
- Quote/询价；
- 一条简短风险预览。

**收费部分**

- 完整 A2A Interaction Trace；
- 完整 Interaction Risk Report；
- Artifact hash、证据引用和风险标记；
- 满足可信来源条件后，可进入 Reputation 聚合的验证结果。

任何收费动作都必须由 Arena 官方 credits 机制确认。没有可信回执时，我们继续输出：

```text
credit_settlement = not_evaluated
```

### 4.4 SharedNet 接入边界

官方讲解把 SharedNet 描述为房间式 Agent 交互，并表示会提供可复制到当前 Agent 会话的房间链接。这意味着最终接入不一定是我们此前假设的普通 REST marketplace API。

当前 `ArenaClient` 抽象可以保留，但 `HttpArenaClient` 不能猜测 endpoint。拿到官方链接和操作说明后，再决定适配方式：

- SharedNet room/message 工具；
- 官方 MCP/skill；
- 官方 HTTP API；
- 或由 Codex 在房间内直接调用的命令。

LangGraph 的策略、状态和 Harness 不依赖具体传输协议，因此不需要重写核心逻辑。

## 5. 当前不存在冲突的设计

以下部分应继续保留：

- 一个统一的 `agent_id`；
- Critique 与客观 Interaction Score 分离；
- 100-credit 硬预算；
- 至少三个不同产品/卖家的严格策略；
- 购买、Critique、Ranking 的稳定幂等键；
- SQLite checkpoint 和跨进程恢复；
- 单方自报事件不能升级为可信 evidence；
- Artifact 交付和 credits 结算分离；
- Arena 故障 Harness、Seller 并发 Harness 和 Soak Harness。

其中“至少体验三个产品、至少消费 80 credits、至少购买三个产品”比本次纪要中的概述更严格。由于此前官网详细规则包含这些要求，在主办方否定前应继续按照更严格版本实现。

## 6. 官方信息中需要确认的矛盾

### 6.1 日期和时区

本次纪要表示 Arena 为周日晚上 9 点至 11 点；此前活动页面同时出现过 Friday、Wednesday 和美东时间描述。

必须取得主办方书面确认：

- 开发截止时间；
- 项目提交截止时间；
- Arena 的准确日期；
- Arena 的准确时区；
- 房间链接发布时间。

在确认之前，团队应按照最早可能截止时间准备。

### 6.2 云端部署要求

纪要表示可以使用 SharedOS Cloud，也可以部署到其他通用云；官网详细材料强调 Built on SharedOS 和 audit trail。

建议采用最严格、也最兼容的解释：

```text
部署位置可以是 SharedOS Cloud 或其他云；
但产品仍必须运行 SharedOS 相关 turn，并留下可验证 audit trail。
```

### 6.3 Credits 交易合同

官方表示 credits 相关网页后续发布。目前仍需确认：

- Quote、购买、扣款和交付的正式顺序；
- 成功、失败、退款和争议的状态定义；
- 是否提供签名 Receipt；
- 是否支持 idempotency key；
- 买方重复购买同一服务是否允许；
- 哪个事件才算入 Top Earner 收入。

## 7. 调整后的比赛架构

```text
                     SharedNet Arena Room
                              |
                  唯一参赛 Agent：Codex
                              |
             +----------------+----------------+
             |                                 |
             v                                 v
  LangGraph Strategy Engine          SharedOS Product Runtime
  - discover / evaluate              - 免费 discovery/preview
  - critique / rank                  - 收费 trace/risk report
  - purchase planning                - 自动事件采集
  - audit / recovery                 - Artifact 交付
             |                                 |
             +----------------+----------------+
                              |
                     固定结构化数据协议
                              |
                 Harness / Audit / Checkpoint
```

## 8. 四人下一步

### 子洋

- 对外将 LangGraph 定位为策略与合规引擎，而非第二个 Agent。
- 保持一个统一参赛 `agent_id`。
- 拿到 SharedNet 真实操作方式后完成 contract test。
- 运行正式两小时 Soak Harness。
- 继续保证 Round 1 和 Round 2 的硬规则自动执行。

### 雅婷

- 尽快取得官方房间链接、账号/tenant 信息和真实接入说明。
- 跑通 SharedOS 最小 turn 和 audit trail。
- 确认部署在其他云时如何证明 Built on SharedOS。
- 把真实 SharedNet 输入、输出、身份和 credits 回执格式提供给子洋。
- 实现从可信运行环境自动生成 InteractionEvent 的入口。

### 冠盛

- 将免费/收费边界写入产品描述和销售 Pitch。
- 把两个付费服务分别写成 Agent 能直接理解的一段话。
- 强调调用方无需手工构造事件，最终只需提交普通任务。
- 准备一分钟以内可被 Agent 阅读的产品说明。

### 思棋

- 保持 Interaction Trace 只使用可观察事实。
- 明确 `self_reported`、`observed`、`platform` 的可信度差异。
- 冻结付费报告的输出字段和风险标记。
- 不把 Critique、广告、购买金额或未验证付款写入 Execution Score。

## 9. 建议发给主办方的问题

```text
您好，我们想确认几个 Arena 接入和时间问题：

1. 请问 Arena 对应的香港时间准确日期和时段是什么？项目提交截止时间是什么？
2. 每队只能有一个 Agent 入场时，是否可以让该 Agent 调用团队自己的 LangGraph 策略工具？
3. SharedNet 最终通过房间链接、MCP/skill 还是 HTTP API 操作？
4. 产品部署到其他云时，只要仍使用 SharedOS 并保留 audit trail，是否符合要求？
5. Credits 的 quote、purchase、delivery、receipt 和 idempotency 规范何时发布？
6. Top Earner 统计的是已扣款、已交付，还是其他状态的 credits？
```

## 10. 当前团队冻结决定

在主办方进一步确认前，团队统一采用以下原则：

1. 只让一个 Codex 身份进入 Arena。
2. LangGraph 作为该 Codex 的策略与合规工具。
3. 产品必须能被其他 Agent 一次调用，不要求客户理解内部事件协议。
4. 免费 discovery/preview，收费完整 trace/risk report。
5. 没有 Arena 官方回执时，不声称付款成功。
6. 部署方案必须能够证明 SharedOS 使用记录和 audit trail。
7. 按更早截止时间和更严格规则准备。

