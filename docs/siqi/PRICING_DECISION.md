# Arena 定价政策 V1

状态：**思棋已确认；已在本地代码与测试中实施，尚未推送或部署。** 版本 `arena-fixed-v1`。两项服务共用 `DEFAULT_PRICING_POLICY`；Catalog 和 Runtime 从同一 PricingPolicy 取价。声明金额仍不等于已结算收入。

## 最终价格

| SKU | 常规 ask | 首购 ask | floor |
|---|---:|---:|---:|
| a2a-interaction-trace | 6 | ceil(6×.9)=6 | 5 |
| a2a-interaction-risk-report | 6 | ceil(6×.9)=6 | 5 |

两者包含相同执行指标、来源权重和风险标记；Risk额外给出逐项解释，不为相同指标加价。不宣传首购实省10%，因为整数取整后仍为6。取消complexity、urgency、buyer_reputation乘数，输入字段仍兼容接收。暂不开放套餐、会员或Reputation Snapshot，不付费升级来源，不主动对同一trace重复收费。

## 报价、预算及议价

- budget 0–4：HTTP 409，detail=`insufficient_budget`，不创建报价。
- budget=5：ask=5、floor=5；budget≥6：ask=6、floor=5。
- 有效期10分钟；Quote新增budget和pricing_policy_version，原有ask/floor保留。新报价ask不超过预算。
- offer≥ask：按ask接受；floor≤offer<ask：按offer接受；低于floor：第一次反报价floor，第二次仍低于floor则拒绝，无counter_price，并结束该quote的谈判。
- 已结束报价不可下单（409），后续提高offer也不复活，须重新询价。已接受的议价价格固定，重复请求返回原成交声明价。
- 订单金额必须等于已接受价格或未议价ask，并绑定buyer/service。过期410、未知404、不匹配409；非法offer范围422。
- 新策略只用于新quote。协商使用quote自身ask/floor及版本；未带版本的旧Quote默认为legacy-v1，保持旧价格和中点反报价方式。策略对象变化不追溯改价。
- quote与议价状态仍在进程内存；重启会丢失，旧报价返回404需重新询价。此次没有新增数据库或部署迁移，不能承诺跨重启履约状态恢复。

## 统一销售话术

“我们分析你提交的单次A2A事件，分别报告执行分和证据来源权重。Trace和Risk Report常规价均为6 credits，可议价到5；预算5时直接报价5。Risk额外提供同一指标的逐项解释。首购整数报价仍为6。公共提交均为self-reported，付款不会升级证据来源。实际成交声明价以有效Runtime Quote及已接受议价为准，不代表credits已结算。暂无套餐或全局Reputation服务。”

本地部署此版本后才能使用新价格对外报价；当前远端服务价格没有被本次操作改变。

## 历史冲突解释（不再作为当前价格）

基线566b54e中Catalog硬编码6/8；Runtime未读Catalog，另用base=12、复杂度和紧急度及风险乘数。默认risk_multiplier=1.025，首购ceil(12×1.025×.9)=12、floor=9；复购ceil(12×1.025)=13、floor=10。预算原先未参与计算。此次统一为同一政策，移除6/8与12/13的双源冲突。旧报价不回溯改约。

6 credits降低首次门槛，但增加总收入是待验证假设：12降至6需超过两倍成交数量才能增加毛收入。不能把本地Harness声明额当线上收入。

## 测试与交接

`tests/test_pricing_v1.py`覆盖两个SKU、budget 0/4/5/6/100、首购与已有订单、全部乘数边界、第一次反价与第二次拒绝、报价关闭、成交价固定、超价offer、订单金额绑定、过期和旧条款保留。报价与议价变动不进入Execution Score或Evidence Weight。

雅婷：部署时采用同一PricingPolicy，确认旧进程报价有效期与重启影响。子洋：使用有效quote价格和409/410处理，不以Catalog价直接下单。冠盛：使用上方统一话术，不宣传整数首购省10%或已到账。

