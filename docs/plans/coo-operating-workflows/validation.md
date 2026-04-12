# Validation

## Validation Goals

证明 `Synapse-Network-Growing` 已经像 COO 系统一样运转，而不是只会展示任务。

## Validation Layers

### 1. Role Contract Validation

确认每个核心 role 都具备：

1. mission
2. input channels
3. outputs
4. decision rights
5. handoff rules

### 2. Requirement Intake Validation

确认需求池可以持续从这些来源接收 requirement：

1. manual
2. optimization signals
3. incident follow-ups
4. company review bundles
5. onboarding / policy gaps

### 3. Daily Rhythm Validation

确认 daily workflows 能稳定运行：

1. 早间 intake sweep 能产出候选 requirement
2. dispatch loop 能启动 ready requirements
3. end-of-day closeout sweep 能生成 compact / summary evidence

### 4. Weekly Rhythm Validation

确认 weekly workflows 能稳定运行：

1. 自动生成 company review
2. 自动生成 next-cycle bundle
3. 自动生成 automation candidate summary

### 5. Operator Experience Validation

确认 operator 首页能回答：

1. 今天最该推进什么
2. 哪些事项卡在人工判断
3. 哪些项目预算紧张
4. 哪些人工 gate 值得自动化

## Automation Tests

后续实现时建议默认补这些测试：

1. source registry API tests
2. recurring workflow registry API tests
3. daily intake workflow integration tests
4. scheduler follow-through loop tests
5. company review weekly workflow tests
6. operator dashboard frontend tests

## Done Criteria

这个 bundle 完成时，至少应满足：

1. 系统每天能自动产出新的高价值 requirement，而不是需求池长期为空
2. 系统每周能自动生成 company review 和 next-cycle bundle
3. operator 不需要盯 task 明细，也能看懂公司当前经营状态和下一步动作
4. role 具备明确 owner 语义，而不是只有 persona 文案
