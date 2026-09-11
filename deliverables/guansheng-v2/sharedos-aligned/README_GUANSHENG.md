# 冠盛 V2 与思棋冻结合同对齐交付

本包包含思棋 sharedos-siqi-v1 完整源码，新增同源 Dashboard 和冠盛产品文件。没有改写评分、定价或 Seller 行为；未推送、未部署线上。

## 启动

需要 Python 3.11 或以上。在本目录执行：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e . pytest pytest-asyncio
$env:SELLER_API_TOKEN = '<自行设置本地演练凭据>'
$env:LEDGER_PATH = './dashboard-local.sqlite3'
.venv/Scripts/python.exe run_dashboard.py
```

打开 http://127.0.0.1:8786/dashboard/。Token 在页面中输入，页面仅保存在当前内存；不要公开截图凭据。本地演练有真实 HTTP 请求与本地订单，但不发生已验证的 Arena credits 结算。示例事件是假设任务，响应由实际 Seller 计算。

`run_dashboard.py` 只增加 `/dashboard` 和 `/product` 静态挂载，原有 API 不变。生产部署可由雅婷将同样两条挂载接入其现有 app，或从本适配入口启动。不要盲目覆盖最新主分支；先合入思棋价格与风险实现，再复制 `dashboard/`、`docs/guansheng/`、适配入口和验证脚本。本包不存在 `.openai/hosting.json`。

## 文件消费

- `/product/catalog.json`：Agent 服务说明、相对 Schema 引用及完整购买步骤。
- `/product/input.schema.json`、`trace_delivery.schema.json`、`risk_delivery.schema.json`：严格输入与交付封装合同；Schema URL 相对 catalog 位置解析。
- `/product/pitch.json`、`faq.json`、`sales.json`：UTF-8 JSON；templates、answers、rules 均为 `{id,title,content}` 数组。按买家目标选择内容；规则字段约束占位符填充。
- `pricing_policy.json`：冻结规则镜像，实际金额仍以 Runtime 返回为准。
- `risk_flags.json`：13项双语解释；实际报告只展示触发项，未知值保留。
- `submission.json`：线上信息保持 null，收到雅婷确认后再填写。不得当作生产服务发现配置。
- Markdown 文件提供同源可复制话术和提交正文。Agent Brain 可直接加载，仍需子洋将意图选择与其现有状态流程连接并签收；本包没有声称已接入其远端 Brain。

## 实测

启动服务并设置相同凭据后运行：

```powershell
$env:DASHBOARD_TEST_BASE = 'http://127.0.0.1:8786'
python verify_guansheng.py
python -m pytest tests -q
```

验收：两项SKU预算5与6；真实成功98、失败43；Risk解释与flags一一对应；严格输出Schema；缺Token 401；错误空输入422；Dashboard无快照fallback。前端浏览器实测记录和截图见上一级 verification。验证请求会产生本地测试订单，勿在正式Arena额度账户随意运行。

## 线上接入

页面默认当前同源地址，不把 localhost 写入最终提交。雅婷确认地址后可填写API Base URL；远端须配置允许展示页来源的CORS及正式认证方案。若使用SharedOS capability而非Bearer，应由Runtime适配认证，不能将本地Token测试作为平台授权证明。跨域失败、策略版本不符或预算越界会显示错误并停止下单。

本页手动操作用于调试，Arena自动销售不依赖本页。没有实现任意请求失败后的自动订单重试，避免未知结果时自动重复购买；出现超时应先结合接口记录核查订单状态。

## 待确认

Discord username、SharedNet node ID、purpose string、线上服务及Product Agent地址待雅婷确认；远端合并、线上认证与生产SLA、团队签收、最终提交均未标为完成。
