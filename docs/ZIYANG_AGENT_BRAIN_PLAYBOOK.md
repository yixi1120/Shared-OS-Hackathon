> 当前单次报告规则与产品边界以 [思棋 V1 冻结规范](siqi/INTERACTION_REPORT_V1.md) 为准；[核查与交接](siqi/AUDIT_AND_HANDOFF.md) 列出本文件中的历史规划冲突。Reputation Snapshot 尚未提供，不对外出售；新价格已确认并在本地实现，见[定价政策](siqi/PRICING_DECISION.md)。

# 子洋的 Agent Brain 实战手册

这不是一份只用于阅读的 LangGraph 教程。每一章都直接对应 SharedOS Hackathon 中子洋负责的 Agent Brain、Arena Strategy 和 Harness Engineering 交付物。

## 最终能力目标

完成本路线后，应当能够独立：

1. 把业务规则建模为 State、Node 和 Edge。
2. 判断什么时候需要普通函数、LangGraph Node、Tool 或 Subgraph。
3. 设计可恢复、可观察、幂等的 Agent 工作流。
4. 区分 LLM 决策与确定性业务规则。
5. 为 Agent 建立可重复的测试环境，而不只是写几个 mock。
6. 注入网络、模型、支付和数据故障并验证系统行为。
7. 设计实验、基线、指标和回归门槛。
8. 将 mock Arena 平滑替换成真实 SharedNet/Arena 接口。

## 学习方式

每一课都按同一循环推进：

```text
理解一个概念
→ 在当前项目中找到对应代码
→ 做一个小修改
→ 先写预期结果
→ 跑测试
→ 解释测试为什么能证明行为正确
```

判断是否掌握的标准不是“看懂了”，而是：

- 能不看答案重新实现；
- 能解释失败路径；
- 能设计一个会让错误实现暴露出来的测试。

---

## 课程路线

### 第 1 课：State、Node、Edge 与 Reducer

项目文件：`src/sharedos_commerce_agent/graph.py`

目标：理解 LangGraph 的四个核心对象。

- **State**：当前运行的事实快照。
- **Node**：读取 State，执行一个动作，返回局部更新。
- **Edge**：决定哪个 Node 下一步运行。
- **Reducer**：当一个字段收到多个更新时，决定如何合并。

完成标志：可以画出当前 Arena Graph，并解释每个字段由谁写入、由谁读取。

### 第 2 课：确定性策略与 LLM 边界

项目文件：`strategy.py`、`model_client.py`

目标：把“必须始终正确”的逻辑留在代码里，只把模糊语义任务交给模型。

确定性代码负责：

- 预算上限和最低消费；
- 至少三个不同卖家；
- 价格底线；
- 排名公式；
- 状态转换和合规检查。

LLM 可以负责：

- 将结果总结成自然语言 critique；
- 从非结构化描述中提取服务特征；
- 解释推荐原因；
- 分析卖家声明中的证据缺口。

完成标志：删除 `MODEL_API_KEY` 后，主流程仍能完成。

### 第 3 课：条件分支、循环与错误分类

项目文件：`graph.py`

目标：区分四种错误：

1. 瞬时错误：可以有限重试。
2. LLM 可修复错误：携带验证反馈重新生成。
3. 规则不满足：进入 fail-closed audit。
4. 程序缺陷：抛出异常并让测试失败。

完成标志：能解释为什么付款等外部副作用不能随意自动重试。

### 第 4 课：Persistence、Checkpoint 与恢复

目标：加入 LangGraph checkpointer 和唯一 `thread_id`。

需要验证：

- 进程在 ranking 后中断，可以从 checkpoint 恢复；
- 已发布 critique 不会重复发布；
- 已完成购买不会重复付款；
- 不同 Arena run 的状态不会串线。

当前实现已经验证两层恢复：

1. `InMemorySaver`：适合单元测试和同一进程内恢复。
2. `AsyncSqliteSaver`：关闭 saver、重新创建 Graph 后，仍能从相同 `thread_id` 恢复。

购买使用稳定幂等键：

```text
{run_id}:purchase:{service_id}:{plan_index}
```

Checkpoint 只保存节点边界的内部状态。若付款已经成功、但 `purchase` 节点尚未返回就崩溃，恢复时这个节点会重跑。稳定幂等键让支付端返回原 receipt，而不是再次扣款。

完成标志：`test_sqlite_checkpoint_survives_graph_recreation` 模拟第二笔付款后崩溃，重新创建 saver 和 Graph 后，最终仍只有四笔真实扣款。

### 第 5 课：Harness Engineering 基础

项目文件：`harness.py`

Harness 不只是 `MockArenaClient`。一个完整 harness 包含：

```text
SUT         被测试系统
Stimulus    输入和环境事件
Test Double 外部系统替身
Observer    记录调用、状态和时序
Oracle      判断结果正确与否
Scenario    一组可重复的环境配置
Report      可比较的实验结果
```

完成标志：成功场景和预期失败场景都能让测试套件通过。

### 第 6 课：故障注入与不变量测试

需要覆盖：

- 服务调用失败；
- critique 发布失败；
- ranking 提交失败；
- 购买未结算；
- 可用卖家不足；
- 返回错误价格；
- API 超时；
- 重复 receipt；
- 模型返回非法 JSON。

关键思想：测试的不是“有没有抛异常”，而是业务不变量是否仍然成立。

```text
spent_credits <= 100
self_trade == false
every_purchase_has_receipt == true
every_tested_product_has_critique == true
no_duplicate_external_side_effect == true
```

### 第 7 课：Persona、Monte Carlo 与策略比较

建立至少六类市场参与者：

- Bargain Hunter：价格高度敏感；
- Skeptical Buyer：需要强证据；
- ROI Buyer：最大化预期收益；
- Risk-Averse Buyer：重视信誉和失败率；
- Impulsive Buyer：容易接受首轮报价；
- Competitive Buyer：购买能提高 Arena 表现的服务。

对多个随机种子运行策略，比较：

- 合规率；
- 平均收入；
- 平均支出；
- 成交率；
- 平均折扣；
- 失败交易比例；
- 购买卖家多样性；
- 模型 token 和美元成本。

完成标志：能用实验结果说明 Strategy V2 是否真的优于 V1。

### 第 8 课：真实接口集成与上线前演练

项目文件：`sharednet_adapter.py`

目标：保持 Agent Brain 不变，只替换 ArenaClient 实现。

上线前必须运行：

- contract test；
- dry run；
- 限额测试；
- 断网恢复测试；
- 真实模型成本测试；
- 全程无人干预测试。

---

## 第 1 课详解：如何阅读当前 Arena Graph

当前 Graph 有三种运行模式：

- `critique`：只执行 Round 1，绝不提前花 credits。
- `market`：只执行 Round 2，不重复发布 critique。
- `full`：供本地 dry run 使用，连续验证两轮规则。

完整 dry run 的执行路径是：

```text
START
  ↓
prepare
  ↓
discover ──卖家不足──→ audit → END
  ↓
evaluate_services
  ↓
publish_required_feedback
  ↓
rank
  ↓
plan_market ──无有效计划──→ audit → END
  ↓
purchase
  ↓
audit
  ↓
END
```

真实分轮路径是：

```text
Critique: START → prepare → discover → evaluate_services → publish_required_feedback → rank → audit → END
Market:   START → prepare → discover → plan_market → purchase → audit → END
```

`run_mode` 是 State 中的事实；两个 conditional edge 根据它选择路径。这个设计保证同一套节点既能按官方时间分轮运行，也能在本地一次完成回归测试。

### State 为什么保存原始事实

State 中保存 `listings`、`results`、`purchase_plan` 和 `progress`，而不是保存一大段“当前情况总结”。原因是原始事实可以被不同 Node 以不同方式重新使用，也更容易测试。

错误示例：

```python
state["summary"] = "We tested three good products and should buy the cheapest."
```

更好的形式：

```python
state["results"] = {service_id: ServiceResult(...)}
state["purchase_plan"] = [PurchaseIntent(...)]
```

### Node 为什么只返回局部更新

`discover` 不需要复制全部 State，只需要返回它新产生的字段：

```python
return {
    "phase": "evaluate_services",
    "listings": listings,
    "evaluation_targets": targets,
}
```

这样每个字段的来源容易追踪，也避免某个 Node 意外覆盖其他 Node 的数据。

### Reducer 为什么用于 violations

多个 Node 都可能发现违规。如果使用默认覆盖规则，后面的错误会把前面的错误覆盖掉。

```python
violations: Annotated[list[str], operator.add]
```

含义是把各 Node 返回的错误列表追加起来。Reducer 必须满足可预测性；不要用有隐藏副作用或依赖当前时间的 reducer。

### Edge 为什么不能执行副作用

条件 Edge 只读取 State 并返回路由名称：

```python
def after_discovery(state):
    return "evaluate_services" if state.get("evaluation_targets") else "audit"
```

不要在 Edge 内付款、调用 API 或修改数据库。Edge 可能在恢复、调试或状态重放中再次被计算。

---

## 第 1 课练习

### 练习 A：预测节点顺序

不运行代码，先写下正常场景流程会经过哪些 Node。然后运行：

```bash
uv run pytest tests/test_graph.py -q
```

解释为什么正常路径是八个 Node，而卖家不足时只有三个 Node。

### 练习 B：解释 State 所有权

为下面每个字段指出第一个写入它的 Node：

```text
progress
listings
evaluation_targets
results
rankings
purchase_plan
report
```

### 练习 C：制造一个条件分支

在 Harness 中把 listings 改成两个卖家，预测：

- 哪个 Edge 会改变方向；
- 哪些 Node 不再运行；
- 最终 violations 应包含什么。

答案已经被编码在 `test_conditional_edge_fails_closed_when_discovery_is_insufficient` 中。先自己回答，再读测试。

### 练习 D：比较三种运行模式

阅读 `test_critique_round_does_not_spend_market_credits` 和 `test_market_round_skips_critique_actions`，回答：

- 为什么 Critique 模式的 `spent_credits` 必须严格等于 0？
- 为什么 Market 模式不要求当前 invocation 产生 critique？
- 为什么 `progress` 必须允许从上一个 round 传入，而不能每次都重建？

### 掌握检查

如果能在不看代码的情况下回答下面问题，就可以进入第 2 课：

1. State 和普通函数参数有什么区别？
2. Node 为什么返回更新，而不是必须返回完整 State？
3. 什么字段需要 reducer？
4. 条件 Edge 应不应该调用外部 API？
5. 为什么 `purchase` 是一个独立 Node，而不是放进 `plan_market`？

### 一个必须守住的产品边界

当前 Arena Graph 是我方 Agent 对外完成比赛规则的 **Outbound Compliance Graph**，不是我们出售的评价产品。`publish_required_feedback` 只负责将已经记录的调用事实转换成赛制要求的 disagreement。

我方产品处理的是另一条 **Inbound A2A Interaction Evidence Flow**：

```text
其他 Agent 经我方节点执行 A2A Task
→ 校验 task_id、subject、provenance 和阶段顺序
→ 检查 artifact 交付、延迟、schema 与争议
→ 输出 InteractionTraceReport
→ 多笔信誉合格的 trace 才能聚合 ReputationSnapshot
```

主观 critique、宣传文案和 LLM 语气都不得进入 `execution_score`。一笔 trace 只能表达单次交互；单方自报数据必须是低证据权重且不得进入信誉聚合。Arena 未提供可信 receipt 前，`credit_settlement` 固定为 `not_evaluated`。

## 当前实现进度

- [x] 业务节点拆分
- [x] 条件路由
- [x] Critique / Market / Full 三种运行模式
- [x] State 可携带上一轮 `progress`
- [x] 14 个确定性 Harness 场景
- [x] Round 1 服务探测受控并发
- [x] 错误价格检测
- [x] API 超时检测
- [x] 重复 receipt 检测
- [x] 客观 A2A interaction trace 模型与确定性评分
- [x] provenance 分层与信誉准入门槛
- [x] 单方自报不能升级成 verified evidence
- [x] 执行探测与赛制 feedback 分离
- [x] InMemory checkpoint 与同进程恢复
- [x] SQLite checkpoint 与跨 Graph 重建恢复
- [x] 购买副作用幂等键
- [x] Critique / ranking 副作用幂等键
- [x] 成功但 acknowledgement 丢失的三类故障场景
- [x] Seller 并发 Harness
- [x] 两小时 Soak Harness（32,272 笔全部 delivered；详见 [SOAK_TEST_REPORT](SOAK_TEST_REPORT.md)）
- [x] Persona 与多随机种子实验
- [ ] 真实 SharedNet contract test

---

## 当前命令

运行全部测试：

```bash
uv run pytest -q
```

运行完整 Harness 场景集：

```bash
uv run arena-harness
```

只学习 LangGraph 节点和分支：

```bash
uv run pytest tests/test_graph.py -q
```

只学习 Harness 场景与 Oracle：

```bash
uv run pytest tests/test_harness.py -q
```

## 官方参考

- LangGraph Graph API：https://docs.langchain.com/oss/python/langgraph/graph-api
- Graph API 使用方法：https://docs.langchain.com/oss/python/langgraph/use-graph-api
- LangGraph 测试：https://docs.langchain.com/oss/python/langgraph/test
- Persistence：https://docs.langchain.com/oss/python/langgraph/persistence
- Interrupts：https://docs.langchain.com/oss/python/langgraph/interrupts
- Thinking in LangGraph：https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph
