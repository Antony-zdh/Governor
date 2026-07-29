#!/usr/bin/env python3
"""Build the ONE-FILE interactive error-taxonomy review page (paper Sec 3).

Inputs (committed):
  results/stage1_logging/analysis/false_consensus_cases.json   (134 stopped-but-wrong cases)
  results/stage1_logging/analysis/classification.json          (AI initial labels for 28)
Output (this dir):
  taskA_taxonomy.html   self-contained: instructions + all 134 cases + in-page
                        labeling + one-click CSV export. This is the only file to send.
"""
import json, sys
from pathlib import Path
from itertools import groupby

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_interactive import render_page

FC = HERE.parent
cases = json.load(open(FC/"results/stage1_logging/analysis/false_consensus_cases.json"))
cls = json.load(open(FC/"results/stage1_logging/analysis/classification.json"))
ai = {c["problem_id"]: c for c in cls["cases"]}
cases.sort(key=lambda c: c["problem_id"])

def rle(seq):
    out = []
    for k, g in groupby(seq):
        n = len(list(g))
        out.append(f"{k}×{n}" if n > 1 else f"{k}")
    return ", ".join(out)

COLUMNS = ["problem_id", "target_gold", "stop_answer_wrong", "final_answer",
           "final_correct", "n_probes", "probe_stream_rle", "ai_type", "ai_reason",
           "HUMAN_type[A-E]", "HUMAN_confident[y/n]", "HUMAN_notes"]

FIELDS = [
    {"key": "HUMAN_type", "label": "类型 (必填)", "type": "select", "options": [
        {"value": "", "label": "— 选择 —"},
        {"value": "A", "label": "A 数值坍缩"}, {"value": "B", "label": "B 表达式坍缩"},
        {"value": "C", "label": "C 符号错误"}, {"value": "D", "label": "D 推导缺口"},
        {"value": "E", "label": "E 格式/选项幻觉"}]},
    {"key": "HUMAN_confident", "label": "有把握", "type": "select", "options": [
        {"value": "", "label": "—"}, {"value": "y", "label": "y"}, {"value": "n", "label": "n"}]},
    {"key": "HUMAN_notes", "label": "备注（可选；两可情形请说明）", "type": "text"},
]

records = []
for c in cases:
    a = ai.get(c["problem_id"], {})
    rle_str = rle(c.get("probe_answers", []))
    records.append({
        "pid": c["problem_id"], "target": str(c["target"]),
        "stop": str(c.get("stop_answer")), "final": str(c.get("final_answer")),
        "fc": bool(c.get("final_correct")), "nprobes": len(c.get("probe_answers", [])),
        "rle": rle_str, "ai_type": a.get("type", ""), "ai_reason": a.get("reason", ""),
        "problem": c["problem"], "full_text": c.get("full_text", ""),
        # fixed CSV cells, in COLUMNS order up to the human fields:
        "csv": [c["problem_id"], str(c["target"]), str(c.get("stop_answer")),
                str(c.get("final_answer")), bool(c.get("final_correct")),
                len(c.get("probe_answers", [])), rle_str, a.get("type", ""), a.get("reason", "")],
    })

INTRO = f"""
<p><b>目标：</b>给每个 <i>提前停但停错了</i> 的案例（共 {len(cases)} 个）选一个错误类型。这些案例是：某个提前停规则在 probe 窗口一致同意时提交了答案，但那个答案是错的（或完整推理后来改对了）。</p>
<p><b>怎么做：</b>逐条看下面的信息（题目、正解、错误停在的答案、probe 流；需要时展开完整推理），在卡片底部选 <code>类型 A–E</code> + <code>有把握 y/n</code>，可写备注。进度自动存在浏览器里，刷新不丢。全部标完点顶栏 <b>下载 CSV</b> 交回即可。</p>
<p><b>五个类型（选最贴切的一个）：</b></p>
<ul>
<li><b>A 数值坍缩</b> — 轨迹稳定收敛到一个<b>错误的数字</b>。</li>
<li><b>B 表达式坍缩</b> — 收敛到一个错误的<b>非数字表达式</b>（公式/集合等）。</li>
<li><b>C 符号错误</b> — 数值大小对、<b>符号</b>错。</li>
<li><b>D 推导缺口</b> — 漏根/漏情况、跳步未验证、读错题。</li>
<li><b>E 格式/选项幻觉</b> — <b>非选择题</b>却稳定吐一个字母（如 “B”“D”）。这是 probe 机制的假象，不是模型的真实判断。</li>
</ul>
<p><b>提示：</b>橙色是 AI 对其中 28 例的初判，可以推翻。非选择题却答字母 → 基本就是 <b>E</b>。D 与 A/B 难分时问自己：是<i>值</i>算错（A/B），还是<i>漏了必要的情况/步骤</i>（D）？两可写在备注。清楚的很快，只在模棱两可的多花时间。</p>
"""

html = render_page(title="错误类型人工标注 (Task A)", intro_html=INTRO,
                    columns=COLUMNS, fields=FIELDS, data=records,
                    task_id="taxonomy", file_prefix="taxonomy_review")
out = HERE/"taskA_taxonomy.html"
out.write_text(html, encoding="utf-8")
print(f"wrote {out.name}  ({len(cases)} cases, {len(ai)} AI-prelabeled, {out.stat().st_size} bytes)")
