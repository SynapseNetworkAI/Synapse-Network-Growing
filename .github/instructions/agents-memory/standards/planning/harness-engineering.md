---
created_at: 2026-03-26
updated_at: 2026-04-07
doc_status: active
---

# Harness Engineering Baseline

接受 Harness Engineering 作为当前项目的统一工作流基线。

## 核心原则

1. 把仓库当成记录系统
2. 短入口文档做地图，不做百科全书
3. 把规则转成可执行约束，而不是只留在文字里
4. 把人类偏好编码成结构、模板、lint、测试和校验
5. 通过持续清理防止熵扩散

## 对 Agents-Memory 的要求

1. 所有新增能力都应有 docs、code、validation 三件套
2. 复杂工作应有 plan / task graph / validation route
3. 过期文档和不再匹配产品定义的内容必须持续清理
4. planning bundle 和核心设计文档都必须带可验证的文档元数据
5. task 状态、实现状态和文档状态必须能被脚本校验，而不是只留在 prose 里