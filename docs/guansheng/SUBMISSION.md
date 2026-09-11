## 十三 最终产品介绍与提交正文

### 1 中文产品介绍

A2A Interaction Intelligence 面向需要理解任务执行记录的Agent。调用方提交同一任务的结构化生命周期事件，服务返回完成、交付、顺序、时延、schema结果、执行得分、证据来源置信度和风险标记。我们将“记录描述了怎样的执行表现”和“记录来自多可信的来源”分开呈现，帮助调用方决定下一步应继续执行、排查问题还是索取更强证据。

当前两项服务为A2A Interaction Trace和A2A Interaction Risk Report，后者增加适用范围和逐项中英文风险解释，两项服务常规价均为6 credits、底价5。公共事件上报统一视为单方自报，不构成平台验证；服务不评估Arena credits结算，也不把一笔任务记录包装成全局信誉。长期的跨任务信誉网络，需要更多符合资格的可信证据后再建设。

### 2 Devpost英文正文

Project name

A2A Interaction Intelligence

Tagline

Understand one agent task through execution metrics, evidence confidence, and explicit limits.

Inspiration

Agents need more than a persuasive service description after a task. They need a compact account of what was reported, whether an artifact and terminal state were present, and how much confidence the evidence source supports. We focus on explaining one interaction before attempting broader reputation claims.

What it does

Our service turns structured A2A lifecycle events into a machine-readable interaction report. It separates execution indicators from provenance confidence and includes evidence references and risk flags. A2A Interaction Trace provides the report. A2A Interaction Risk Report adds scope boundaries and bilingual explanations for each actual risk flag in interpretation.flags. Both services normally quote 6 credits, with a floor of 5. Caller-submitted events stay self-reported, and credit settlement is not evaluated.

How it works

A caller selects a service, requests a quote, submits an order with a stable idempotency key and task events, and retrieves the report. The input covers one task and one subject agent, with a maximum of 200 events. The normal input uses metadata, evidence references, and optional hashes instead of raw prompts or full artifacts. Deterministic code calculates execution metrics and source confidence; commercial negotiation does not alter the result.

Why another agent would use it

The report gives another agent a consistent structure for task review, debugging, and evidence follow-up. It can distinguish a delivered analysis from an underlying task that failed. It can also show a strong-looking execution record with weak source confidence, reducing the risk that a single score is mistaken for global trust.

Current integration status

The current implementation has been exercised locally for successful task analysis, failed-task analysis, and a configured bearer-token rejection. These demonstrations do not establish live SharedNet reachability, SharedOS grant enforcement, or Arena credit settlement. The production deployment identifiers and audit evidence must be supplied before those capabilities are claimed.

What is next

We plan to connect trusted event ingestion and, when sufficient eligible evidence exists, build multi-interaction reputation views with sample size, provenance, and confidence. That future network is not part of the current single-interaction purchase.

### 3 可提交的服务清单段落

A2A Interaction Trace — Submit 1–200 lifecycle events for one task and one subject agent using the InteractionTraceInput schema. Receive completion, delivery, ordering, schema validity, reported latency, execution score, evidence weight, confidence, reputation eligibility, evidence references, and risk flags. Public submissions remain self-reported and credit settlement is not evaluated. Regular and first-purchase quote: 6 credits; floor: 5. A budget of 5 receives a 5-credit quote. Use the valid runtime quote and accepted final_price. SharedNet call: [填写真实节点与调用方式]. Delivery commitment: [填写已验证且不超过300秒的时限].

A2A Interaction Risk Report — Uses the same task input and report fields, with interpretation.meaning, interpretation.not_meaning and interpretation.flags containing per-flag Chinese and English explanations. The score describes the supplied task and neither verifies settlement nor establishes global reputation. It does not add a separate risk model. Regular and first-purchase quote: 6 credits; floor: 5. Use the valid runtime quote and accepted final_price. SharedNet call: [填写真实调用方式]. Only list this service when its additional explanation is useful to the buyer.

## 十四 提交标识核对与最终检查

### 1 必填标识检查结果

| 提交字段 | 当前应填写的值或状态 |
|---|---|
| 队长Discord username | 待提供真实用户名 |
| 个人Agent SharedNet node ID | 待提供真实节点ID |
| 服务调用地址与方式 | 待提供真实SharedNet入口 不能用localhost代替 |
| SharedOS purpose string | 待提供实际审计可检索值 |
| 产品Agent地址 | 待提供实际地址列表 |
| 仓库链接 | https://github.com/yixi1120/Shared-OS-Hackathon |
| 文稿采用的代码版本 | main 3b5b99d 冠盛新增材料基于此版本 |
| 冠盛交付包 | Guansheng-v3 基于最新main的新增材料 待合并 |

上述未填写项不能通过猜测补齐。提交正文已经留出准确字段位置，但现阶段不能勾选“标识全部写入”。取得真实值后逐项填写，并核对节点、服务目录、审计与视频中的标识一致。

### 2 冠盛最终提交检查表

□ 产品名称与最新service_id一致，废弃的旧服务名已经清除。

□ 服务清单可让Agent仅凭目录理解输入、输出、价格和购买顺序。

☑ 本地目录与Runtime已对齐思棋最终价格，首购无整数额外优惠；雅婷的线上部署确认仍待完成。

□ 队长Discord、node ID、purpose、产品Agent地址及真实调用方式已经填写并核验。

□ 报告始终区分执行分、来源置信度、信誉资格和结算状态。

□ 所有宣传承诺有实际Runtime输出或线上运行证据支撑。

□ 子洋已签收销售和FAQ规则，雅婷已签收承诺矩阵。

☑ Dashboard源码随包交付，并通过本地真实API链路验证；线上地址与部署由雅婷确认后补入。

□ 成功、失败与未授权例的证据已保存；平台授权例有真实审计。

□ 正式视频不超过2分钟，备用文件可播放，Arena不依赖人工演示。

□ 比赛日期、缺失规则及有效credits口径已按最终公告确认。

□ 在真实截止时间前提交并保存平台回执。

