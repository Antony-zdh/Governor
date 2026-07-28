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
from typing import Any, Mapping, Optional, Sequence

from . import common, model_map, metrics

REPO = Path("/localdata/dzhaoah/Governor")
SPLIT_MANIFEST = REPO / "benchmark/FalseConsensus/governor_v2/generated/split_manifest.json"


def _fmt(v: Any, places: int = 2) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{places}f}"
    return str(v)


def _ci(lo: Any, hi: Any, places: int = 2) -> str:
    if lo is None or hi is None:
        return "—"
    return f"[{_fmt(lo, places)}, {_fmt(hi, places)}]"


def _dev_table(views: dict) -> str:
    """Dev-pooled model × benchmark table."""
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
            f"| {row.get('model','—')} | {row.get('dataset','—')} | {row.get('method','—')} "
            f"| {_fmt(row.get('accuracy'),4)} | {_fmt(row.get('baseline_accuracy'),4)} "
            f"| {_fmt(row.get('accuracy_diff_pp'),2)} | {_fmt(ci.get('accuracy_diff'),4)}→{_fmt(ci.get('accuracy_diff_ci_lo'),4)},{_fmt(ci.get('accuracy_diff_ci_hi'),4)} "
            f"| {_fmt(row.get('all_generated_token_saving_fraction'),4)} "
            f"| {_fmt(ci.get('all_generated_token_saving'),4)}→{_fmt(ci.get('token_saving_ci_lo'),4)},{_fmt(ci.get('token_saving_ci_hi'),4)} "
            f"| {_fmt(row.get('main_only_token_saving_fraction'),4)} "
            f"| {_fmt(row.get('stop_rate'),4)} | {_fmt(row.get('avg_probe_out_tokens'),1)} |"
        )
    return "\n".join(lines)


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
    expected = common.EXPECTED_TOTAL_TRAJECTORIES * 3  # 8208
    data_ready = row_count == expected

    report = []
    report.append("# Governor v2 相关工作基线实验报告\n")
    report.append("## 1. 执行结论\n")
    if data_ready:
        report.append(f"全量数据已就绪（{row_count} 行，3 方法 × {common.EXPECTED_TOTAL_TRAJECTORIES} 轨迹/方法）。\n")
    else:
        report.append(f"数据尚不完整（{row_count}/{expected} 行）。以下表格中—表示数据待补。\n")

    report.append("\n## 2. 实验范围与复现标签\n")
    report.append(f"- **模型**: DeepSeek-R1-Distill-Qwen-7B (rev `916b56a`), Qwen3-8B (rev `b968826`)\n")
    report.append(f"- **基准**: MATH500 (400/env), AMC23 (32/env), AIME24 (24/env)\n")
    report.append(f"- **种子**: 42, 43, 44\n")
    report.append(f"- **环境数**: 18 (2 模型 × 3 基准 × 3 种子), **轨迹总数**: {common.EXPECTED_TOTAL_TRAJECTORIES}\n")
    report.append(f"- **阶段**: development (train+dev), 无测试数据\n")
    report.append(f"- **协议版本**: `{common.EXPECTED_PROTOCOL_VERSION}`\n")
    report.append(f"- **拆分种子**: `{common.EXPECTED_SPLIT_SEED}`\n")

    report.append("\n## 3. 方法/协议表\n")
    report.append(_protocol_table())
    report.append("")

    report.append("\n## 4. 覆盖率\n")
    if coverage:
        report.append(f"- 方法数: {coverage.get('method_count', '—')}\n")
        report.append(f"- 环境数: {coverage.get('environment_count', '—')}\n")
        per_method = coverage.get("rows_per_method", {})
        report.append(f"- 每方法行数: {per_method}\n")
        report.append(f"- 测试行数: {coverage.get('test_rows', '—')}\n")
    else:
        report.append("数据待补。\n")

    report.append("\n## 5. Dev 模型×基准表\n")
    report.append(_dev_table(views))
    report.append("")

    report.append("\n## 6. Dev 宏观视图（不使MATH500按样本数主导）\n")
    macro = views.get("dev_macro", [])
    if macro:
        lines = [
            "| 方法 | 模型 | 基准数 | 准确率 | 准确率差(pp) | 全量token节省 | 主token节省 | 停止率 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for m in macro:
            lines.append(
                f"| {m.get('method','—')} | {m.get('model','—')} | {m.get('benchmark_count','—')} "
                f"| {_fmt(m.get('accuracy'),4)} | {_fmt(m.get('accuracy_diff_pp'),2)} "
                f"| {_fmt(m.get('all_generated_token_saving_fraction'),4)} "
                f"| {_fmt(m.get('main_only_token_saving_fraction'),4)} "
                f"| {_fmt(m.get('stop_rate'),4)} |"
            )
        report.append("\n".join(lines))
    else:
        report.append("数据待补。\n")
    report.append("")

    report.append("\n## 7. 公平计费说明\n")
    report.append("**两种成本视图**:\n")
    report.append("1. **论文式** `main_tokens_through_stop` — 冻结推理长度到停止（或全长如无停止）\n")
    report.append("2. **公平全量** `all_generated_tokens` = 主停止长度 + 所有探针/试错/读出输出token\n")
    report.append("探针/试错/读出 **prompt token**（重发前缀）单独报告，不计入全量生成token。\n")
    report.append(f"\n**配对分层 bootstrap**: {metrics.BOOTSTRAP_SAMPLES} 样本, 种子 `{metrics.BOOTSTRAP_SEED}` — "
                 "重采样种子→种子内配对问题行。仅在 dev-pooled + train+dev 视图运行（非逐环境）。\n")

    report.append("\n## 8. 失败/截断/解析诊断\n")
    if views.get("environment_split"):
        env = views["environment_split"]
        invalid_rates = [r.get("invalid_aux_response_rate") for r in env if r.get("invalid_aux_response_rate") is not None]
        capped_rates = [r.get("capped_rate") for r in env if r.get("capped_rate") is not None]
        stop_rates = [r.get("stop_rate") for r in env if r.get("stop_rate") is not None]
        if invalid_rates:
            report.append(f"- 无效辅助响应率: 均值 {_fmt(sum(invalid_rates)/len(invalid_rates),4)}\n")
        if capped_rates:
            report.append(f"- 截断率: 均值 {_fmt(sum(capped_rates)/len(capped_rates),4)}\n")
        if stop_rates:
            report.append(f"- 停止率: 均值 {_fmt(sum(stop_rates)/len(stop_rates),4)}\n")
    else:
        report.append("数据待补。\n")

    report.append("\n## 9. 局限性\n")
    report.append("- TJE/DEER 为冻结轨迹复现，非端到端忠实运行（冻结轨迹 TJE/DEER 复现标签）\n")
    report.append("- TJE 的 `structured_outputs.choice` 约束改变了标签分布（vs 无约束），影响触发率\n")
    report.append("- AMC/AIME 样本量小（32/24），置信区间较宽\n")
    report.append("- 模型在截断轨迹上可能声称高置信但无法完成读出（合法无早期停止）\n")

    report.append("\n## 10. 精确修订/哈希\n")
    for key in ("deepseek", "qwen3"):
        info = model_map.model_info(key)
        report.append(f"- {key}: model=`{info['model_id']}` rev=`{info['revision']}` endpoint=`{info['endpoint']}`\n")

    report.append("\n## 11. 复现命令\n")
    report.append("```bash\n")
    report.append("# 验证冻结银行\n")
    report.append("python -m benchmark.FalseConsensus.related_work.preflight\n")
    report.append("\n# 全量收集（每模型）\n")
    report.append("bash benchmark/FalseConsensus/results/related_work/_runtime/run_full_model_pipeline.sh deepseek\n")
    report.append("bash benchmark/FalseConsensus/results/related_work/_runtime/run_full_model_pipeline.sh qwen3\n")
    report.append("\n# 后处理（replay + aggregate + report）\n")
    report.append("python -m benchmark.FalseConsensus.related_work.postprocess\n")
    report.append("\n# PDF渲染\n")
    report.append("bash benchmark/FalseConsensus/results/related_work/_runtime/render_pdf.sh\n")
    report.append("```\n")

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
