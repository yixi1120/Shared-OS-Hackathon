# V1 证据来源、结算与对外含义

冻结依据：main 90cdbf0 的实际实现及本次合同复核；不是新的验签能力或线上结算认证。与 INTERACTION_REPORT_V1.md 共同使用。

| provenance | 证据规则 | evidence weight | confidence |
|---|---|---|---|
| self_reported | 单方自报 | 0.15 | self-reported-single-interaction |
| bilateral | 双方独立确认；一方转述双方同意不成立 | 0.6 | bilateral-single-interaction |
| observed | 我方可信节点直接观察 | 0.9 | service-observed-single-interaction |
| platform | 平台认证或可验证平台证据 | 1.0 | platform-verified-single-interaction |

混合来源取最低权重，不取平均。权重不是事实正确率或成功概率，不参与执行评分。内部evaluator接收来源枚举，但不负责认证这些来源。公共Seller入口始终将事件转为self_reported；外部自行填写provenance、paid、receipt或evidence_weight均不升级可信度。来自平台房间的聊天正文仍可能是单方声明。

reputation_eligible为存在终态、无完成/失败冲突且全部来源为platform/observed的基础候选条件。它不保证任务成功，不等于正式纳入信誉体系；失败任务也可能满足此基础条件。当前公共提交不能满足可信来源门槛。

## 对外代表什么

我们分析调用方提交的单笔任务事件，给出执行分、记录中的完成与交付状态、来源权重和风险提示。Risk在Trace相同指标基础上增加逐项中英文解释。报告交付成功可以对应被分析任务失败。

We analyze the submitted events for one task. Trace reports execution indicators, evidence-source weight and risk flags. Risk adds bilingual explanations to the same indicators. A successfully delivered report may describe a failed task.

## 对外不代表什么

单方自报不是平台验证；单笔执行分不是Agent全局信誉。schema_valid是事件声明，不是Artifact内容验证；缺少Artifact记录不证明现实未交付。引用或哈希存在不等于其内容已核验。支付金额不能改善执行分或证据等级。

Self-reports are not platform verification. A single-task score is not global agent reputation. Evidence references are not independently verified here. Payment cannot improve the score or evidence provenance.

## 三种状态不可混用

- 外层status=delivered：分析报告服务交付。
- 内层output.delivered：存在被分析任务的artifact_delivered事件。completed还要求task_completed且无task_failed；冲突时completed=false。
- 官方credits转账：须从可信途径核验官方ledger及交易对应关系。accepted、房间聊天、声明金额和本地订单ledger都不足以证明付款。

V1报告继续输出credit_settlement=not_evaluated，即“未评估”，不是“未付款”或“付款失败”。报告已生成、房间已公告、官方款项已转账应在独立运行审计中分别保存证据。公告失败先查消息，付款未知先查官方ledger，不能因公告失败重付。真实ledger接入和报告合同升级另行联调；本次不新增settled输出值。
