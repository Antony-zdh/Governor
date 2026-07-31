#!/usr/bin/env python3
"""Deterministic Chinese Markdown report generator for the related-work baselines.

Driven only by validated aggregate/manifests data. Does NOT fabricate values --
if data is missing or incomplete, the report states so explicitly.

Usage:
    python -m benchmark.FalseConsensus.related_work.report_gen \
        --aggregate <aggregate.json> --output <report.md>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Any, Mapping, Optional, Sequence

from . import common, model_map, metrics

REPO = common.REPO_ROOT
SPLIT_MANIFEST = REPO / "benchmark/FalseConsensus/governor_v2/generated/split_manifest.json"

METHOD_LABELS = {
    "certaindex_mid_frozen": "CertaIndex mid",
    "tje_frozen": "TJE",
    "deer_frozen": "DEER",
}

GOVERNOR_REFERENCE_FILE = (
    Path(__file__).resolve().parent / "configs/governor_exploratory_reference.json"
)


def _fmt(v: Any, places: int = 2) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:.{places}f}"
    return str(v)


def _ci(lo: Any, hi: Any, places: int = 2) -> str:
    if lo is None or hi is None:
        return "N/A"
    return f"[{_fmt(lo, places)}, {_fmt(hi, places)}]"


def _pct(v: Any, places: int = 2) -> str:
    if v is None:
        return "N/A"
    return f"{100.0 * float(v):.{places}f}%"


def _pct_ci(lo: Any, hi: Any, places: int = 2) -> str:
    """Format a confidence interval stored as fractions in percentage points."""
    if lo is None or hi is None:
        return "N/A"
    return f"[{100.0 * float(lo):.{places}f}, {100.0 * float(hi):.{places}f}]"


def _method_label(value: Any) -> str:
    return METHOD_LABELS.get(str(value), str(value))


def _dev_table(views: dict) -> str:
    """Evaluation-split pooled model × benchmark table.

    ``dev_pooled`` is retained as the aggregate schema key for backward
    compatibility.  For a test-only aggregate it contains test rows.
    """
    dev_pooled = views.get("dev_pooled", [])
    if not dev_pooled:
        return "| 模型 | 基准 | 方法 | 数据待补 |\n|---|---|---|---|\n"
    lines = [
        "| 模型 | 基准 | 方法 | 准确率 | 全量准确率 | 准确率差(pp) | 95%CI(准确率差) "
        "| 全量token节省 | 95%CI(token节省) | 主token节省 | 停止率 | 探针开销(token) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in dev_pooled:
        ci = row.get("ci") or {}
        lines.append(
            f"| {row.get('model','N/A')} | {row.get('dataset','N/A')} | {_method_label(row.get('method','N/A'))} "
            f"| {_pct(row.get('accuracy'))} | {_pct(row.get('baseline_accuracy'))} "
            f"| {_fmt(row.get('accuracy_diff_pp'),2)} | {_pct_ci(ci.get('accuracy_diff_ci_lo'), ci.get('accuracy_diff_ci_hi'))} "
            f"| {_pct(row.get('all_generated_token_saving_fraction'))} "
            f"| {_pct_ci(ci.get('token_saving_ci_lo'), ci.get('token_saving_ci_hi'))} "
            f"| {_pct(row.get('main_only_token_saving_fraction'))} "
            f"| {_pct(row.get('stop_rate'))} | {_fmt(row.get('avg_probe_out_tokens'),1)} |"
        )
    return "\n".join(lines)


def _pareto_table(views: Mapping[str, Any]) -> str:
    """Full + related-work dev-macro Pareto table, separately by model."""
    rows = list(views.get("dev_macro", []))
    if not rows:
        return "数据待补。"
    by_model: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_model[str(row.get("model"))].append(dict(row))
    output = [
        "| 模型 | 方法 | 宏平均准确率 | 相对 Full | 公平 token 节省 | 非支配 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for model, model_rows in sorted(by_model.items()):
        baseline_values = [
            float(r.get(
                "baseline_accuracy",
                float(r.get("accuracy", 0.0))
                - float(r.get("accuracy_diff_pp", 0.0)) / 100.0,
            ))
            for r in model_rows
        ]
        baseline = sum(baseline_values) / len(baseline_values)
        points = [{
            "label": "Full generation",
            "accuracy": baseline,
            "accuracy_diff_pp": 0.0,
            "saving": 0.0,
        }]
        points.extend({
            "label": _method_label(r.get("method")),
            "accuracy": float(r["accuracy"]),
            "accuracy_diff_pp": float(r["accuracy_diff_pp"]),
            "saving": float(r["all_generated_token_saving_fraction"]),
        } for r in model_rows)
        for point in points:
            dominated = any(
                other["accuracy"] >= point["accuracy"]
                and other["saving"] >= point["saving"]
                and (
                    other["accuracy"] > point["accuracy"]
                    or other["saving"] > point["saving"]
                )
                for other in points if other is not point
            )
            output.append(
                f"| {model} | {point['label']} | {_pct(point['accuracy'])} "
                f"| {point['accuracy_diff_pp']:+.2f}pp | {_pct(point['saving'])} "
                f"| {'否' if dominated else '是'} |"
            )
    return "\n".join(output)


def _matched_interpretation(views: Mapping[str, Any]) -> str:
    rows = list(views.get("dev_macro", []))
    if not rows:
        return "数据待补。"
    by_model: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_model[str(row.get("model"))].append(dict(row))
    lines = []
    for model, model_rows in sorted(by_model.items()):
        lines.append(f"- **{model}**：")
        for loss_budget in (1.0, 3.0, 5.0):
            eligible = [
                r for r in model_rows
                if float(r.get("accuracy_diff_pp", -1e9)) >= -loss_budget
            ]
            if eligible:
                best = max(
                    eligible,
                    key=lambda r: float(r.get("all_generated_token_saving_fraction", -1e9)),
                )
                lines.append(
                    f"  - matched-accuracy（损失≤{loss_budget:.0f}pp）最省的是 "
                    f"{_method_label(best.get('method'))}："
                    f"{_pct(best.get('all_generated_token_saving_fraction'))}，"
                    f"Δacc={float(best.get('accuracy_diff_pp')):+.2f}pp。"
                )
            else:
                lines.append(
                    f"  - matched-accuracy（损失≤{loss_budget:.0f}pp）：没有相关工作基线满足。"
                )
        if len(model_rows) >= 2:
            pairs = [
                (abs(float(a["all_generated_token_saving_fraction"])
                     - float(b["all_generated_token_saving_fraction"])), a, b)
                for i, a in enumerate(model_rows)
                for b in model_rows[i + 1:]
            ]
            gap, a, b = min(pairs, key=lambda item: item[0])
            lines.append(
                f"  - 最近的 matched-token 对是 {_method_label(a.get('method'))} 与 "
                f"{_method_label(b.get('method'))}（节省差 {_pct(gap)}）；"
                f"准确率差为 {100.0 * (float(a['accuracy']) - float(b['accuracy'])):+.2f}pp。"
            )
    lines.append(
        "- 每个方法只有一个预注册主 operating point；因此不存在连续阈值曲线时，"
        "不能把“最近点”解释为严格的等 token 因果比较。"
    )
    return "\n".join(lines)


def _governor_reference_table() -> str:
    reference = json.loads(GOVERNOR_REFERENCE_FILE.read_text(encoding="utf-8"))
    source_path = REPO / reference["source_path"]
    source_hash = common.sha256_file(source_path)
    if source_hash != reference["source_sha256"]:
        raise ValueError(
            f"Governor exploratory reference source hash mismatch: {source_hash}"
        )
    points = reference["points"]
    lines = [
        "| 历史探索点 | 准确率 | 相对 Full | token 节省 |",
        "|---|---:|---:|---:|",
    ]
    baseline = float(points[0]["accuracy_percent"])
    for point in points:
        label = str(point["method"])
        accuracy = float(point["accuracy_percent"])
        saving = float(point["token_saving_percent"])
        lines.append(
            f"| {label} | {accuracy:.2f}% | {accuracy - baseline:+.2f}pp | {saving:.2f}% |"
        )
    lines.append(
        f"\n- 来源文件：`{reference['source_path']}`\n"
        f"- 来源 SHA-256：`{reference['source_sha256']}`\n\n"
        "该表是历史三-seed MATH500 探索结果，模型/seed/任务构成与本报告的 "
        "18 个 development 环境不完全匹配；只用于定性定位，不能和上表作严格"
        "横向显著性比较。"
    )
    return "\n".join(lines)


def _diagnostic_table(views: Mapping[str, Any]) -> str:
    rows = list(views.get("train_dev_diagnostic", []))
    if not rows:
        return "数据待补。"
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("method")), str(row.get("model")))].append(dict(row))
    lines = [
        "| 模型 | 方法 | 行数 | 辅助调用 | 无效辅助响应 | capped/right-censored | 恢复截断 | 过度思考避免 | 辅助 wall time(s) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for (method, model), group in sorted(grouped.items()):
        n = sum(int(r.get("n", 0)) for r in group)
        aux = sum(int(r.get("total_aux_calls", 0)) for r in group)
        invalid = sum(int(r.get("invalid_aux_responses", 0)) for r in group)
        wall = sum(float(r.get("auxiliary_wall_seconds", 0.0)) for r in group)
        weighted = lambda field: (
            sum(float(r.get(field, 0.0)) * int(r.get("n", 0)) for r in group) / n
            if n else 0.0
        )
        lines.append(
            f"| {model} | {_method_label(method)} | {n} | {aux} "
            f"| {invalid} ({(100.0 * invalid / aux if aux else 0.0):.3f}%) "
            f"| {_pct(weighted('capped_rate'), 3)} "
            f"| {_pct(weighted('recovery_truncated_rate'), 3)} "
            f"| {_pct(weighted('overthinking_avoided_rate'), 3)} | {wall:.1f} |"
        )
    return "\n".join(lines)


def _executive_conclusion(views: Mapping[str, Any], data_ready: bool) -> str:
    rows = list(views.get("dev_macro", []))
    if not data_ready or not rows:
        return "数据尚不完整，暂不作效果结论。"
    best_accuracy = max(rows, key=lambda r: float(r.get("accuracy_diff_pp", -1e9)))
    best_saving = max(
        rows, key=lambda r: float(r.get("all_generated_token_saving_fraction", -1e9))
    )
    safe = [r for r in rows if float(r.get("accuracy_diff_pp", -1e9)) >= -3.0]
    safe_sentence = (
        "存在≤3pp 准确率损失的相关工作点。"
        if safe else
        "没有任何相关工作主点达到“准确率损失≤3pp”的 matched-accuracy 条件。"
    )
    return (
        f"完整主结果显示：准确率保留最好的是 {_method_label(best_accuracy.get('method'))}"
        f" / {best_accuracy.get('model')}（宏平均 Δacc="
        f"{float(best_accuracy.get('accuracy_diff_pp')):+.2f}pp）；"
        f"公平 token 节省最高的是 {_method_label(best_saving.get('method'))}"
        f" / {best_saving.get('model')}（"
        f"{_pct(best_saving.get('all_generated_token_saving_fraction'))}）。"
        f"{safe_sentence} 这些结论只针对冻结轨迹复现，不反推原论文端到端结果。"
    )


def _protocol_table() -> str:
    return """| 方法 | 模块 | 来源(pin) | 复现类别 |
|---|---|---|---|
| CertaIndex faithful mid | `certaindex_mid.py` | `dynasor/core/cot.py` @ `dbe76ad` | 忠实prompt+停止规则; 冻结轨迹时间 |
| TJE | `tje.py` | https://aclanthology.org/2026.findings-eacl.263/ (Fig.2+§2.2) | 冻结轨迹TJE复现 |
| DEER | `deer.py` | https://github.com/iie-ycx/DEER @ `c9dd19f` | 冻结轨迹DEER复现 |"""


def generate_report(aggregate_path: Path, output_path: Path) -> str:
    """Generate the Chinese Markdown report from validated aggregate data."""
    if not aggregate_path.exists():
        # No data yet -- produce a skeleton with "数据待补" placeholders
        views = {}
    else:
        views = json.loads(aggregate_path.read_text(encoding="utf-8"))

    coverage = views.get("coverage", {})
    row_count = views.get("row_count", 0)
    test_rows = int(coverage.get("test_rows", 0) or 0)
    is_test = bool(row_count and test_rows == row_count)
    trajectories_per_method = 684 if is_test else common.EXPECTED_TOTAL_TRAJECTORIES
    expected = trajectories_per_method * 3
    data_ready = row_count == expected
    phase_label = "Test" if is_test else "Development"

    report = []
    report.append(f"# Governor v2 相关工作基线实验报告（{phase_label}）\n")
    report.append("## 1. 执行结论\n")
    if data_ready:
        report.append(
            f"全量数据已就绪（{row_count} 行，3 方法 × "
            f"{trajectories_per_method} 轨迹/方法）。\n"
        )
    else:
        report.append(f"数据尚不完整（{row_count}/{expected} 行）。以下表格中 N/A 表示数据待补。\n")
    report.append(_executive_conclusion(views, data_ready))

    report.append("\n## 2. 实验范围与复现标签\n")
    report.append(f"- **模型**: DeepSeek-R1-Distill-Qwen-7B (rev `916b56a`), Qwen3-8B (rev `b968826`)\n")
    report.append(f"- **基准**: MATH500 (400/env), AMC23 (32/env), AIME24 (24/env)\n")
    report.append(f"- **种子**: {'45, 46, 47' if is_test else '42, 43, 44'}\n")
    report.append(
        f"- **环境数**: 18 (2 模型 × 3 基准 × 3 种子), "
        f"**轨迹总数**: {trajectories_per_method}\n"
    )
    report.append(
        f"- **阶段**: "
        f"{'confirmation (test only)' if is_test else 'development (train+dev), 无测试数据'}\n"
    )
    report.append(f"- **协议版本**: `{common.EXPECTED_PROTOCOL_VERSION}`\n")
    report.append(f"- **拆分种子**: `{common.EXPECTED_SPLIT_SEED}`\n")

    report.append("\n## 3. 方法/协议表\n")
    report.append(_protocol_table())
    report.append("")

    report.append("\n## 4. 覆盖率\n")
    if coverage:
        report.append(f"- 方法数: {coverage.get('method_count', 'N/A')}\n")
        report.append(f"- 环境数: {coverage.get('environment_count', 'N/A')}\n")
        per_method = coverage.get("rows_per_method", {})
        report.append(f"- 每方法行数: {per_method}\n")
        report.append(f"- 测试行数: {coverage.get('test_rows', 'N/A')}\n")
    else:
        report.append("数据待补。\n")

    report.append(f"\n## 5. {phase_label} 模型×基准表\n")
    report.append(_dev_table(views))
    report.append("")

    report.append(
        f"\n## 6. {phase_label} 宏观视图（不使MATH500按样本数主导）\n"
    )
    macro = views.get("dev_macro", [])
    if macro:
        lines = [
            "| 方法 | 模型 | 基准数 | 准确率 | 准确率差(pp) | 全量token节省 | 主token节省 | 停止率 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for m in macro:
            lines.append(
                f"| {_method_label(m.get('method','N/A'))} | {m.get('model','N/A')} | {m.get('benchmark_count','N/A')} "
                f"| {_pct(m.get('accuracy'))} | {_fmt(m.get('accuracy_diff_pp'),2)} "
                f"| {_pct(m.get('all_generated_token_saving_fraction'))} "
                f"| {_pct(m.get('main_only_token_saving_fraction'))} "
                f"| {_pct(m.get('stop_rate'))} |"
            )
        report.append("\n".join(lines))
    else:
        report.append("数据待补。\n")
    report.append("")

    per_seed = views.get("per_seed", [])
    if per_seed:
        report.append(f"\n### 6.1 {phase_label} pooled per-seed sensitivity\n")
        lines = [
            "| Seed | Method | n | Accuracy | Accuracy diff | All-generated saving | Stop rate |",
            "|---:|---|---:|---:|---:|---:|---:|",
        ]
        for row in per_seed:
            lines.append(
                f"| {row.get('base_seed','N/A')} | {_method_label(row.get('method','N/A'))} "
                f"| {row.get('n','N/A')} | {_pct(row.get('accuracy'))} "
                f"| {_fmt(row.get('accuracy_diff_pp'),2)} pp "
                f"| {_pct(row.get('all_generated_token_saving_fraction'))} "
                f"| {_pct(row.get('stop_rate'))} |"
            )
        report.append("\n".join(lines))
        report.append("")

    report.append("\n## 7. Accuracy-compute Pareto\n")
    report.append(_pareto_table(views))
    report.append(
        "\n“非支配”仅在同一模型的 Full + 三个相关工作主点内部计算；"
        "准确率越高、token 节省越高越好。\n"
    )

    report.append("\n### 可用 Governor 探索点（非严格 matched 参考）\n")
    report.append(_governor_reference_table())
    report.append("")

    report.append("\n## 8. Matched-accuracy / matched-token 解读\n")
    report.append(_matched_interpretation(views))
    report.append("")

    report.append("\n## 9. 公平计费说明\n")
    report.append("**两种成本视图**:\n")
    report.append("1. **论文式** `main_tokens_through_stop` - 冻结推理长度到停止（或全长如无停止）\n")
    report.append("2. **公平全量** `all_generated_tokens` = 主停止长度 + 所有探针/试错/读出输出token\n")
    report.append("探针/试错/读出 **prompt token**（重发前缀）单独报告，不计入全量生成token。\n")
    report.append(
        f"\n**配对分层 bootstrap**: {metrics.BOOTSTRAP_SAMPLES} 样本, "
        f"种子 `{metrics.BOOTSTRAP_SEED}` - 先重采样种子，再在种子内"
        f"重采样配对问题行。仅在 {phase_label.lower()}-pooled 与方法汇总视图"
        "运行（非逐环境）。\n"
    )

    report.append("\n## 10. 失败、截断与解析诊断\n")
    report.append(_diagnostic_table(views))
    report.append(
        "\n`invalid_aux_responses` 是已完整记录的方法级失败（交付空答案并计错），"
        "不是丢行；8192-token TJE 与 4096-token DEER readout 触顶作为"
        " capped/right-censored 诊断保留。请求错误、context overflow、缺行仍是硬失败。\n"
    )

    report.append("\n## 11. 局限性\n")
    report.append("- TJE/DEER 为冻结轨迹复现，非端到端忠实运行（冻结轨迹 TJE/DEER 复现标签）\n")
    report.append("- TJE 的 `structured_outputs.choice` 约束改变了标签分布（vs 无约束），影响触发率\n")
    report.append("- AMC/AIME 样本量小（32/24），置信区间较宽\n")
    report.append("- 模型可能声称高置信但在固定读出 cap 内无法完成 boxed 答案；该结果按方法失败计错，不补用未来完整答案\n")
    report.append("- 历史 Governor 探索点与当前 18 环境网格不完全匹配，只可定性参照\n")

    report.append("\n## 12. 精确修订/哈希\n")
    for key in ("deepseek", "qwen3"):
        info = model_map.model_info(key)
        report.append(f"- {key}: model=`{info['model_id']}` rev=`{info['revision']}` endpoint=`{info['endpoint']}`\n")
    report.append(f"- split manifest: `{SPLIT_MANIFEST.relative_to(REPO)}`\n")
    report.append("- 每个 collector manifest 记录 source commit、prompt/config hash、输入 trajectory bank hash 与 split hash\n")

    report.append("\n## 13. 复现命令\n")
    report.append("```bash\n")
    report.append("# 验证冻结银行\n")
    report.append("python -m benchmark.FalseConsensus.related_work.preflight\n")
    report.append("\n# 全量收集（每模型）\n")
    report.append("bash benchmark/FalseConsensus/results/related_work/_runtime/run_full_model_pipeline.sh deepseek\n")
    report.append("bash benchmark/FalseConsensus/results/related_work/_runtime/run_full_model_pipeline.sh qwen3\n")
    report.append("\n# 后处理（replay + aggregate + report）\n")
    if is_test:
        report.append(
            "python -m benchmark.FalseConsensus.related_work.aggregate_all "
            "--inputs benchmark/FalseConsensus/results/related_work/test/_replay/*/replay_rows.jsonl "
            "--output-dir benchmark/FalseConsensus/results/related_work/test/aggregate --allow-test\n"
        )
    else:
        report.append("python -m benchmark.FalseConsensus.related_work.postprocess\n")
    report.append("\n# PDF渲染\n")
    report.append("bash benchmark/FalseConsensus/results/related_work/_runtime/render_pdf.sh\n")
    report.append("```\n")

    report.append("\n## 14. Artifact inventory\n")
    artifact_root = "test" if is_test else "full"
    aggregate_root = (
        "benchmark/FalseConsensus/results/related_work/test/aggregate"
        if is_test
        else "benchmark/FalseConsensus/results/related_work/aggregate"
    )
    report.append(f"- 原始逐题结果：`benchmark/FalseConsensus/results/related_work/{artifact_root}/<model>__<benchmark>__seed_<seed>/<method>/`\n")
    report.append(f"- 54 个 replay：`benchmark/FalseConsensus/results/related_work/{artifact_root}/_replay/`\n")
    report.append(f"- 聚合 JSON：`{aggregate_root}/aggregate.json`\n")
    report.append(f"- 环境/pooled/宏视图 CSV：`{aggregate_root}/*.csv`\n")
    report.append(f"- Markdown 报告：`{aggregate_root}/report.md`\n")
    report.append(f"- PDF 报告：`{aggregate_root}/report.pdf`\n")
    report.append(f"- 运行/验证日志：`benchmark/FalseConsensus/results/related_work/{artifact_root}/_runtime/`\n")

    text = "\n".join(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Chinese Markdown report generator")
    ap.add_argument("--aggregate", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args(argv)
    text = generate_report(args.aggregate, args.output)
    print(f"report written to {args.output} ({len(text)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
