# Interaction Report V1 风险标记与双语解释

与 risk_rules.py 的14项解释逐字一致。触发条件见 INTERACTION_REPORT_V1.md 第4节；标记不额外扣分。

| 标记 | 中文 | English |
|---|---|---|
| `missing_terminal_task_state` | 缺少终态 | No completion or failure state was recorded. |
| `artifact_not_delivered` | 未记录交付 | No artifact delivery was recorded; absence is not proof of non-delivery. |
| `invalid_stage_order` | 阶段乱序 | Timestamp-ordered events regress in lifecycle stage. |
| `schema_validation_failure` | schema 不合规 | At least one submitted event declares schema_valid=false. |
| `interaction_disputed` | 存在争议 | A dispute was recorded; the report does not adjudicate it. |
| `conflicting_terminal_task_state` | 终态冲突 | Both task_completed and task_failed were recorded; the task is not treated as completed or reputation-eligible. |
| `evidence_not_reputation_eligible` | 不具备基础纳入资格 | The trace fails the V1 terminal-state and trusted-source gate. |
| `task_start_not_recorded` | 未记录开始 | No task_started event was recorded. |
| `completion_not_recorded` | 未记录完成终态 | No task_completed event was recorded; a failure terminal may still exist. |
| `task_explicitly_failed` | 明确失败 | A task_failed event was recorded; report delivery can still succeed. |
| `latency_not_computable` | 延迟无法计算 | The trace lacks a request/start or completion/failure timestamp. |
| `evidence_reference_missing` | 证据引用缺失 | At least one event has no non-empty evidence reference; references are not verified here. |
| `weak_evidence_source` | 证据来源较弱 | The weakest source is bilateral or self-reported; execution score is unchanged. |
| `credit_settlement_not_evaluated` | 结算未评估 | No trusted settlement evaluation is attached; declared price is not payment proof. |
