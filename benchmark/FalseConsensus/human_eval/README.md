# Human-eval — 两个自包含标注页

每个任务就是**一个 HTML 文件**,里面已经含:说明书 + 全部案例 + 页内标注 + 一键导出 CSV。
数据全部来自**已冻结、已提交**的结果,**不跑任何实验、不占 GPU**——双击打开即可用。

题目里的 **LaTeX 公式**用内联 KaTeX 渲染成真数学排版;竞赛题的 **`[asy]` 配图**已用 Asymptote
预编译成内联矢量图(SVG)直接显示,标注员看到的是真图,不是源码。全部资源内嵌,离线自包含。

| 文件 | 任务 | 量 | 用时 | 导出 |
|---|---|---|---|---|
| `taskA_taxonomy.html` | 错误类型标注(论文 §3) | 134 例 | ~40 min | `taxonomy_review_<名字>.csv` |
| `taskB_grader.html` | grader 判分核对(附录) | 89 行 | ~25 min | `grader_check_review_<名字>.csv` |

## 怎么用（发给同学）
1. 双击打开 HTML（离线即可，无需联网/装东西）。
2. 顶栏填**自己的名字**;逐条在卡片底部标注(进度自动存在浏览器,刷新不丢)。
3. 全标完点顶栏 **⬇ 下载 CSV**,把导出的 CSV 发回。

## 4 人分工（2+2 双标 → 可报标注者一致性）
- **Task A**:P1、P2 各发一份 `taskA_taxonomy.html`,**各标全部 134**。
- **Task B**:P3、P4 各发一份 `taskB_grader.html`,**各标全部 89**。
- 同一任务两人的表**互不相见**(否则一致性作废);同一个 HTML 发给两人即可,各自导出带自己名字的 CSV。
- 若只做一个任务,优先 **Task A**(论文正文点名要的就是它)。

## 回收后
- Task A:合并 P1/P2 → A–E 计数 + 两人 κ + 逐条裁定分歧(人工复核 of record)。
- Task B:合并 P3/P4 → grader 错误率 = 判错比例 + 95% CI(支撑那个薄边际)。

## 重新生成
```
python3 make_taxonomy_package.py      # -> taskA_taxonomy.html
python3 make_grader_check_package.py  # -> taskB_grader.html
```
两者都调用 `build_interactive.py`(共享的交互页生成器)。确定性、可复现。
