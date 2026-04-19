# Validation

## Validation Goals

证明系统已经能把 bug 从“日志里的错误文本”变成“可治理、可修复、可验证的 requirement backlog”。

## Validation Layers

### 1. Source Registry Validation

确认系统能正确列出内置 bug sources：

1. source key
2. source kind
3. ingest mode
4. dedupe scope
5. auto-intake policy

### 2. Intake API Validation

确认 `POST /api/bugs/intake` 能做到：

1. 接收 bug payload
2. 正确归一化
3. 正确去重
4. 返回 created / updated / deduped 结果

### 3. Dedupe Validation

确认同一 fingerprint 的重复 bug：

1. 不会反复创建新 bug record
2. 不会反复创建 requirement
3. 只增长 occurrence_count 和 recent evidence

### 4. Log Sweep Validation

确认 `bug_log_sweep` recurring workflow 能：

1. 发现新错误
2. 忽略无效噪音
3. 正确更新 bug registry
4. 为高价值 bug 生成 intake candidates

### 5. Requirement Materialization Validation

确认高价值 bug 转 requirement 时：

1. `source = bug_intake`
2. `source_ref = bug_key`
3. `target_project_path` 指向正确项目
4. `acceptance_contract` 与 workflow risk context 被正确补齐
5. priority 与 severity / impact 一致

### 6. Fix Validation

确认 bug requirement 关闭前，系统会验证：

1. 已有 root cause 或足够证据
2. 改动真正落在目标项目
3. regression guard 存在
4. 动态 validation contract 已执行
5. 同 fingerprint 没有继续以高频复发

## Recommended Tests

后续默认补这些测试：

1. `test_bug_source_registry_api.py`
2. `test_bug_intake_api.py`
3. `test_bug_fingerprint_and_dedupe.py`
4. `test_bug_log_sweep_workflow.py`
5. `test_bug_requirement_materialization.py`
6. `test_bug_validation_contract.py`
7. `BugDashboard.test.tsx` 或首页 company review bug 面板测试

## Done Criteria

这个 bundle 完成时，至少满足：

1. 日志或外部推送的 bug 能进入系统，而不是停在原始日志
2. 重复 bug 不会重复耗 token 或反复生成需求
3. 高价值 bug 能稳定转成 requirement backlog
4. bug requirement 关闭前必须完成修复验证
5. operator 可以在 company review 中看到 bug pressure 和 remediation progress
