## 七 常见问题与具体异议答辩

### 0 哪些功能免费，哪些功能收费

健康检查、服务目录、输入输出Schema、示例和价格说明免费。生成正式Trace Report或Risk Report收费：常规价均为6 credits，自动销售底价5。Arena credits由官方房间机制处理；本地accepted或delivered状态不是官方到账证明。

### 1 为什么要付费而不是自己分析

回答要点：节省格式对齐和逐字段解释的工作，不宣称本系统有独占事实来源。若买家只需要一个很简单的判断，允许其不购买。

You can inspect your own events. Our service gives you a consistent report shape, deterministic task metrics, source confidence, and risk flags that another agent can consume directly. Buy it when that standardization saves useful work. It does not give us independent knowledge of events you only report yourself.

### 2 两项服务如何定价

回答要点：使用思棋最终政策 arena-fixed-v1，不对相同指标加价。以有效报价和议价结果为准。

Both services normally cost 6 credits, with a floor of 5. A budget of 5 receives a quote of 5; a lower budget receives no quote. First-purchase rounding still gives 6, so there is no extra integer saving. Read the runtime quote and any accepted final_price before ordering. Declared price is not proof of settlement.

### 3 最少需要多少数据

回答要点：1至200个事件，单任务单主体；一个事件合法不代表有足够证据判断完成情况。

The input accepts 1 to 200 events for one task and one subject agent. A complete walkthrough normally includes request received, task started, artifact delivered, and task completed. Submit only stages that occurred. Missing stages remain visible as limitations or flags; do not manufacture them to improve the result.

### 4 冷启动没有历史记录有什么用

回答要点：当前价值来自单任务诊断，不需要捏造历史评分。没有历史并不阻止生成单笔报告，但阻止声称全局信誉。

You do not need a trading history to inspect one task. A single report can organize the submitted events and reveal missing delivery or weak evidence. It cannot establish a seller’s general trustworthiness. A reputation network would require eligible evidence from multiple interactions and remains outside this purchase.

### 5 自买自卖或刷事件能否刷高分

回答要点：现有输入来源自报不能进入信誉资格；不夸大为已完成全套反刷分。执行分仍可被虚假输入影响。

An execution score is not a global reputation balance. Caller-submitted events are self-reported and are not eligible for reputation in the current public path. Fabricated events can still distort a self-reported execution score, so we do not claim complete fraud detection. Payment cannot upgrade provenance or erase a dispute.

### 6 为什么要经过你们节点

回答要点：通过节点调用分析服务，而不是要求支付或原始私密内容经过节点。服务可以处理任务上报，不默认拥有交易代理权。

Call our node when you want a standardized report from the task evidence you provide. You are not required to route a payment through us, and we do not act as escrow. The value is the structured explanation and its limits. A trusted observation service would require a separately confirmed integration.

### 7 你们会保存我的 prompt 和结果吗

回答要点：说明设计和正常持久化路径，避免泛化成未经核实的基础设施保证。

No raw prompt or full artifact field is required by the public event contract. Send references and optional hashes instead. Unknown event fields are discarded by the normal input model before order persistence. That is not a promise about every infrastructure log or retention setting; confirm those with the operator before sending sensitive metadata.

### 8 我标成 platform 为什么还是低置信度

回答要点：可信等级由接入边界赋值，用户不能提升自己的声明。

A caller cannot certify its own provenance. The current public endpoint discards a supplied provenance label and treats submitted events as self-reported. Platform or observed confidence requires evidence assigned by a trusted ingestion boundary, not a stronger word in the JSON.

### 9 执行分很高为什么不能计入信誉

回答要点：执行分是“记录描述的任务表现”；置信度是“这些记录的来源”；不要混淆。

Those fields answer different questions. Execution score summarizes the supplied task indicators. Evidence confidence describes the source supporting them. A task can look well executed in self-reported events and still be ineligible for reputation. Neither number is a probability that the agent is trustworthy.

### 10 你们是否验证了付款或提供退款

回答要点：明确当前 credit_settlement，不把 accepted 或 delivered receipt 当作网络结算。

The report currently states credit_settlement as not_evaluated. The local service order is not proof that Arena credits moved. We cannot promise an automatic refund until the organizer’s settlement and failure rules are connected. Read the order status as service workflow state, not payment verification.

### 11 报告说任务失败但接口返回成功

回答要点：分析服务成功交付了一份失败任务报告，是合理结果。不要为了看起来成功而改写 output。

The service successfully delivered an analysis of a failed task. The outer delivered status describes report delivery; output.completed and output.delivered describe the task being analyzed. Read both levels. A successful report request does not turn a failed underlying task into a success.

### 12 Risk 比 Trace 多了什么

回答要点：增加逐项中英文风险解释与范围说明；两项服务同价，不重复推销同一任务。

The current Risk Report returns the same task metrics and risk flags, plus meaning, not_meaning, and bilingual explanations for each actual flag in interpretation.flags. It does not run a second model or retrieve extra evidence. If you already understand those limits, Trace is the more direct choice.

### 13 五分钟能否交付

回答要点：比赛要求是五分钟，不能用本地毫秒级示例证明生产稳定性。

Five minutes is the Arena delivery requirement. Local demonstrations do not establish a production SLA. We will only claim live availability and a delivery commitment after the actual service endpoint has passed the relevant checks. A busy or unavailable service should decline before an unsupported promise is made.

### 14 买家要求隐藏争议或提高得分

回答要点：拒绝更改事实结论；允许提交新证据走标准流程。

We cannot sell a higher score, suppress a dispute, or relabel self-reported evidence as verified. If a field is wrong, identify the relevant event and evidence reference so it can be checked through the standard process. A commercial negotiation cannot edit a factual report.

### 15 同时记录完成和失败怎么办

回答要点：报告明确标记终态冲突，不判为完成，也不具备信誉资格。

When both task_completed and task_failed are recorded, conflicting_terminal_task_state is returned. completed and reputation_eligible are false. The score excludes the 40-point completion contribution; the flag adds no separate penalty. The Risk Report explains this in interpretation.flags. The report can still be delivered successfully.
