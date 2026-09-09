# 冠盛工作入口

先读《冠盛交付与最新代码核查.md》，其中逐项列出已实现、已验证与仍受团队环境阻塞的内容。

```text
uv sync --frozen
uv run pytest -q
uv run python scripts/demo_guansheng.py
uv run commerce-api
```

启动后：

- `http://localhost:8000/dashboard/`：最小调试展示页。
- `http://localhost:8000/v1/catalog`：服务目录、内嵌输入输出 schema、真实 REST 购买步骤。
- `http://localhost:8000/v1/sales`：简短介绍、FAQ、销售说明。
- `POST /v1/sales/respond`，示例输入 `{"topic":"provenance"}`：自动答辩，不依赖模型。
- `http://localhost:8000/docs`：完整 API 文档。

此 API 仍是本地开发 Runtime。不要将它直接公开作为已接通 SharedOS 的生产服务。真实授权、账户认证及网络结算由雅婷继续对接。

`scripts/demo_guansheng.py` 调用实际 FastAPI 代码并使用临时内存账本，将结果写入 `local-runtime-results/`，刷新 Dashboard 内置样例。它不会花费 Arena credits，也不会访问其他 Agent。

提交文案中的真实账号、节点、purpose、服务地址和审计证据必须补齐。网页空状态与本地演练标签必须保留，不得将演练结果包装成线上成交。
