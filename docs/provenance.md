# 报告溯源与引用

BettaFish 的报告溯源链分为 `SourceRecord`、`EvidenceRecord` 与
`ClaimRecord` 三层，定义位于 `common/provenance/`：

- `SourceRecord` 保存原始来源的标题、平台、作者、发布时间和 URL；
- `EvidenceRecord` 保存从原始结果提取的可引用片段、来源 ID 和检索范围；
- `ClaimRecord` 将报告中的事实、指标、推断、预测或建议绑定到证据 ID。

这三层分别回答“来自哪里”“引用了哪段原始内容”和“报告中的哪项结论使用了它”。
Query、Media 和 Insight 引擎会随各自结果保存 `.provenance.json` 审计文件。
网页工作流还会为每次搜索创建独立的 `run_id`，子引擎经本机回调提交本轮结果，报告端只消费该轮的证据，避免使用旧搜索遗留的报告或侧车文件。

## 报告行为

章节生成前会按章节主题选择有限的相关证据，而不是把全文引擎报告当作证据输入。装订阶段会再次执行来源和主张门禁：

- 事实和指标必须有有效证据 ID；结论中的数字还必须能在证据片段或标准化值中找到；
- 推断只有一条证据时显示为“弱支持”，没有证据时不输出；
- 预测和建议会与事实段落分开标记；
- 论坛讨论文本只作为上下文，不能直接作为证据；
- 未找到可追溯证据的内容会替换为明确的占位文本，而不会保留生成式结论。

HTML 报告会在段落末尾显示引用上标。点击上标可打开原始 URL；悬浮详情包含来源标题、平台、发布时间、证据片段和“引用理由”。`Document IR` 还包含 `provenanceIndex` 和 `claimIndex`，便于审计、重渲染和程序化检查。

Insight 的数据库证据保留表名、记录 ID、查询时间、筛选条件、时间窗口、样本量、聚合方法及行 ID 等血缘信息。若其来源没有公网 URL，页面仍显示这些可审计的内部来源信息，但不能跳转到外部网页。

## 验证

使用项目环境执行专项回归：

```powershell
conda run -n bettafish python -m pytest -q `
  tests/test_provenance_models.py `
  tests/test_provenance_dedupe.py `
  tests/test_provenance_selector.py `
  tests/test_provenance_claim_gate.py `
  tests/test_provenance_runtime.py `
  tests/test_html_citations.py
```

这组测试覆盖模型兼容、去重、章节选择、主张门禁、运行态隔离、无 URL 外部证据的拒绝，以及从装订后的 IR 到可点击 HTML 引用的完整路径。
