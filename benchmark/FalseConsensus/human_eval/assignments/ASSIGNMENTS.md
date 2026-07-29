# 人工标注分工（4 人，2+2 双标）

两个任务，每个任务由 **2 人各自独立标注全集**，得到全量双标 → 可算标注者一致性（IAA）并对分歧裁定。
**互相不要看对方的表。** 参考 HTML 和 codebook 共享。

## Task A — 错误类型标注（论文 §3）
- 标注员：**P1、P2**（各标全部 134 条）
- 发给每人：
  - `../CODEBOOK.md`（类别定义 A–E + 说明）
  - `../taxonomy_reference.html`（浏览器打开，每条含题目/金标/错误停在的答案/probe 流/完整推理）
  - **自己那份空白表**：P1 → `taxonomy_P1.csv`，P2 → `taxonomy_P2.csv`
- 每人填：`HUMAN_type`（A/B/C/D/E）、`HUMAN_confident`（y/n）、`HUMAN_notes`
- 回收：填好的两份 CSV

## Task B — grader 判分抽查（附录）
- 标注员：**P3、P4**（各标全部 89 条）
- 发给每人：
  - `../CODEBOOK_grader.md`
  - `../grader_check_reference.html`
  - **自己那份空白表**：P3 → `grader_P3.csv`，P4 → `grader_P4.csv`
- 每人填：`HUMAN_grader_correct?`（y/n）、若 n 再填 `HUMAN_true_verdict`（correct/incorrect）、`HUMAN_notes`
- 回收：填好的两份 CSV

## 回收后我来做
- Task A：合并 P1/P2 → 报告 A–E 计数、两人一致性（κ）、逐条裁定分歧，作为论文里的"人工复核 of record"。
- Task B：合并 P3/P4 → grader 错误率 = 判错比例，带 95% CI，支撑那个薄边际。

## 备注
- 每份 `*_reference.html` 自包含，双击即可打开，不用联网。
- CSV 用 Excel / Google Sheets 直接打开，填完原样导出即可。
- 若只想先做一个任务，优先 **Task A**（论文正文点名要的就是它）。
