# 运行与实验索引

本页只索引有明确日期、证据边界和复现/来源说明的运行记录。

## 2026-09-15：正式 Arena 运行归档

- 新增：[`LIVE_RUN_2026-09-13.md`](LIVE_RUN_2026-09-13.md)
- 运行日期：2026-09-13
- 归档日期：2026-09-15
- 代码基线：`f35093b`
- 关键事实：正式 Arena 2 seat 加入；listener 至少监听至 sequence 808；官方账本确认累计收入 `received=36` credits。
- 关键限制：未保存全部 buyer input、trade ID、artifact 与交付回执，因此不宣称全部收入已经完成业务交付。

## 2026-09-11：Seller 两小时 soak

- 记录：[`SOAK_TEST_REPORT.md`](SOAK_TEST_REPORT.md)
- 观察时长：7,755.5 秒
- 并发：16
- 唯一交易：32,272，全部 `delivered`
- 边界：本地 Seller Runtime 测试，不包含正式 SharedNet 和 credits。
