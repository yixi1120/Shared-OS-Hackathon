# 冠盛最终产品材料 V4

基于 main 9dff6be664f216769621a6ff6e72e3372581cc3a 更新产品内容、销售意图匹配和 Dashboard。评分、定价与订单算法保持当前 main。两项报告均6 credits、底价5；目录、健康检查、Schema、示例输入和报价免费。全部14项风险标记保留。

## 交付入口

- docs/guansheng/catalog.json 与相关 Schema：机器调用说明。
- introduction.json、pitch.json、faq.json、sales.json 及对应 Markdown：最终销售内容。
- 冠盛最终产品交付手册V4.docx：可直接阅读的最终说明。
- dashboard/：真实 API 面板源码，支持仅询价及三个报告场景。
- docs/guansheng/verification/：本次验证与截图。
- docs/guansheng/media/A2A_Interaction_Intelligence_Backup.webm：字幕备用录屏。
- SUBMISSION.md、DEMO_SCRIPT.md、FINAL_CHECKLIST.md：提交文案与操作流程。

官方待填信息仅在 docs/guansheng/submission.json 中保存 null；按用户要求暂缓等待雅婷及正式提交。历史 V3 手册由 V4 替代。既有团队历史审计文件中的旧版本数字不代表现售价格。

## 本地启动

需要 Python 3.11 以上。在仓库根目录执行：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e . pytest pytest-asyncio
$env:SELLER_API_TOKEN = '<自行设置本地演练凭据>'
$env:LEDGER_PATH = './dashboard-local.sqlite3'
.venv/Scripts/python.exe run_dashboard.py
```

打开 http://127.0.0.1:8786/dashboard/。凭据在页面输入，仅保存在当前页面内存。`run_dashboard.py` 给现有 FastAPI app 增加 `/dashboard` 和 `/product` 静态挂载，评分、定价与订单逻辑直接使用当前 main 实现。

页面默认连接同源 API；也可填写明确的远端地址，但对方须正确配置 CORS 与认证。报价策略不匹配、超预算、未接受议价或接口错误时停止下单。无凭据测试只证明配置后的本地 Bearer 保护，不代表 SharedOS capability 验证。

## 验证

保持本地服务运行，在另一个终端设置相同的 `SELLER_API_TOKEN`，执行：

```powershell
$env:DASHBOARD_TEST_BASE = 'http://127.0.0.1:8786'
.venv/Scripts/python.exe verify_guansheng.py
.venv/Scripts/python.exe -m pytest tests -q
```

HTTP 检查创建本地演练订单并写入 `docs/guansheng/verification`，不要直接使用正式比赛额度。冲突示例使用 main 的 `conflicting_terminals` 事件，预期57.5分、完成false、信誉资格false；成功98分，失败43分。API和截图属于本地固定输入的实际响应，不证明线上成交或已结算 credits。
