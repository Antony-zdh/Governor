# Stage 6 标注指南（Probe Validity Audit）

对应 `plan.md` §4.4。同样内容也内嵌在 `annotate.html` 页面底部的折叠区域里，
这里作为独立文档存档。

## 主标签（每个 probe 选一个）

| Label | 定义 |
| --- | --- |
| `supported_correct` | prefix 已经充分支持当前 probe，且答案正确 |
| `supported_wrong` | prefix 已经形成明确但错误的答案 |
| `tentative_guess` | prefix 尚未完成，probe 只是被迫猜测 |
| `incomplete_answer` | 答案被 token 限制截断 |
| `format_artifact` | 输出形式与任务不匹配 |
| `inconsistent_with_prefix` | probe 与 reasoning prefix 明显矛盾 |
| `ambiguous` | 无法可靠判断 |

## 二元字段（可多选，独立于主标签）

- `valid_as_current_answer` — 这个 probe 输出是否可以作为模型此刻真实答案的合理代表
- `ready_to_stop` — 如果 Governor 在此刻停止生成，是否合理
- `answer_complete` — 答案本身（不考虑对错）在 10 token 内是否说完整了
- `prefix_contains_support` — reasoning prefix 中是否包含推导出该答案的实际依据
- `requires_more_reasoning` — 模型此刻是否明显还需要更多推理才能给出可靠答案

## 判断要点

重点看 reasoning prefix 的最后几句话：

- 是否已经在陈述/复述一个结论（→ 倾向 `supported_*`）；
- 还是仍在演算过程中被 probe 打断（→ 倾向 `tentative_guess` 或 `incomplete_answer`）；
- probe 输出格式明显对不上任务类型 → `format_artifact`（具体子情况见下）；
- probe 答案与 prefix 里刚推导出的结果对不上（→ `inconsistent_with_prefix`）；
- 以上都判断不了 → `ambiguous`，不要勉强塞进其他标签。

### `format_artifact` 的常见子情况

探针后缀固定是 `**Final Answer**\n\n\[ \boxed{`，只续写 10 个 token。以下情况都算
"输出形式与任务不匹配"（plan.md §4.4 原文），不是内容层面的对错问题：

1. **boxed 结构没收尾**——10 token 内没写完 `\boxed{...}` 的右括号/LaTeX 结构，
   截成半截（如 `\boxed{\frac{1}{2`）。跟 `incomplete_answer` 的区别：后者是
   "内容还没想完"，前者是"就算内容想完了，这几个 token 字面呈现的结构也不是
   一个可用答案"——两者常常同时发生，选更贴切的那个。
2. **答案类型跟题目要求对不上**——如选择题(ABCD)本该输出字母却写出具体数值，
   或反过来非选择题却蹦出单个字母（可能只是变量名巧合）。
3. **同一个 boxed 里塞了多个并列候选**——如 `\boxed{2 \text{ or } 3}`，说明推理
   还没收敛，被 10-token 格式硬挤成"一个答案"的样子。
4. **占位符/模板字面量残留**——如 `\boxed{X}`、`\boxed{\text{answer}}`，没有真正
   代入具体值。
5. **续写成推理性文字/公式片段而非独立答案**——如 `= 3x + 2` 这种展开式片段，
   不是一个自洽的答案值。
6. **表示形式不满足题目规范但内容本身没错**——如要求"最简分数"却给了小数近似，
   要求区间/集合却只给了单点值。
7. **多余符号导致自动提取器抓空/抓歪**——肉眼看着答案是对的，但因为多余的反
   斜杠/括号错位，`probe_answer_normalized` 字段跟真实答案对不上。

（以上子情况是根据探针机制补充的判断细则，不是 plan.md 原文枚举，供参考而非
硬性穷举——遇到不属于以上任何一类但确实"形式不对"的情况，仍然可以判
`format_artifact`，必要时在 notes 里简单说明是哪种。）

## 标注流程（plan.md §4.5）

- **Round 1**：独立标注前 100 个案例。
- **Round 2**：计算 Cohen's kappa / raw agreement，对争议案例讨论并按需修改本指南。
- **Round 3**：扩展至 300–500 个案例。

本项目当前只有一名真实人工标注者（用户本人），因此 Round 2 的 kappa 计算暂缺，
`analyze_audit.py` 不会编造第二标注者的数据；如果未来有第二人独立标注，再补上。
