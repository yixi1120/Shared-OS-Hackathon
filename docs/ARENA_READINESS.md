# Arena 上线与提交状态

核对时间：2026-09-13（香港时间）。本文件只记录已验证事实；网页、聊天截图和示例值不能替代真实运行标识。

## 已确认

- 产品：A2A Interaction Intelligence。
- 付费服务：A2A Interaction Trace 与 A2A Interaction Risk Report；常规价均为 6 credits，底价 5。
- 免费入口：health、catalog、interaction contract、Schema、示例和价格说明。
- GitHub：https://github.com/yixi1120/Shared-OS-Hackathon
- 公开服务：https://modelscope-sharedos.tail81043f.ts.net
- 外部客户端已验证 HTTPS、`/health`、Catalog、Schema、OpenAPI 与 Dashboard 返回正常；
  未携带凭据访问受保护端点返回 401。
- Discord server：AICOO。
- Discord username：`yixi1120_19547`；display name：`yixi1120`。
- 最终入口：AICOO → SHAREDOS HACKATHON → `#submission`。
- 提交频道：https://discord.com/channels/1507115506682040440/1547362093592743936
- `#submission` 在核对时为空论坛频道，尚未显示额外帖子模板。
- 官方在 `#arena-support` 表示 QA Room 已开放；正式 competition room 将在比赛开始前两小时发布。
- 官方 npm CLI 当前为 `sharednet@0.1.8`，要求 Node 22.18+；本机 Node 25.8.2 满足要求。
- QA Room 已成功加入：seat `i_E0nD7EzS5k`，SharedNet account principal `p_SDi8fKiq5X`。
- `whoami`、`session status`、`rooms`、`balance` 和 `ledger` 只读检查成功；凭据文件权限为 owner-only `0600`。
- 已使用官方兑换码 `HACK100` 领取 100 credits；真实返回为 balance=100、granted=100、sent=0、received=0，兑换记录已进入官方 ledger。
- QA 实例显示 `runtime_kind=codex`、`reach=public`、`status=online`，但 `agent_id=null`。
- 已由本队 seat 成功发送并读回 QA 消息 `msg_sS44mdor4R`（sequence 61），证明发言和定向读取链路可用。
- 官方已明确：`i_...` 是可调用 seat，`a_...` 是角色/tag 地址，`p_...` 是收款 account principal；三者不可互换。Room roster 是发现目录，seat ID 可公开。
- 官方已明确 credits 使用 `pay <p_...|a_...|i_...> <amount> --memo ... --room`，官方 ledger 是结算账本；付款成功与房间回执发布是两个独立操作。

QA Room 邀请凭据不写入 Git 仓库。需要时从 Discord `#arena-support` 获取。

官方 CLI 的安全准备命令：

```bash
node --version
npx sharednet login
npx sharednet join '<从Discord复制的QA或正式房间邀请>'
npx sharednet rooms
```

登录和加入房间会建立外部账号/房间状态，应由账号本人确认后执行。CLI 凭据位于用户配置目录，项目内的 `.sharednet/` 已加入 `.gitignore`。

## 仍待真实环境提供

- 正式比赛房间的 SharedNet seat ID；历史材料中的 node ID 单独保留，不能假定二者相同。
- SharedOS principal ID。
- Agent address。
- 官方房间的真实消息格式和 Agent 调用记录。
- 正式比赛中的真实转账、room receipt 和双方 ledger 对账样本。
- 两个 Round 全程在线记录。

上述值不得使用 QA 示例、其他参赛者 ID、localhost 或猜测值代填。

## 不依赖正式房间、现在可以完成

- [x] 冻结两项付费服务名称和价格。
- [x] 在 Catalog 和提交材料中区分免费与付费能力。
- [x] 写入 Discord username 和 `#submission` 地址。
- [x] 保留未确认 Runtime 标识为 null。
- [x] 使用 QA Room 验证登录、join、历史读取、身份、房间、余额与凭据权限。
- [x] 经用户确认发送一条最小QA消息，并验证say/read/wait与cursor推进。
- [x] 核对官方 credits、ledger、seat/tag/principal 语义并在代码中实现读取、付款和入账核验适配层。
- [x] 用独立本地 HTTP 进程验证 Agent-facing CLI 的 health、catalog 与完整报告交付。
- [x] 完成公开部署并从非本机调用公开接口。
- [ ] 安全注入 Seller Token 后完成线上 Quote → Order → Deliver → Query。

## 正式房间发布后的顺序

1. 雅婷从 Discord 官方消息取得正式 competition room 邀请。
2. 使用唯一参赛 Agent 执行 `sharednet join`，立即保存控制台输出和 seat ID。
3. 回填 `docs/guansheng/submission.json` 中的 Runtime 标识。
4. 子洋从正式 Room roster/消息发现服务，通过对方公开 MCP/CLI/HTTPS 调用，并用官方 pay/ledger 完成购买与对账。
5. 思棋核验真实事件的 provenance 与报告结果。
6. 冠盛核对最终帖子，团队确认后发布到 Discord `#submission`。
7. 保存提交帖链接或截图作为提交回执。

## 比赛期间

- Agent 在周日晚 21:00–23:00（北京/香港时间）两个 Round 全程在线。
- 房间通信与 Seller Runtime 同时运行，禁止依赖人工发言或临时修复。
- 只把官方房间可核验的 credits 行为作为结算事实；本地订单只表示服务工作流状态。
- 出现断联时从 checkpoint、操作日志和远端可见状态恢复，保持同一幂等键。
