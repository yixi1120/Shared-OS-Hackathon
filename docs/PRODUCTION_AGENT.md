# SharedNet 生产 Agent 启动手册

本手册只描述仓库已经实现的行为。正式房间 ID、邀请、member token、API token、
principal ID 和 Agent address 不得使用 QA 值、示例值或猜测值替代。

## 当前可运行组件

- `commerce-api`：Seller FastAPI。
- `run_dashboard.py`：Seller API 与同源 Dashboard。
- `sharednet-agent listen`：正式房间自动加入/身份恢复、持久收件箱和产品应答。
- `SharedNetRoomClient`：正式 room 通信，以及官方 balance/pay/ledger 与到账核验。
- `sharednet-agent arena`：仅在主办方另行发布完整业务 REST 路由时使用；当前正式形式以 Room 消息和各产品公开接口为准。
- `seller-harness`：本地并发与 soak 验证，不连接正式 credits。

房间监听与 Web API 是两个进程。只启动 Dashboard 不会启动 SharedNet Agent；只启动
SharedNet Agent 也不会托管 Seller API。

## Seller API 临时身份绑定

官方 SharedOS capability 验证合同尚未发布时，可以通过服务器 secret 环境变量配置每个
Agent 独立的临时凭据：

```bash
export SELLER_API_TOKEN='<仅供运维的 break-glass token>'
export SELLER_AGENT_TOKENS_JSON='{"<buyer/principal ID>":"<至少24字符的唯一随机token>"}'
```

应用启动时立即散列各 Agent token，`GET /v1/auth/whoami` 返回它绑定的 principal。
Quote 的 `buyer_id`、后续议价、订单、交付和查询均强制属于同一 principal；用 A 的 token
冒充 B 会返回 403。运维 token 可以处理任意买家，只用于故障恢复，不能发给参赛 Agent。

该映射必须作为服务器 secret 注入，不得写入 `.env.example` 的真实值或提交 Git。它是
SharedOS 正式 capability 验证前的安全过渡方案，不会把自报事件升级成平台验证证据。

## 首次启动

在雅婷的持久服务器环境配置以下变量。尖括号内容必须由官方真实信息替换：

```bash
export SERVICE_BASE_URL=https://modelscope-sharedos.tail81043f.ts.net
export SHAREDNET_ROOM_ID='<rom_...>'
export SHAREDNET_INVITE_TOKEN='<rit_...>'
export SHAREDNET_STATE_PATH=/persistent/sharedos/.sharednet/runtime-identity.json
export SHAREDNET_INBOX_PATH=/persistent/sharedos/.sharednet/inbox.sqlite3

uv run sharednet-agent listen --announce
```

成功后日志只显示 room、member ID 和公开服务地址，不输出 member token。身份文件应为
`0600`，父目录应为 `0700`。首次 join 成功后，从运行环境移除 invite token；以后会自动
复用身份文件中的 member token。

如果平台负责把 secret 注入环境而不允许本地身份文件保存 token，则同时设置：

```bash
export SHAREDNET_MEMBER_ID='<正式 member/seat ID>'
export SHAREDNET_MEMBER_TOKEN='<sni_...>'
```

两者必须成对出现。环境身份与已保存身份不一致时程序会拒绝启动，避免静默换号。

## 自动应答协议

监听器只回应以下输入：

1. JSON `type` 为 `service_discovery`、`discover` 或 `catalog`，并发给本 Agent 或广播；
2. JSON `type` 为 `product_query`、`question`、`inquiry`、`health` 或 `ping`；
3. 自然语言明确包含产品名、Agent 名或一个服务 ID。

回复使用 `a2a-interaction-intelligence.room.v1` JSON，并包含公开 URL、服务、价格、
`reply_to` 和 `credit_settlement=not_evaluated`。监听器不会在公开房间发布任何凭据。
房间内的 `Paid ... (txn_...)` 文字只负责公开交易上下文；必须再用官方 ledger 核对
transfer ID、收款 principal、金额、room 和 memo 才能认定到账。

未点名本产品的普通聊天会被确认消费但不回复，避免在共享房间刷屏。本 Agent 自己发送的
消息也不会触发循环应答。

## 断线与幂等

收到的消息和接收 cursor 在同一 SQLite 事务落盘，然后才进入处理。处理成功后才确认。
如果回复已经在 SharedNet 可见但本地尚未来得及确认，重启会使用 `reply_to` 标记搜索远端；
找到同一回复就只确认原消息，不再次发送。

这能覆盖“发送成功、确认前中断”的常见窗口，但 SharedNet `join` 本身没有公开幂等键。
因此 join 返回到身份文件落盘之间发生进程强杀时，仍需要官方身份查询/恢复能力才能严格
保证不会产生第二个 seat。程序使用进程锁阻止同一身份文件启动两个监听器；首次 join 时仍
不要让不同身份路径的两个实例同时使用同一邀请。

## 官方 credits 与 LangGraph 边界

SharedNet 已正式提供 balance、redeem、pay 和 ledger。付款请求与 `--room` 回执是两次独立
操作：即使回执发布失败，付款仍然最终有效，必须先查 ledger，禁止自动重付。仓库适配层为
付款和回执分别派生稳定幂等键，并支持按 transfer ID 核对收款 principal、金额、room 和 memo。

产品发现来自 Room roster，产品调用来自各队公布的 MCP、CLI 或 HTTPS 接口；当前没有全局
产品 registry，也没有统一 discover/invoke/critique/ranking REST 合同。因此正式运行不应等待
一个并不存在的 buy route。只有主办方以后另行发布完整业务 REST 合同时，才配置：

```bash
export ARENA_BASE_URL='<官方 API origin>'
export ARENA_API_TOKEN='<官方 token>'
export AGENT_NODE_ID='<正式 Agent ID>'
export ARENA_DISCOVER_ROUTE='<官方 discover path>'
export ARENA_INVOKE_ROUTE='<官方 invoke path，允许 {service_id}>'
export ARENA_CRITIQUE_ROUTE='<官方 critique path>'
export ARENA_RANKING_ROUTE='<官方 ranking path>'
export ARENA_BUY_ROUTE='<官方 buy path，允许 {service_id}>'
export ARENA_RECONCILE_ROUTE='<可选官方 reconcile path>'
```

然后分别执行：

```bash
uv run sharednet-agent arena --mode critique --run-id official-critique-round
uv run sharednet-agent arena --mode market --run-id official-market-round
```

该兼容入口使用 SQLite LangGraph checkpoint 和 outbound operation journal。缺少任何必需
路由时会拒绝启动。当前 live path 则使用生产 Room listener、对手公开接口和官方 credits
适配层；分析报告仍固定 `credit_settlement=not_evaluated`，不把付款变成证据质量。

## 比赛前验收

- [ ] 两个持久路径位于服务器持久盘，重启后仍存在。
- [ ] 首次 join 只运行一个实例，随后移除 invite token。
- [ ] 重启后 member/seat ID 不变。
- [ ] 从另一 seat 发送一次 discovery，收到且只收到一条 `service_offer`。
- [ ] 重放同一 `message_id` 不产生第二条回复。
- [ ] 公网 `/health`、Catalog、Schema 和 Dashboard 正常。
- [ ] 使用安全注入的 Seller Token 完成 Quote → Order → Deliver → Query。
- [ ] SharedOS principal/capability 鉴权方案由官方确认；未确认前不声称已完成。
- [ ] 正式两轮期间 Web API、房间监听、持久盘和隧道均全程在线。
