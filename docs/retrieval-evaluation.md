# 示例检索评测

使用 `examples/docs` 的 3 份虚构文档和 `examples/eval.jsonl` 的 12 条合成案例；10 条有目标文档，2 条没有目标文档。k=3，结果按片段排序后去重为文档。

| 指标 | 本次结果 | 分母 |
|---|---:|---|
| Recall@3 | 1.0 | 10 条有目标文档的案例 |
| MRR | 1.0 | 10 条有目标文档的案例 |
| 无匹配查询准确率 | 1.0 | 2 条无目标文档的案例 |

这些资料与案例同时构建，规模很小，没有独立留出集。因此此结果只能作为回归样例，**不能说明真实业务准确率、语义拒答率或生成质量**。部分问题仍返回额外文档，Recall 和 MRR 不衡量这类干扰，应补充 Precision@k 与真实留出集。

Recall@k = 召回的目标文档数 / 目标文档总数；MRR 为第一个目标文档排名倒数的平均。无匹配查询准确率仅检查检索结果是否为空。原始证据见 [retrieval-results.json](retrieval-results.json)。

| 问题 | 检索来源 | Recall |
|---|---|---:|
| API 超过速率限制后应该怎么重试？ | api-policy.md | 1.0 |
| API Key 可以写入浏览器吗？ | api-policy.md, leave-policy.md | 1.0 |
| HTTP 请求超时时怎么办？ | api-policy.md | 1.0 |
| 年假有几天，需要提前多久申请？ | leave-policy.md | 1.0 |
| 连续病假超过两天有什么要求？ | leave-policy.md | 1.0 |
| 每周远程办公几天？ | leave-policy.md | 1.0 |
| P0 事故发生时要通知谁？ | incident-playbook.md, api-policy.md, leave-policy.md | 1.0 |
| 错误率达到多少时考虑回滚？ | incident-playbook.md | 1.0 |
| 事故恢复后何时完成复盘？ | incident-playbook.md | 1.0 |
| 年假审批与事故回滚由谁负责？ | incident-playbook.md, leave-policy.md | 1.0 |
| 星际飞船曲率引擎 | (empty) | - |
| quantum penguin teleportation | (empty) | - |
