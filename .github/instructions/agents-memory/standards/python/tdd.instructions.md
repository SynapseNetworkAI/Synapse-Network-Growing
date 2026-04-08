---
created_at: 2026-03-26
updated_at: 2026-04-07
doc_status: active
---

# TDD Baseline

适用范围：所有会改变行为的 Python 代码。

## 规则

1. Bug fix 必须补回归测试，除非是纯包装层且无可测试行为
2. 新 service 逻辑必须至少有最小单元测试
3. 行为变更必须同步更新测试、文档和命令说明
4. 测试优先围绕 observable behavior，而不是内部实现细节

## 最小要求

1. `services/` 逻辑新增分支时，要新增对应测试覆盖
2. 文件系统副作用要断言输出文件内容，而不是只断言函数被调用
3. `doctor`、`register`、`sync`、`bootstrap` 这类关键流程需要回归测试