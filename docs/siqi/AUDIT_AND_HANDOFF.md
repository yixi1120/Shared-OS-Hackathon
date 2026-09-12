# 思棋核查与跨团队交接

历史记录：本文重复计数与缺资料结论来自早期基线；当前事件去重修复见[EVENT_IDENTITY_CHANGE.md](EVENT_IDENTITY_CHANGE.md)，最新交付入口为[README.md](README.md)。

## 执行摘要

在隔离本地 clone 核查 main `566b54e`（Harden purchase recovery with bilateral reconciliation），初始工作树干净。没有覆盖队友工作、提交远程、注册部署、改变 LangGraph 或数据库。此次冻结单次报告而非全局信誉。正式依据为当前代码；旧材料冲突逐项如下。

## 发现的冲突与材料缺口

| 材料 / 位置 | 冲突 / 缺口 | 处理 |
|---|---|---|
| 请求中的 TEAM_RESPONSIBILITIES(2).md、OFFICIAL_BRIEFING_CONFLICT_REVIEW(1).md | 仓库只有无编号文件，无法确认是否相同修订 | 已读取无编号版本；不声称核对过未提供修订 |
| 《冠盛产品设计与自动销售交付手册》 | 仓库及当前工作材料中未找到 | 无法逐句核对；本交接提供替代可用话术，需冠盛补手册再比对 |
| TEAM_RESPONSIBILITIES 产品定位 | “Verified”、经节点自动采集与公共自报 API 不符 | 当前应称结构化单次任务分析；可信自动采集是待接入 |
| OFFICIAL_BRIEFING_CONFLICT_REVIEW §4.2/§10 | 普通任务一次调用是目标；当前要求 events | 不能宣传普通任务自动执行已实现 |
| TEAM_RESPONSIBILITIES 阶段枚举 | 漏 quote_declared | 以 models.py 九阶段为准 |
| TEAM_RESPONSIBILITIES 报告示例 | 850ms 全成功示例 93.2 不符合公式 | 若 schema=1 且 ordered，无争议应 99.58；不是 93.2 |
| 当前成功/失败示例 | 98、43 依赖 4 秒；原 malformed 测试为22.33，Seller Harness成功99.6 | 保留各自输入，新增准确98/43 API演示测试 |
| seller.py / strategy.py | Catalog 6/8 与 Runtime 默认12/13；budget未参与 | 已获确认并统一本地Catalog/Runtime为6/6、底价5，部署前不声称远端已更新 |
| Risk Report | 原先仅两句解释，Catalog却提 score breakdown | 新增逐flag解释；不声称已输出结构化逐项score breakdown字段 |
| telemetry.py 旧风险列表 | 无失败、开始缺失、延迟缺失、证据缺失、来源弱、结算状态单独标记 | 新增7项，保留原六项及评分 |
| TEAM_RESPONSIBILITIES 去重/拒绝乱序承诺 | evaluator会评分乱序，重复仍计数；订单幂等不是事件去重 | 记录V1行为，未来聚合必须再查重 |
| reputation_eligible | 只有终态+来源；无证据ID、身份、自交易检查 | 保留基础候选语义，禁止只凭bool正式入库 |
| TEAM_RESPONSIBILITIES Snapshot/50分Unrated/多SKU | 当前未实现也不应销售 | 本次明确撤销当前售卖口径，历史规划保留为历史 |
| OFFICIAL_BRIEFING_CONFLICT_REVIEW 免费风险预览 | 当前无专门 preview endpoint | 仅发现、health、quote已实现；不承诺免费风险预览已上线 |
| provenance / confidence | evaluator信任内部枚举，不实际验签；schema_valid默认true | 公共仍全self-reported；权重不是概率/独立校验结果 |
| Catalog reputation=.8/.78 | 静态listing字段，不是多笔聚合结果 | 不可作为产品生成的全局信誉营销 |
| Token 401 与正式平台授权 | 本地Bearer测试无 capability grant/audit proof | 平台认证仍需真实来源，不把Mock IDs当真实记录 |
| seller_harness declared_credits | 模拟订单声明额，不是平台到账 | 测试收入不作为Top Earner线上成交证明 |

README / 分工文件 / 冲突审查 / 子洋 playbook 已增加醒目链接，将此次规范标作当前单次报告与产品边界依据；保留历史文本用于追溯。未重新核验官方最新赛程与资格，不能仅从代码宣布 Arena 资格已满足。

## 已实现与未实现

已实现并测试：本地 FastAPI Catalog/Quote/Negotiation/Order/Delivery、参数约束、Token入口、订单幂等、确定性评分、自报降级、Risk解释、单次报告；仓库也有Outbound LangGraph、适配器及恢复测试。本次全量测试包含这些测试，未改变其行为。

仍未由本次证据证明：真实SharedOS部署和持续在线、官方audit/grant、普通任务可信采集、平台来源签名核验、credits真实到账、Reputation网络/查询/聚合、防自买自卖正式身份服务、线上销量或两小时实际Soak。没有伪造endpoint、node ID或审计引用。

## 给雅婷

- 字段/阶段/缺失处理见 INTERACTION_REPORT_V1.md §1–2；机器schema见 schemas.json。Risk interpretation.flags 是新增数组，保留 meaning/not_meaning。
- 公式为 clamp 后 round(40C+15D+15O+20V+max(0,10−L/2000)−25U,2)，缺L延迟项0；V用未四舍五入比例。
- provenance platform/observed/bilateral/self_reported 对应1/.9/.6/.15，混合取最小；公共入口禁止升级。
- Risk条件见§4和risk_rules.py；没有额外扣分。
- eligibility保留终态+全platform/observed；未来正式纳入须按§6认证身份、可解析证据、查重及排除自交易。不要仅看bool写入全局信誉。
- 最终价格已获思棋确认：本地Catalog/Runtime均为6/6、底价5；预算<5拒绝，预算5直接报5。见PRICING_DECISION.md。尚未部署。

## 给子洋

- 固定输入events和输出报告见schemas.json；tests/fixtures/interaction_v1.json是17个完整预期结果，TEST_MATRIX.md是可读表。所有案例重复运行应完全一致。
- 成功98、失败43与低证据.15必须分别展示。失败分析报告仍正常交付，两SKU均有API测试；Token测试不当平台审计。
- 新版本按quote的ask/floor接受，低于floor第一次反价floor、第二次拒绝并关闭；预算<5拒绝。旧quote仍按原条款议价。
- Critique、Ranking、广告、金额、付费、优惠、会员、未验证结算、Evidence Weight全部禁止进入Execution Score。Expected Utility与Ranking属于另外的策略评分。
- 回归要保留当前重复计数、最弱来源和相同时间稳定排序语义；后续若修改这些规则，必须同步升级版本与 golden fixtures。

## 给冠盛

可说：“分析你提交的单次任务事件，返回完成、交付、顺序、schema声明比例、记录时延、执行分、证据来源权重和风险标记。Risk Report在同样指标上增加逐项解释。单方自报即使98分，来源权重仍为0.15。”

不可说：已验证平台任务/全局信誉、付费提升可信度、已结算、Token拒绝等于SharedOS grant审计、无需events即可自动运行普通任务、静态Catalog reputation是真实信誉、已有Snapshot可购买、模拟订单是真实成交。evidence_weight不是真实性概率。

产品差异：Trace含全部核心指标和风险；Risk额外含固定双语解释，不能以“购买Risk才能看到真实风险”诱导重复收费。暂不开放套餐。新政策已批准，本地实现完成；部署新版本后使用PRICING_DECISION.md统一话术。请补交原销售手册核查具体承诺。

## 剩余决策与下一步

1. 思棋已确认6/6、底价5、取消乘数、预算及议价规则；本地统一与测试完成，后续由团队部署。
2. 冠盛提供缺失手册和编号材料；雅婷提供真实审计与结算合同，才能升级来源或证明正式能力。
3. 主分支合入已处理冲突终态和时间验证；后续版本仍需处理重复证据、schema可信度和任务SLA。
