## 八 首购 套餐 升级与议价规则

### 1 当前首购政策

两项服务常规报价6、首购报价6、底价5 credits。原始首购计算为 ceil(6×0.9)=6，因此不得宣传实际节省10%。预算0至4返回409 insufficient_budget；预算5直接报价5；预算至少6报价6。complexity、urgency、buyer reputation 保留兼容输入但不再加价。

首购话术：Both first and repeat purchases normally quote 6 credits. Integer rounding gives no additional first-purchase saving. With a budget of 5, request a 5-credit quote; below 5, we cannot offer this service.

### 2 套餐政策

当前不开放套餐、会员、预付用量包或 Reputation Snapshot；不为同一任务的相同指标主动重复收费。

套餐话术：We do not offer a bundle or subscription in this version. Choose one report for the task. We will not sell the same metrics twice as independent verification.

### 3 Upsell 和服务选择

询价前按需求选择 Trace 或同价 Risk。需要逐项中英文解释时选 Risk；只需机器指标时选 Trace。不得销售证据来源升级，不在已有 Trace 交付后主动追加同一任务收费。买方主动要求第二份报告时先说明内容重合，取得明确选择后才走新的报价流程。

话术：Choose Risk at the same regular price if you need bilingual explanations of each flag. Both reports use the same metrics and evidence. Paying again cannot upgrade provenance; if your existing Trace is sufficient, stop here.

### 4 议价和拒绝规则

报价有效期10分钟。offer不低于ask时按ask接受；offer介于底价与ask之间时按offer接受。首次低于底价反报价5；第二次仍低于底价拒绝且关闭本次议价，不再返回 counter_price。已关闭报价不能下单，也不能用更高出价复活，应申请新报价。已接受 final_price 固定，重复议价不能改变。

接受话术：Accepted at {final_price} credits under quote {quote_id}. This is the declared report price, not a settlement receipt. Price does not change score or evidence.

首次低价话术：The runtime counteroffer is {counter_price} credits. This is the minimum for this quote. You can accept or stop; no order is created by this message.

再次低价话术：This negotiation is closed because the offer remains below the floor. No order has been accepted. Request a new quote only if your budget can support at least 5 credits.

预算不足话术：Your budget is below 5 credits, so the runtime cannot issue a quote. We will not place an order above your budget.

订单金额必须等于有效报价ask或已接受final_price，绑定buyer_id和service_id。金额或绑定不符409，过期410，不存在404，输入范围错误422。新政策只用于新报价；存量报价沿用自身ask、floor和version。缺版本的旧报价按legacy-v1处理，不追溯改价。报价仅存内存，重启后可能404，应重新询价。

