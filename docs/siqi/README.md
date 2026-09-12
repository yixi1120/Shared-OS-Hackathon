# 思棋最终交付包

开发基线 main `90cdbf0`；2026-09-12 完成本地合同验收，并按用户批准的策略完成[事件身份与消息重放修复](EVENT_IDENTITY_CHANGE.md)。本修复已在冠盛 V4 合入后的 main `a2c654c` 上完成集成复核，结果为 125 passed。V1 输出字段和公式兼容；先去重再计算，输入 Schema 新增 event_id。以下六项为交付入口：

1. [最终Interaction Report V1合同](INTERACTION_REPORT_V1.md)：输入、全部输出字段、公式、状态语义、风险触发条件及边界；[机器Schema](schemas.json)用于交付校验。
2. [14项风险标记和中英文解释](RISK_FLAGS_V1.md)：与运行代码逐字一致。
3. [provenance与evidence weight规则](EVIDENCE_AND_PUBLIC_MEANING_V1.md)：来源认证边界、权重、公共输入降级。
4. [固定样例和完整预期输出](../../tests/fixtures/interaction_v1.json)：17组；[可读测试矩阵](TEST_MATRIX.md)。包含成功、失败、缺Artifact、缺终态、终态冲突及弱来源等。
5. [对外代表什么／不代表什么](EVIDENCE_AND_PUBLIC_MEANING_V1.md)：中英文说明及结算表达。
6. [最终联调验收记录](FINAL_ACCEPTANCE_2026-09-12.md)：本地通过项、已知未通过项和线上待验收项；[测试原始输出](verification/pytest.txt)。

## 本轮完成标准核对

| 标准 | 结果与证据 |
|---|---|
| 相同输入始终同结果 | 本地通过：17组完整固定输出重复计算；API交付重放一致。时间相同而改变输入顺序不是相同输入。 |
| 成功、失败、冲突正确区分 | 本地通过：两SKU覆盖全部五类核心案例及阶段/schema异常，严格校验输出Schema。 |
| 自报不展示为平台验证 | 本地通过：公共入口伪造platform仍降为self_reported、0.15，不具备信誉候选资格。 |
| 支付金额不影响执行分 | 本地通过：实际接受5与6 credits的两SKU订单，完整报告输出相同；这不是官方真实付款测试。 |
| 单笔不包装成全局信誉 | 当前合同、Risk解释、Dashboard页头和提交正文均明确边界。 |
| 文档、代码、Dashboard和提交材料一致 | 合入冠盛 V4 后，当前仓库的字段 Schema、14项双语解释、价格及核心证据表达一致；Dashboard 已包含“仅免费询价”按钮。此次完成源码与完整测试复核，仍未进行线上浏览器验收。 |

## 材料版本差异与保留问题

思棋开发基线 `90cdbf0` 当时尚未包含冠盛 V4 的“仅免费询价”按钮；当前集成基线已经包含该按钮及冠盛 V4 的95项测试。叠加本修复后，当前完整测试为125项通过。旧 AUDIT_AND_HANDOFF.md、REVIEW.md 和 FINAL_ACCEPTANCE_2026-09-12.md 中的旧测试数属于历史记录，以本入口和最新集成复核为当前状态。

此前重复有效事件将93分提高至94分的问题已在本轮修复，原xfail现为普通通过测试。相同显式身份的冲突内容返回409并记录；房间使用独立message_id收件箱。修订为interaction-v1-event-identity-1。仍不得宣传完整防刷分，换ID伪造和自报真实性不属于去重保证。思棋原始测试记录见 verification/pytest.txt（123 passed）；与冠盛 V4 合并后的完整复跑为125 passed。之前110 passed/1 xfailed为历史结果。

真实SharedNet业务事件、公开服务、正式ledger及两小时运行没有本次可验证证据，因此线上最终联调状态为待验收。交付包可用于团队核对与接入，不等于正式比赛验收通过。未发送外部消息或推送远程。
