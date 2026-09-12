# 销售内容接入

Brain 的 SalesPolicy 从 resources/sales_v1.json 自动读取介绍与答复。本次增加免费询价、冷启动、刷分、同价原因与无 Artifact 的意图匹配，不改报告评分、价格算法或订单逻辑。完整多买家 Pitch 保存在 pitch.json；当前确定性路由不声称自动使用所有 Pitch 模板。

测试覆盖八类需求，子洋可直接使用 ArenaRunner.product_introduction 与 answer_buyer。目录描述来自 resources/product_catalog_v1.json，运行时价格由定价策略给出。雅婷部署时需要 run_dashboard.py 的同源静态挂载，才能提供 /product 和 /dashboard；这些路径不是原 api.app 自带的部署承诺。
