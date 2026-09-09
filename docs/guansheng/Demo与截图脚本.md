# Demo Script、截图与备用录屏

## 90 秒英文演示脚本

| 时间 | 屏幕内容 | 英文讲稿 |
|---|---|---|
| 0–12 秒 | 项目名与机器目录 | “Agents need evidence after a trade, not just a convincing pitch. We return a structured transaction trace with explicit source limits.” |
| 12–25 秒 | 真实服务目录与输入 schema | “A buyer can read the description, price, input, and output without opening a website. We accept lifecycle metadata and evidence references, not raw prompts.” |
| 25–48 秒 | 真实外部 Agent 调用；显示请求、交付 report 与 receipt | “Here is an authorized external call. The result reports what happened in this transaction, with evidence references and the runtime’s measured delivery time.” |
| 48–62 秒 | 真实失败例 | “Invalid or undeliverable requests produce an explicit failure. We do not turn a failed operation into a successful trace or a reputation event.” |
| 62–74 秒 | 真实 SharedOS denied 审计 | “This caller lacks permission. SharedOS denies the invocation before private data or a paid delivery is released.” |
| 74–86 秒 | 报告置信度与来源详情 | “One trade is not global reputation. Self-reported evidence stays self-reported, and paying for the report cannot improve the score.” |
| 86–90 秒 | 服务名称与真实调用地址 | “Ask for a quote through the listed SharedNet service.” |

上面“真实”段落只有实际运行后才能录制。当前本地重放用于彩排，讲稿必须改为“synthetic contract fixture”，不能声称已授权外部调用或平台 denied。录制成片应≤120秒，推荐90秒；保留备用本地视频，Arena 不依赖人为播放或操作。

## 三个本地可复现彩排

```text
uv run python scripts/demo_guansheng.py
```

- 成功：精确重放已提供的合成 report，显示 `synthetic_fixture`；93.2 仅是团队样例值。
- 失败：事件时间逆序，返回 `EVENT_ORDER_INVALID`，没有 report。
- 未授权：测试上下文返回 `UNAUTHORIZED`，不是实际 SharedOS 授权测试。

这些是已可运行的本地 Runtime 示例；不是线上交易证据。真实例按《集成与验收.md》运行并留存平台证据。

## 截图清单与图注

| 文件建议名 | 必须展示 | 图注 |
|---|---|---|
| 01-live-service-catalog.png | 真实服务名称、价格、调用方式 | “Machine-readable service listing used by the Arena runtime.” |
| 02-live-success-trace.png | 真实 transaction_id、结果、single-transaction、证据引用 | “One transaction trace; source verification is limited to the referenced evidence.” |
| 03-live-failure.png | 真实错误码与无成功交付 | “A controlled failure returns an explicit error instead of a successful report.” |
| 04-live-authorization-denied.png | 真实 SharedOS deny 与审计引用 | “Unauthorized invocation denied by SharedOS.” |
| ui-synthetic-preview.png | 保留“合成测试”横幅 | “Synthetic interface fixture. Not a live trade or platform verification.” |

截图只展示与论点有关的元数据，隐藏密钥、私人消息、完整正文。不能裁掉 synthetic 标识或把弱来源的说明裁掉。实际截图和录屏应以团队 Runtime 为输入；当前没有真实平台数据，因此不能生成名为 live 的证据图或声称备用录屏完成。

## 录制前检查

- [ ] 时间和官方报名条件已确认。
- [ ] 三类真实例在测试环境已完成。
- [ ] 报告和截图与真实接口输出一致。
- [ ] 使用的是思棋批准的价格及指标版本。
- [ ] 录屏少于120秒，无密钥、无人工补造交易步骤。
- [ ] 本地备用视频已能正常播放；若提供链接，评委能访问。
- [ ] 提交页中的节点、服务地址与画面一致。
