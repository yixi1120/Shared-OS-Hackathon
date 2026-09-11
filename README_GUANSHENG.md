# 冠盛 Dashboard 与产品材料 V3

本次从 main `3b5b99dad1703b873de5810b9743afce8365cb46` 新建 Guansheng-v3，仅新增本页列出的材料、展示适配入口和验证文件。没有复制旧 Guansheng 分支的历史、嵌套 Runtime、旧 Dashboard 或旧定价文件。现有 `src/`、依赖声明及思棋合同文件保持 main 原样。

两项服务均为 6 credits，底价 5。已知风险标记为 14 项；新增 `conflicting_terminal_task_state`，冲突时 `completed=false`、`reputation_eligible=false`。报告的完成计分项不加40分，标记不重复扣分。

## 交付入口

- [Word 手册](docs/guansheng/冠盛产品设计与自动销售交付手册V3.docx) 与 [Markdown 正文](docs/guansheng/冠盛产品设计与自动销售交付手册V3.md)
- [机器材料](docs/guansheng)：catalog、pricing_policy、pitch、faq、sales、risk_flags、Schema、submission
- [Dashboard 源码](dashboard)：成功、失败、终态冲突事件输入；所有报告来自 API
- [验证记录和真实截图](docs/guansheng/verification)
- [版本与新增范围](docs/guansheng/release.json)

Schema 从 main 的 `docs/siqi/schemas.json` 派生，`x-known-risk-flags` 注释列出14个已知标记，不改变原校验规则，也不使用封闭枚举拒绝未知标记。Risk 的 `interpretation.flags` 必须与实际风险逐项对应。

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

## 接入与提交状态

`/product/catalog.json` 的相对 Schema 可直接解析。Pitch、FAQ和销售规则可读取，Brain 的意图选择与团队签收仍由子洋确认。单笔报告不等于全局信誉，调用方自报不等于平台验证。

Discord username、SharedNet node ID、purpose string、线上服务及产品 Agent 地址继续在 `submission.json` 保持 null，等待雅婷确认。当前材料不声称已部署或完成比赛提交。主分支历史审计中旧价格用于追溯，不是本次新增材料的现售价格。
