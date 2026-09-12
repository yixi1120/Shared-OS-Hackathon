# 稳定事件身份与消息重放修复

修订：interaction-v1-event-identity-1，基线90cdbf0，2026-09-12。依据本轮用户明确批准的策略实施。之前的93→94已知失败被修复，原xfail已转为普通通过测试。本次输出Schema、14项风险标记、公式和credit_settlement=not_evaluated不变；改变的是计算前的事件集合及重复记录计数。

## 事件接入

新生产方在首次创建逻辑事件时分配event_id，持久化到自己的任务记录中，重试、转发和恢复使用同一个ID。两个真实发生的不同事件使用不同ID；不要每次HTTP请求重新生成ID，也不要用一个task_id充当所有阶段的event_id。现有CLI透传输入JSON中的event_id，不重写ID。

```json
{"event_id":"task-17-start-1","task_id":"task-17","subject_agent_id":"agent-9","stage":"task_started","occurred_at":"2026-09-12T06:00:00Z","schema_valid":true}
```

去重键为(source_id, task_id, subject_agent_id, event_id)。内部可信接入必须分配稳定source_id，不能把调用方正文的provenance或source_id当作认证身份。当前公共Seller没有独立调用方身份认证映射，保守地共享public-submission来源域，仍全部self_reported；公共生产方应使用全局唯一任务ID和事件ID防止相互撞名。多租户可信身份绑定待接入，不能由buyer_id冒充解决。

同键同内容保留首次事件，评分、schema比例、时延、来源统计及证据列表全部从去重后集合计算。不同ID即使其他内容一样也表示不同逻辑事件。规范化比较使用模型接受的字段、默认值、UTC时间及可信provenance；未知字段在入口丢弃，不属于被分析内容。

同键不同内容返回409 event_identity_conflict，不生成报告。Seller的SQLite event_identities持久化身份与内容哈希，跨订单、重启和多个数据库连接不能静默改写。event_conflicts保存冲突键、前后内容哈希和时间；不保存冲突正文。通过Ledger.event_conflicts()读取。直接调用纯evaluator时会抛EventConflictError并输出哈希日志；持久审计应走Seller/ Ledger边界。冲突批次不注册该批新身份，也不创建订单。已经登记的身份不会因请求结束而遗忘。

兼容策略：event_id暂为可选，旧输入使用规范化内容SHA-256身份，因此完全重复的旧事件也不会再抬分。旧输入内容改动会产生新哈希，无法识别为“同ID冲突”；要获得冲突保护必须迁移为稳定显式ID。缺ID不能使用随机值填充，也不能用evidence_id替代业务事件ID。部署前创建、尚未经过新校验的旧订单会在交付时校验；过去已交付报告不自动追溯改写。首次重新交付旧重复输入可能产生更新后的统计，消费者应按本修订识别。

## 房间消费

新增SharedNetRoomClient.receive_pending(inbox)，inbox是持久化文件路径的Ledger。其去重键为(room_id, message_id)，与业务event_id完全独立。新消息先和接收cursor在同一SQLite事务落盘；相同消息只保留一个inbox记录；未确认消息会在重启后重新交付消费者。缺message_id或相同消息ID内容变化会拒绝入箱，不推进持久cursor。

```python
inbox = Ledger("data/sharednet-inbox.sqlite")
messages = await room_client.receive_pending(inbox)
for message in messages:
    # 在此先做定向过滤，使用稳定订单幂等键处理；此处不提供广播自动回复。
    # 完成业务处理并持久化结果后，或明确决定忽略非目标消息后：
    inbox.acknowledge_message(room_client.room_id, message.message_id)
```

每个房间使用一个顺序消费者；处理失败时不要ack，下次继续相同消息和相同业务幂等键。ack前崩溃可能重试业务处理，因此消费者仍必须保证订单/付款副作用幂等；这里不承诺分布式exactly-once。原始read/wait继续作为查询/传输接口，生产监听要使用receive_pending；本仓库尚无正式房间自动业务转换runner，本次没有宣称完成生产监听上线。

## 验收与交付

tests/test_event_identity.py覆盖显式ID重复有效/无效事件、不同身份范围、内容冲突、UTC规范化、旧输入、跨订单/重启审计、并发连接和房间ack恢复。tests/test_siqi_final_acceptance.py中的93分反例已取消xfail。固定duplicate_event样例的来源计数从5改为4、重复引用只计一次，其余固定样例预期保持原值。输入Schema在打包资源、思棋合同和冠盛材料同时更新。

当前可以说“同一逻辑事件重放不再改变评分；同ID内容冲突被拒绝并记录”。不能说“完整防刷分”：换ID伪造新事件、虚构自报内容、身份冒充和证据真实性仍需要可信接入与其他控制。没有执行真实SharedNet监听、转账或部署。本地测试结果见verification/pytest.txt。
