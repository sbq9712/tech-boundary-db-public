# MAINTENANCE —— 修订流程（发现问题 → 修订完成 → 发布升级）

本包是**快照打包**：运行层单源在开发仓 `outputs/github-triage-20260615-23/`（管线）与
`outputs/classification-scoring-rules-20260909/`（规则数据 + 机制表格）。**不要直接改本包内
`pipeline/`、`rules/`、`docs/` 的快照**——按下面流程在单源改，再同步过来。

## 1. 修订流水线（六步，顺序不可省）

```
① 反馈登记：问题案例（URL/题名/期望档位）写入开发仓 问题.txt（= docs/requirements_ledger.txt 台账）
② 备份：outputs\github-triage-20260615-23\_backup_vNN_日期\（管线 + score_data.py；历轮备份链从不断崖）
③ 改单源：build_strict_semantic_triage.py（规则数据动 outputs\classification-scoring-rules-20260909\*.py）
④ 验证链：
   a. 06-26 / 06-25 两测试批重建（LLM 决策复用）→ 与上一版做全量 diff，迁移必须逐条对得上修订意图，零意外迁移
   b. 七套回归全绿：verify_v104 / v103 / v102_feedback、verify_strict_semantic、
      check_typing / check_policy_finance / check_scope_regression
⑤ 同步本包：
   pipeline\ + rules\ 快照 → ENGINE_VERSION 与 method 串尾标签 →
   README 版本历史 + AI_INTERFACE §5 机制总表 → tests\test_smoke.py 补新机制断言 →
   冒烟 + pytest + 实数据 e2e（cli run --batch-dir …）→ docs\ 表格快照
   （02 评分框架表用开发仓 patch_workbooks_vNNN 系列幂等脚本增补后拷入）
⑥ 留痕：outputs\triage-review-日期-vNNN\修复报告（逐条原因：根因→改点→验证→边界）＋
   测试报告 §增量 ＋ 会话记忆更新
```

## 2. 版本递增规则

- 机制行为变化（新规则/新守卫/改档位）→ 小版本 +1（v1.08 → v1.09），method 串尾追加标签
  （惯例：`+机制名-v1NN`，见 `engine.py METHOD_TAG`）。
- 只改文档/表格不动行为 → 版本不变，同步 docs 即可。
- 常数草案（阈值/词表/窗口，标注于 AI_INTERFACE §5.7）：每批回测观察，不稳即调，调整也要走完整流水线。

## 3. 铁律（历轮教训）

1. **不删旧机制**：历轮用户口径只叠加不回退；问题.txt 台账是最高基准。
2. **题名锚定**：抬档证据（瓶颈/首证/新技术豁免）以题名为准，正文背景提及不抬档（M1 口径）。
3. **审计链完整**：每个档位变化必须能在 gateActions / scoreAudit 里找到规则号与原因串；
   硬上限命中但档位已低时也要留"上限确认"审计行。
4. **备份先行**：任何机制修改前先落 `_backup_vNN_日期\`，无备份不动手。
5. **双源合一**：代码（rules\*.py）与表格（docs\*.xlsx）改其一必须同步另一个，版本页对齐。

## 4. 调用方（服务器/GitHub）升级方式

本包无状态、`run()` 幂等全量重算——**整个 triage_engine\ 目录替换**即可升级：
```bash
python -m triage_engine.cli version        # 确认版本串尾标签 = 预期版本
python -m triage_engine.tests.test_smoke   # 冒烟过 = 可信任
```
历史 LLM 决策（llm_semantic_decisions.json）与升级前兼容可复用；不兼容时 run_llm 会按 url 重新判定增量。

## 5. 历轮修订档案（追溯入口）

| 轮次 | 报告位置（开发仓 outputs\） |
|---|---|
| v1.03/v1.04 档位政策 | triage-review-20260919 / 20260920-v103 / v104 |
| v1.05 事件级去重 | test-triage-20260625 §6 |
| v1.06 论文统一档位 | triage-review-20260922-v106 |
| v1.07 参考区 + 打包 | triage-review-20260923-v107 |
| v1.08 未来态/汇总稿/媒体解读裁决 | triage-review-20260923-v108 |

（新轮次按 `triage-review-日期-vNNN\修复报告_vN.NN_逐条原因.md` 命名续接。）
