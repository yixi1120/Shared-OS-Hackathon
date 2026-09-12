# 最终交付与提交检查表

- [x] 免费资源与两项付费报告已在 Catalog、Pitch、FAQ、销售规则及提交文案区分。
- [x] 标价6 credits、底价5；首购不承诺额外整数折扣。实际金额取有效报价或接受的议价。
- [x] 单句与20秒介绍均可读取 introduction.json。
- [x] 八类买家问题有中英文答案；Agent 使用打包销售内容与确定性意图路由。
- [x] 输入和输出 Schema 与当前 Runtime 对齐，风险标记保留完整14项及 interpretation.flags。
- [x] Dashboard 源码直接调用真实 API，另提供仅询价按钮。
- [x] Demo Script、真实响应截图与带说明的备用录屏已纳入交付。
- [x] 自报证据、单笔分析、报告交付与 credits 结算分别说明。
- [x] 所有待填官方信息只在 submission.json 保留 null，未使用示例值。
- [ ] 雅婷交付真实身份及线上信息后，更新 submission.json 并通过 check_submission.py。
- [ ] 对已确认线上 API 做同等合同验证；当前验证仅覆盖本地真实 API。
- [ ] 按主办方通知在 Discord 指定 submission 环节完成提交并保存回执。

最后三项按用户要求暂缓，不属于已完成或已验收的线上事项。测试记录见 verification；正式信息不得从演练截图、样例买家或本地地址推断。


验证基线：95 项代码测试通过；39 项 HTTP 合同检查与 9 项浏览器检查通过（本地真实 API，非线上结算验证）。
