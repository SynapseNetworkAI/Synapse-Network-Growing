---
created_at: 2026-03-26
updated_at: 2026-04-07
doc_status: active
---

# DRY And Reuse Baseline

适用范围：所有 Python 代码和模板生成逻辑。

## 规则

1. 重复的路径解析、文件写入、registry 处理，不允许在多个命令里重复实现
2. 重复的模板装配逻辑，必须抽成 helper 或 service
3. 新 agent 集成必须复用 adapter registry，不允许新增 if/else 分支地狱
4. 新 profile 安装必须复用统一 profile loader，而不是命令内手写流程

## 判断标准

满足任一条件就应抽象：

1. 同类逻辑出现两次以上
2. 同一个数据结构在多个模块重复解析
3. 同一个文件写入模式在多个地方重复出现