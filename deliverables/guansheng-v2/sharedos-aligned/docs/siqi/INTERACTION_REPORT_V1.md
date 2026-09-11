# Interaction Intelligence V1 冻结规范

状态：报告、公式、来源和风险规则已冻结；定价方案已获思棋确认并在本地实现（见 PRICING_DECISION.md）。依据：main `566b54e`，2026-09-11 本地核查。兼容性：Execution Score、来源映射、基础 eligibility 均保持主分支行为；本补丁仅追加 7 个 risk flags，并为 Risk Report 添加逐 flag 双语解释。消费者必须允许新增风险值和 interpretation 子字段。

## 1. 产品真实性与输入边界

公共 Seller 当前分析调用方提供的结构化事件；不是自动执行任意普通任务的可信观测节点。仅出售单次 Trace / Risk Report，不出售全局 Reputation。报告外层 `status=delivered` 是分析产品交付状态；内层 `completed` / `delivered` 是被分析任务状态，二者不混用。输出分数由 telemetry.py 确定计算，无 LLM。所有公共事件均由 seller.py 强制赋为 self_reported；未知字段（包括 provenance）在持久化前丢弃。

正式输入 `InteractionTraceInput={events:[InteractionEventSubmission]}`，1–200 条、同一 task_id 和 subject_agent_id。每条必填 task_id/subject_agent_id（1–256 字符）、stage、occurred_at（datetime）；schema_valid 默认 true；evidence_id/request_hash/artifact_hash 为可选 string|null，最长 256。额外字段忽略。事件本身无 ID、买卖双方认证身份或可信 receipt 验证字段。hash 仅保存，当前不校验 hash 内容或证据可解析性。

合法阶段及序号：task_created 0 → request_received 1 → quote_declared 2 → task_started 3 → artifact_delivered 4 → buyer_acknowledged 5 → task_completed/task_failed 6 → disputed 7。quote_declared 是当前代码存在但旧分工文档枚举遗漏的阶段。timeout 不是合法 stage；不能凭空改为 task_failed。无终态的超时只能报告缺终态；明确失败须由真实来源记录 task_failed。

V1 按时间稳定排序，时间相同保留输入次序；检查序号是否非递减。输入列表乱序但时间正确不扣分；同阶段重复允许，不去重。相同完整有序 JSON 输入重复计算输出一致，不依赖当前时间。推荐调用方提供带时区时间戳；当前模型接受 naive datetime，混用 naive/aware 可导致排序异常，列为 V1.1 修复项；不能宣称已验证全部日期输入。同一时间事件换序不属于相同输入。

## 2. 字段合同

以下“必填”指输出合同：所有下列字段均由 evaluator 返回；模型构造层默认值另外注明。S=影响 Execution Score；R=影响现有 V1 基础 eligibility；未来聚合约束见第 6 节。必填输入缺失或类型不合法在 API 返回 422，不用默认成功补齐。

| 字段 | 类型/必填 | 来源与计算 | 缺失处理 | 对外解释 | S / R |
|---|---|---|---|---|---|
| task_id | string/是 | 输入唯一 task_id | 输入无值拒绝 | 该次任务标识，非交易回执 | 否/未来去重键 |
| subject_agent_id | string/是 | 输入唯一 subject | 输入无值拒绝 | 被分析主体，当前为调用方声明 | 否/未来身份核验 |
| completed | bool/是 | 同时存在 artifact_delivered 与 task_completed | 任一无则 false | 记录显示交付及完成；冲突失败不覆盖（V1 缺陷） | +40/无直接影响 |
| delivered | bool/是 | 是否存在 artifact_delivered | false | 记录有 Artifact 交付，不证明内容质量 | +15/否 |
| ordered | bool/是 | 时间排序后阶段非递减 | 单事件 true | 生命周期记录顺序符合映射 | +15/否 |
| schema_valid_rate | float[0,1]/是 | true 数量/N，展示 round(x,4) | 事件 schema_valid 未填默认 true | 调用方 schema 标记合规比例，非服务自行验证 Artifact | 原始比例×20/否 |
| disputed | bool/是 | 是否有 disputed | false | 有争议声明，不是裁决 | −25/否 |
| end_to_end_latency_ms | int≥0\|null/是，模型默认 null | max(0,int((最晚终态−最早 request_received/task_started)秒×1000)) | 缺任一侧 null | 记录跨度，不是报告 API 耗时 | 延迟奖励/否 |
| execution_score | float[0,100]/是 | 第 3 节公式，round(x,2) | 无有效输入拒绝 | 仅该次输入轨迹的执行分 | 结果/否 |
| evidence_weight | float/是 | 所有事件最弱 provenance 权重 | 内部 provenance 必填；公共强制 .15 | 证据来源政策权重，非成功概率 | 否/同一来源门槛间接关联 |
| confidence | string/是 | 最弱 provenance 的固定标签 | 同上 | 单次证据来源等级，非统计置信区间 | 否/否 |
| reputation_eligible | bool/是 | 有 completed 或 failed 终态，且每条来源为 platform/observed | 无终态 false | 仅通过基础候选门槛，未来正式纳入仍须核验第 6 节 | 否/该字段是基础结果 |
| credit_settlement | string/是，模型默认 not_evaluated | evaluator 不接受结算输入，固定 not_evaluated | 不推断已付款 | 尚未评估可信结算 | 否/否，不以付费买资格 |
| provenance_counts | object<string,int>/是，模型默认 {} | 所有事件分来源计数，含重复 | 不存在的来源键省略 | 输入记录数，不等于独立任务样本量 | 否/来源决定基础门槛 |
| evidence_ids | list<string>/是，模型默认 [] | 按输入次序取非空 evidence_id，保留重复 | []；空字符串被忽略 | 待核验引用，不是已验证证据 | 否/未来证据与去重门槛 |
| risk_flags | list<string>/是，模型默认 [] | 第 4 节依次追加 | [] 在旧版可能出现；新版必有结算未评估 | 诊断标记，不再二次扣分 | 不另扣/不另改 |
| interpretation | object/仅 Risk Report 必填 | meaning:string，not_meaning:string，flags:list<{flag,zh,en}>；固定代码映射 | Trace 不输出；Risk 必有 | 单次分析含义、非全局信誉/付款声明与逐项解释 | 否/否 |

`credit_settlement` 当前模型类型仍为 str，直接手动构造模型可以填其他文字；正式 evaluator/Seller 路径始终 not_evaluated。没有可信回执接入前不得用手工构造报告绕过这一合同。

机器合同 `schemas.json` 中，`trace_report_model` 保留 Pydantic 构造默认值语义；`trace_report` 是正式交付合同，所有报告字段必需且结算值固定为 `not_evaluated`；`risk_report` 另外要求完整 `interpretation`。请使用后两者校验交付，不用模型构造 Schema 替代输出合同。

## 3. Execution Score V1

令 C/D/O/U 为 completed/delivered/ordered/disputed 的 0/1，V 为未四舍五入 schema 有效率，L 为延迟毫秒：

```text
latency_points = 0 if L is null else max(0, 10 - L/2000)
raw = 40*C + 15*D + 15*O + 20*V + latency_points - 25*U
execution_score = round(clamp(raw,0,100), 2)  # Python round 语义
```

完整成功 4 秒：40+15+15+20+8=98。失败 4 秒、无 Artifact、顺序正确、schema 全 true：0+0+15+20+8=43。注意已有 test_failed_or_malformed_trace 是 2 秒、乱序、2/3 schema 合规，实际 22.33，并不是 43；Seller Harness 成功用 800ms，实际 99.6，不是 98。不要把不同输入的分数混用。

缺 task_started 无直接扣分；仍可从 request_received 计算延迟。缺交付同时失去完成 40 和交付 15。缺终态无 completed，延迟奖励为 0；artifact 若存在保留 15。明确失败没有独立罚分，终态可用于延迟；争议扣 25。结构不合法事件在入口拒绝，schema_valid=false 则进入比例计算。不得用 risk flags 再扣一次分。

禁止输入评分的因素：Arena Critique、广告/销售话术、Ranking、金额、是否付费、会员、优惠、未经验证 credits 结算、Evidence Weight。两分独立展示，不能相乘或汇总“可信度总分”。

### V1.1 建议（未实施，不替换 V1）

固定 20 秒降至零的延迟奖励不适合跨任务比较。V1 对外只在同任务类型和同 SLA 下比较；V1.1 应先按可信任务类别声明 SLA，再评估相对时延，不能让调用方任意提高 SLA。另需：时区统一和混用拒绝；终态冲突标记并阻止成功结论；可信事件/证据去重后再计算比例；负时延不应 clamp 成 0 获得满额奖励；schema_valid 应由验证器证明；缺阶段不应借助完美顺序获得过高基础分。任何改分均须新版本及新 golden fixtures。

## 4. Risk Flags V1

顺序为下表顺序；前六项兼容原版，后七项本次新增。中文/英文买方文案的机器源为 risk_rules.py。S 列指触发事实已如何进入公式；flag 自身不额外扣分。R 指现有基础门槛；未来入库规则另行判断。

| 机器名 | 确定触发条件 | 中文 / English 含义及买方解释 | S | R | 测试案例 ID |
|---|---|---|---|---|---|
| missing_terminal_task_state | 无 task_completed 且无 task_failed | 缺终态 / Missing terminal：不能判断最终任务状态 | 完成0、延迟0 | 拒绝 | single_event |
| artifact_not_delivered | 无 artifact_delivered | 未记录交付 / Artifact not recorded：记录缺失不证明现实未交付 | 完成0、交付0 | 无 | missing_artifact |
| invalid_stage_order | 时间序列阶段回退 | 阶段乱序 / Invalid stage order：生命周期记录不连贯 | 失去15 | 无 | stage_order |
| schema_validation_failure | 任一 schema_valid=false | schema 不合规 / Schema failure：至少一条声明无效 | 按有效比例 | 无 | partial_schema |
| interaction_disputed | 存在 disputed | 存在争议 / Disputed：未作裁决 | −25 | 无 | dispute |
| evidence_not_reputation_eligible | 基础 eligibility=false | 未过基础准入 / Ineligible：无终态或来源不够强 | 无 | 已拒绝 | success_self_reported |
| task_start_not_recorded | 无 task_started | 未记录开始 / Start not recorded：request_received 不代造 start | 无直接影响 | 无 | missing_start |
| completion_not_recorded | 无 task_completed | 未记录完成 / Completion not recorded：可能已有失败终态 | 完成0 | 无，失败可入候选 | explicit_failure |
| task_explicitly_failed | 有 task_failed | 明确失败 / Explicit failure：分析报告仍可交付 | 无独立扣分 | 不排除失败证据 | explicit_failure |
| latency_not_computable | L=null | 延迟不可算 / Latency unavailable：缺起点或终点 | 延迟0 | 无 | missing_start |
| evidence_reference_missing | 任一 evidence_id 缺失或空串 | 引用缺失 / Missing reference：现有引用也尚未验证 | 无 | 基础不拒绝；未来缺证据拒绝 | missing_references |
| weak_evidence_source | 最弱来源权重<.9 | 来源偏弱 / Weak source：含 bilateral/self_reported | 无 | 拒绝 | mixed_bilateral |
| credit_settlement_not_evaluated | 当前总为真 | 结算未评估 / Settlement unevaluated：报价和声明金额不是付款证明 | 无 | 无 | 每个案例 |

没有 timeout、duplicate 或 conflicting_terminal 的新 stage/flag：V1 已知缺口明确留给 V1.1，不能凭标记补造事实。

## 5. Provenance / Evidence Confidence V1

| 来源 | 判定标准（由可信入口赋值） | weight | confidence |
|---|---|---:|---|
| platform | 平台认证事件或可验证平台签名/审计引用，校验来源、任务绑定及重放 | 1.0 | platform-verified-single-interaction |
| observed | 服务受控执行环境亲自观测，有身份绑定及可追溯原始引用 | .9 | service-observed-single-interaction |
| bilateral | 双方独立认证确认且任务/内容一致，不能只是同一调用方写“两方确认” | .6 | bilateral-single-interaction |
| self_reported | 单方提交，未由可信环境独立验证 | .15 | self-reported-single-interaction |

混合来源一律 min(weight)，confidence 取该最弱来源；不是平均或多数投票。0.15 是已有确定性政策常数，用于保守区分来源，不是统计实验估计、15% 真实性概率或 85% 不可信。weight 不影响 execution_score。

公共 Seller 只有 self_reported 路径；内部 InteractionEvent 可赋其他等级，但 evaluator 不验证其真实性，接入者须实现上述认证。无法验证 audit reference、仅有本地 Bearer Token、付款、买方好评或调用方填写 provenance，一律拒绝升级。401 仅证明配置 Token 后本地入口拒绝访问；不等于 SharedOS capability grant 审计。

## 6. Reputation 边界（政策冻结，聚合实现不在本次范围）

现有 reputation_eligible=true 仅表示“终态且所有来源可信”的基础候选资格，不能宣传已经正式纳入或已生成 Reputation。V1 为兼容保留这一字段；未来入库必须另行通过全部检查，不能仅凭 bool 入库：

1. 原始 evidence_id 非空、可解析、身份和 task/subject/hash 绑定可验证；最弱来源至少 observed；公共自报及 bilateral 不纳入。
2. 有可验证成功或失败终态；不能只收成功以造成选择偏差。冲突终态隔离等待解决，真实失败/争议保留作负面证据。
3. 平台任务 ID + 认证 subject 构成唯一任务键，event/evidence ID 和内容 hash 查重；同任务的 Trace/Risk 两次购买只算一份；重放不得增加样本。
4. 认证 buyer 与 subject/seller 不同且非同一控制主体；无身份或关系证明不纳入。不把 buyer_id 自报字符串当认证身份。
5. 同一对手方 24 小时重复交易至多一份独立样本；异常重复低金额任务隔离审核，不让微交易增加信心。金额不改变 execution_score，不通过高金额买权重。
6. 建议未来展示阈值：少于 10 个独立任务或 3 个认证独立对手方，显示 Unrated 与 n，不发布总分；达到门槛仍必须展示样本量、观察窗口、来源分布、成功率的 95% Wilson 区间（不能把 provenance 标签当区间）。这一保守阈值为未来产品政策，未声称已有实现；100 样本也不保证高可信。

当前不创建 ReputationSnapshot、不发布其价格或调用方法。不存在 0/1/10/100 样本全局评分服务。新 Agent 不默认展示可误解的“50 分信誉”。

## 7. 测试与演示

`tests/fixtures/interaction_v1.json` 为 17 个固定输入、完整预期 JSON 和证明目的；`tests/test_interaction_v1_contract.py` 比对全部输出，连续计算两次。`TEST_MATRIX.md` 是同源可读摘要。fixture 的预期分数手工列定，未调用 evaluator 生成。

成功 demo 用 success_self_reported：98/.15/self-reported-single-interaction/false/not_evaluated。失败 demo 用 explicit_failure：43、completed=false、delivered=false，API 外层 status=delivered；Trace 和 Risk 均自动测试。未授权 demo 使用已有 test_configured_bearer_token_protects_non_discovery_endpoints；缺/错 Token 401，正确 Token 200，Catalog 免费可读；不是正式平台授权证明。
