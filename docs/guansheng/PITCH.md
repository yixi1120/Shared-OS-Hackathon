## 六 自动产品介绍与买家 Pitch

### 1 二十秒以内的自动介绍

英文可直接发送或朗读：

We turn one A2A task’s lifecycle events into a readable execution report. See completion, latency, evidence confidence, and risk flags. Self-reports stay self-reports. No global reputation or payment verification. Send task metadata, choose a service, and request a quote.

该稿按空格分词共39词，按每分钟150词约16秒，给停顿留有余量；文本房间可直接发送。若录制语音，成片以实际计时为准，须控制在20秒以内并保留证据边界句。

中文对应稿：

我们分析单笔A2A任务的阶段事件，返回执行指标、证据置信度和风险标记。自报不等于平台核验，也不是全局信誉。提交任务元数据即可询价。

### 2 买家希望降低下一次采购风险

触发：买家提到下单前检查、失败经历、对卖方能力缺少证据。目标是出售可解释的一笔任务分析，不承诺预测准确率。

Before your next purchase, inspect what the events from an earlier task actually support. Trace gives you delivery and completion indicators, reported latency, confidence, and risk flags in one response. It can guide follow-up questions; it does not guarantee the next seller will succeed. Start with the trace and request a quote.

### 3 卖家希望解释自己的交付记录

触发：卖家希望把任务执行过程交给买家核对。不能把服务包装成购买第三方背书。

Give your buyer a consistent, machine-readable account of the task events you submit. The report keeps evidence references and source limits visible. Paying for a report cannot change its score or turn your claim into platform verification. Use it to explain the record, not to purchase an endorsement.

### 4 开发型 Agent 希望排查调用失败

触发：出现任务中断、没有交付物、阶段不清晰或 schema 问题。

Send the events for one failed or incomplete task. We show whether an artifact and terminal state were reported, whether stages are ordered, and which risk flags follow from those events. You get a compact diagnostic record without uploading the original prompt or artifact.

### 5 预算敏感的买家

触发：预算有限、想先试一次或对 Risk 的增量价值存疑。

Start with A2A Interaction Trace. The current Risk Report adds bilingual per-flag explanations to the same metrics; if you already understand those limits, you may not need it. Both services normally cost 6 credits. A budget of 5 can receive a 5-credit quote. Request a quote before ordering.

### 6 隐私敏感的买家

触发：担心 prompt、交付内容或业务秘密被保存。

Keep your prompt and full artifact with you. Send only task metadata, evidence references, and optional hashes. Use opaque IDs, and confirm the operator’s retention policy if the metadata is sensitive. The report will still state the limits of self-reported evidence.

### 7 证据要求高的买家

触发：要求平台签名、独立观察或可用于信誉评分的证据。

The public submission path currently treats your events as self-reported. It cannot satisfy a requirement for independently authenticated platform evidence. If that requirement is essential, do not buy on the assumption that a provenance label will upgrade your evidence. A trusted ingestion path must be confirmed first.

