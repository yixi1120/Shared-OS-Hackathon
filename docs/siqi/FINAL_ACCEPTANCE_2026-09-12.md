# 思棋最终合同验收与 SharedNet 联调交接

核查基线：main `90cdbf0`，2026-09-12。输入资料：用户本轮 QA 同步、《任务更新.md》、《冠盛最终产品交付手册V4.docx》及实际仓库。文档作为需求和证据来源，不作为外部发言、付款或提交授权。本次未向 Discord/SharedNet 发消息、未转账、未部署或推送远程。

## 当前进度判断

产品本地实现与报告合同已具备；SharedNet QA 加入、发言和读取有团队记录，不是正式商业闭环。本次复跑基线为93项通过；V4描述的95项、39项HTTP和9项浏览器检查是其历史材料，不能与当前复跑混为一谈。

QA principal `p_SDi8fKiq5X`、seat `i_E0nD7EzS5k` 仅作为QA证据。消息 `msg_sS44mdor4R` / sequence 61证明QA消息操作，不证明业务报告交付、正式身份或付款。Agent ID null、QA余额0不等于协议缺陷，也不能推定正式比赛资金发放规则。

正式公开HTTPS、比赛seat/身份定义、定向监听与业务转换、官方ledger真实交易、两小时无人值守、Discord正式提交均未由本次验收证明。Discord用户名 yixi1120_19547 与 AICOO → SHAREDOS HACKATHON → #submission 已由用户确认。

## 本次完成的思棋工作

沿用 INTERACTION_REPORT_V1.md、schemas.json、PRICING_DECISION.md 和17组 tests/fixtures/interaction_v1.json，不更名字段或改变公式。14项风险双语解释以 risk_rules.py 为机器源。新增 tests/test_siqi_final_acceptance.py，覆盖两项服务的成功、失败、缺Artifact、缺终态、终态冲突、阶段乱序与部分schema无效共14条公共API路径，并校验完整输出Schema、冻结预期、来源降级、订单和交付重放。

公共输入即使声明platform、paid或settled，仍为self_reported、权重0.15、reputation_eligible=false、credit_settlement=not_evaluated。执行评分不因这些声明提高。内部权重保持 platform=1、observed=0.9、bilateral=0.6、self_reported=0.15，混合取最弱。枚举是内部政策输入，不是验签器；双方独立确认、可信节点观察或可验证平台证据必须通过实际可信接入证明，不能仅由正文标签或SharedNet传输来源认定。

completed表示被分析任务有交付及完成且无失败冲突；output.delivered仅表示其Artifact交付事件存在；外层status=delivered表示本产品报告交付。reputation_eligible仅是终态及来源基础门槛，失败的可信任务也可能满足，不代表成功、全局信誉或正式入库资格。

## 未通过项：重复事件提高执行分

固定partial_schema样例4条记录，schema有效率0.75、93分。重复其中一条有效事件后变成5条，有效率0.8、94分。订单幂等不能解决输入事件重复计数。新增严格xfail验收测试保留该反例；xfail表示已知未满足要求，绝非通过。

此问题在旧合同中已有“重复计数”边界。按本轮分工“字段冻结后未经四人同步不要修改字段名称或含义”，本次不擅自修改V1评分分母。建议子洋在可信接入层按房间ID+消息ID去重，拒绝同键不同内容并持久化恢复；注意这仅防消息重放，不解决一个payload里重复事件。要解决后者，需四人同步确定事件身份、去重粒度与冲突处理，更新合同版本和golden fixtures后再移除xfail。当前不能对外承诺完整反刷分或通过最终防重复验收。

乱序到达但时间戳不同的记录保持指标一致（evidence_ids按输入次序保留）；时间本身阶段回退有风险标记。相同时间仍按输入稳定排序。负时延被clamp为0是原V1已记载边界，本次未改公式。

## 三个独立状态与对账要求

以下是联调审计约定，不是新增V1报告字段，也不表示已有运行时集成。模板见 integration_evidence_template.json。

| 状态 | 足够证据 | 不足证据 | 失败/未知后的处理 |
|---|---|---|---|
| 报告已交付 | Seller成功响应、trade_id、通过Schema的报告、取回路径或留存副本 | 仅accepted、请求已发送、超时 | 按原trade_id和幂等键查询恢复，不另造订单 |
| 房间已公告 | 该业务报告对应的房间ID、message ID及内容关联，可读取核验 | say调用发起、其他QA消息、报告本地生成 | 查房间记录；只恢复公告，不因此重新付款 |
| credits已转账 | 可信途径取得的官方ledger记录，核对唯一交易、付款方/收款方、金额、资产或单位、房间与订单关联及官方最终状态语义 | 聊天“已付”、本地ledger、balance变化、CLI参数、买家上传JSON、截图或单纯退出码 | 先官方ledger对账；结果未知不自动重付 |

官方CLI pay/ledger/--room能力来自用户同步，当前仓库房间客户端未提供经核验的官方结算接入。本次不猜测CLI回执字段、交易状态名、幂等支持或最终身份映射。真实ledger即使到手，也需确认来源与以上关联，不能仅看出现一笔金额相同的交易。

报告V1继续固定credit_settlement=not_evaluated。未来可信付款事实先保存在独立运行审计中；如需升级报告字段值，必须协调版本/Schema变更，不能手工把V1报告改为settled。公告失败不推翻已经核验的付款，付款成功不保证报告或公告成功。

## 真实联调验收待输入

雅婷提供正式room/身份、公开URL、真实脱敏事件和官方ledger原始结构；子洋提供定向接收后的业务事件、消息到task/trade的映射、重放/重启记录。不要提供token或私钥。先分别验证成功、失败、缺终态、冲突终态以及公告失败但付款成功的恢复路径，再保存两小时运行证据。

目前仅验收本地合成样例，不把QA聊天转换成虚构task_completed/artifact_delivered，也不把用户对CLI的说明当作真实支付记录。思棋本地合同复核和补充测试已完成；防重复验收未通过、真实事件及结算联调待证据，不能宣布思棋全部线上完成。

复现：在项目根目录安装锁定依赖后执行 `.venv/bin/python -m pytest -q`。测试输出见 verification/pytest.txt。
