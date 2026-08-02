#!/usr/bin/env python3
"""Three main-body generalization figures: DEER vs consensus (+ oracle), showing
the selection->generalization pipeline. Consensus train-gate candidates (orange)
and the three DEER operating points selected on dev (labelled stars) are tracked
onto each panel's data; generalization panels (models, benchmarks) use the TEST
split so we see how selected strategies transfer out of sample.
Oracle points are cached (probe-bank scan is slow)."""
from __future__ import annotations
import glob, gzip, json, statistics, sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
GOV = HERE.parent / "governor_v2"
RES = HERE.parent / "results"
BANK = RES / "governor_v2_ws_sweep"
CACHE = HERE / "figures/gen/oracle_cache.json"
sys.path.insert(0, str(GOV)); sys.path.insert(0, str(HERE.parent / "related_work"))
from replay_rules import answers_equal, valid_answer, normalize_answer, load_split_map  # noqa
from deer_threshold_sweep import THRESHOLDS, eq, replay_problem, iter_bank  # noqa

SEL = {"math500": 16384, "amc23": 16384, "aime24": 32768}
GATES = [("conservative", 1.0, 0.10, "#16a34a"), ("balanced", 2.0, 0.20, "#2563eb"),
         ("token_efficient", 3.5, 0.30, "#9333ea")]
GDICT = {g[0]: g for g in GATES}
DEVID = {"deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "Qwen/Qwen3-8B"}
SLUG = {"deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": "deepseek-ai-deepseek-r1-distill-qwen-7b",
        "Qwen/Qwen3-8B": "qwen-qwen3-8b",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B": "deepseek-ai-deepseek-r1-distill-qwen-32b",
        "deepseek-ai/DeepSeek-R1-Distill-Llama-8B": "deepseek-ai-deepseek-r1-distill-llama-8b"}
# DEER operating points selected on dev (max-saving tau passing each gate).
SELECTED = {"C": 0.995, "B": 0.99, "T": 0.97}
split_map = load_split_map(GOV / "generated/split_manifest.json")
_ORACLE = json.loads(CACHE.read_text()) if CACHE.exists() else {}


def load_gz(p):
    with gzip.open(p, "rt") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def cons_rows():
    rows = list(load_gz(BANK / "dev/consensus_dev_train.jsonl.gz"))
    for r in load_gz(BANK / "test/consensus_test.jsonl.gz"):
        if r["model"] in DEVID and int(r["budget"]) == SEL[r["benchmark"]]:
            rows.append(r)
    for r in load_gz(BANK / "heldout_test/consensus_heldout_32b_llama_3seed.jsonl.gz"):
        if int(r["budget"]) == SEL[r["benchmark"]]:
            rows.append(r)
    return rows


def macro(rows, keep):
    by = defaultdict(list)
    for r in rows:
        if keep(r):
            by[str(r["rule_id"])].append(r)
    return {rid: (statistics.fmean(float(x["accuracy_drop_pp"]) for x in e),
                  statistics.fmean(float(x["saving_fraction"]) for x in e) * 100.0)
            for rid, e in by.items()}


def frontier(pts):
    pts = sorted(pts, key=lambda t: (t[0], -t[1]))
    fr, best = [], float("-inf")
    for d, s in pts:
        if s > best:
            fr.append((d, s)); best = s
    return fr


# DEER: {tau: (drop, saving)} on a subset
def deer_by_tau_bank(keep):
    by = defaultdict(list)
    for r in load_gz(BANK / "deer/deer_threshold_sweep.jsonl.gz"):
        if keep(r):
            by[float(r["threshold"])].append(r)
    return {t: (statistics.fmean(float(x["accuracy_drop_pp"]) for x in e),
                statistics.fmean(float(x["saving_fraction"]) for x in e) * 100.0) for t, e in by.items()}


def deer_by_tau_heldout(model_id):
    slug = SLUG[model_id]; want = "qwen32b" if "32B" in model_id else "llama8b"
    hb = RES / "related_work/deer_confidence_bank_cap30_heldout/test"
    per = defaultdict(list)
    for env in sorted(hb.glob("*__*__seed_*")):
        key, bench, stag = env.name.split("__")
        if key != want:
            continue
        seed = int(stag.replace("seed_", "")); budget = SEL[bench]
        mrun = RES / f"governor_v2/confirmation__{slug}__{bench}__seed_{seed}/main"
        midx = {}
        for p in (mrun / "traj").glob("problem_*.json"):
            t = json.loads(p.read_text()); midx[int(t["problem_id"])] = {
                "target": t["target"], "final_answer": t.get("final_answer"),
                "tokens_used": int(t["tokens_used"]), "finished_naturally": bool(t["finished_naturally"])}
        recs = {int(r["problem_id"]): r for r in iter_bank(env)}
        base = {pid: {"baseline_complete": (m["finished_naturally"] and m["tokens_used"] <= budget),
                      "baseline_correct": (eq(m["final_answer"], m["target"]) if (m["finished_naturally"] and m["tokens_used"] <= budget and m["final_answer"] is not None) else False),
                      "baseline_tokens": min(m["tokens_used"], budget)} for pid, m in midx.items()}
        for thr in THRESHOLDS:
            vals = [replay_problem(recs[pid], midx[pid], base[pid], thr, budget) for pid in recs]
            bl = statistics.fmean(v["baseline_decode_tokens"] for v in vals)
            tot = statistics.fmean(v["total_decode_tokens"] for v in vals)
            drop = 100 * (statistics.fmean(v["baseline_correct"] for v in vals) - statistics.fmean(v["correct"] for v in vals))
            per[thr].append((drop, (bl - tot) / bl if bl else 0.0))
    return {t: (statistics.fmean(x[0] for x in e), statistics.fmean(x[1] for x in e) * 100.0) for t, e in per.items()}


def oracle_point(model_id, benchmarks, seeds, prefix, splits):
    ck = f"{model_id}|{','.join(benchmarks)}|{','.join(map(str,seeds))}|{prefix}|{','.join(sorted(splits))}"
    if ck in _ORACLE:
        return tuple(_ORACLE[ck]) if _ORACLE[ck] else None
    slug = SLUG[model_id]; per_env = []
    for bench in benchmarks:
        budget = SEL[bench]
        for seed in seeds:
            d = RES / f"governor_v2/{prefix}__{slug}__{bench}__seed_{seed}"
            traj = d / "main/traj"; probes = d / "dense_simple32/probes"
            if not traj.exists() or not probes.exists():
                continue
            savs = []; bc_l = []; oc_l = []
            for tp in traj.glob("problem_*.json"):
                t = json.loads(tp.read_text()); pid = int(t["problem_id"])
                if split_map.get((bench, pid)) not in splits:
                    continue
                target = t["target"]; toks = int(t["tokens_used"]); comp = bool(t["finished_naturally"]) and toks <= budget
                bc = (answers_equal(t.get("final_answer"), target) if comp and t.get("final_answer") is not None else False)
                bl = min(toks, budget); pf = probes / f"problem_{pid}.json"; chosen = None; cum = 0
                if pf.exists():
                    for pr in sorted(json.loads(pf.read_text()).get("probes", []), key=lambda z: int(z["token_position"])):
                        if int(pr["token_position"]) > budget:
                            break
                        cum += int(pr.get("probe_out_tokens", 0)); a = str(pr.get("probe_answer", ""))
                        if valid_answer(normalize_answer(a), bench, "schema") and answers_equal(a, target):
                            chosen = (int(pr["token_position"]), cum); break
                tot, oc = (chosen[0] + chosen[1], True) if chosen else (bl, bool(bc))
                bc_l.append(bc); oc_l.append(oc); savs.append((bl - tot) / bl if bl else 0.0)
            if bc_l:
                per_env.append((100 * (statistics.fmean(bc_l) - statistics.fmean(oc_l)), statistics.fmean(savs) * 100.0))
    res = (statistics.fmean(p[0] for p in per_env), statistics.fmean(p[1] for p in per_env)) if per_env else None
    _ORACLE[ck] = list(res) if res else None
    CACHE.parent.mkdir(parents=True, exist_ok=True); CACHE.write_text(json.dumps(_ORACLE))
    return res


def panel(ax, cons, deer, oracle, title, winners, show_labels=False):
    for name, cap, floor, c in GATES:
        ax.add_patch(Rectangle((0, floor * 100), cap, 100 - floor * 100, facecolor=c, alpha=0.05,
                     edgecolor=c, lw=0.7, ls="--", zorder=1))
    cp = list(cons.values())
    ax.scatter([d for d, s in cp], [s for d, s in cp], s=5, c="#c2c6ce", alpha=0.5, linewidths=0,
               zorder=2, label=f"consensus rules (n={len(cp)})")
    hp = [cons[i] for i in winners if i in cons]
    if hp:
        ax.scatter([d for d, s in hp], [s for d, s in hp], s=13, c="#f59e0b", alpha=0.85, linewidths=0,
                   zorder=3, label=f"consensus train candidates (n={len(hp)})")
    fr = frontier(list(deer.values()))
    ax.plot([d for d, s in fr], [s for d, s in fr], "-D", color="#059669", ms=3, lw=1.2, zorder=4,
            label="DEER frontier")
    for lab, tau in SELECTED.items():
        if tau in deer:
            d, s = deer[tau]
            ax.scatter([d], [s], marker="*", s=130, c="#065f46", edgecolor="white", linewidths=0.7,
                       zorder=6, label=("DEER selected (C/B/T)" if lab == "C" else None))
            ax.annotate(lab, (d, s), textcoords="offset points", xytext=(4, 4), fontsize=7, color="#065f46", zorder=7)
    if oracle:
        ax.scatter([oracle[0]], [oracle[1]], marker="*", s=150, c="#7c3aed", edgecolor="white",
                   linewidths=0.6, zorder=6, label="oracle upper bound")
    ax.set_xlim(-12, 30); ax.set_ylim(-5, 78)
    ax.axhline(0, color="#e5e7eb", lw=0.6, zorder=0); ax.axvline(0, color="#e5e7eb", lw=0.6, zorder=0)
    ax.set_xlabel("accuracy drop (pp)"); ax.set_title(title, fontsize=9); ax.grid(True, alpha=0.13)


def savefig(fig, name):
    out = HERE / "figures/gen"; out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{name}.pdf"); fig.savefig(out / f"{name}.png", dpi=140); plt.close(fig)
    print("wrote", name)


def main():
    rows = cons_rows()
    selb = lambda r: ("budget" not in r) or int(r["budget"]) == SEL[r["benchmark"]]
    D7, Q3 = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "Qwen/Qwen3-8B"
    B32, LL = "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B", "deepseek-ai/DeepSeek-R1-Distill-Llama-8B"
    train_cons = macro(rows, lambda r: r["split"] == "train" and selb(r) and r["model"] in DEVID)
    winners = {i for i, (d, s) in train_cons.items() if d <= 1.0 and s >= 10.0}

    def orc2(seeds, prefix, sp):
        a = oracle_point(D7, list(SEL), seeds, prefix, {sp}); b = oracle_point(Q3, list(SEL), seeds, prefix, {sp})
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) if a and b else (a or b)

    # ---- Fig SPLITS (train/dev/test, dev models) ----
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.7), sharey=True)
    for ax, sp in zip(axes, ["train", "dev", "test"]):
        c = macro(rows, lambda r, sp=sp: r["split"] == sp and selb(r) and r["model"] in DEVID)
        d = deer_by_tau_bank(lambda r, sp=sp: r["split"] == sp)
        seeds = (42, 43, 44) if sp != "test" else (45, 46, 47)
        pref = "development" if sp != "test" else "confirmation"
        panel(ax, c, d, orc2(seeds, pref, sp), f"{sp} split", winners)
    axes[0].set_ylabel("net token saving (%)")
    axes[1].legend(loc="lower right", fontsize=6.3, framealpha=0.95)
    fig.suptitle("Selection $\\rightarrow$ generalization: consensus train candidates (orange) leave the gate on dev/test; the three DEER operating points (C/B/T) stay in it", fontsize=9)
    fig.tight_layout(rect=[0, 0, 1, 0.955]); savefig(fig, "fig_splits")

    # ---- Fig MODELS (2x2, small on top, all TEST split) ----
    fig, axes = plt.subplots(2, 2, figsize=(11.2, 9.0), sharex=True, sharey=True)
    cfg = [(D7, "DeepSeek-7B (dev model, test split)"), (Q3, "Qwen3-8B (dev model, test split)"),
           (B32, "Qwen-32B (held-out scale, test)"), (LL, "Llama-8B (held-out arch, test)")]
    for ax, (mid, title) in zip(axes.flat, cfg):
        c = macro(rows, lambda r, mid=mid: r["model"] == mid and r["split"] == "test" and selb(r))
        d = deer_by_tau_bank(lambda r, mid=mid: r["model"] == mid and r["split"] == "test") if mid in DEVID else deer_by_tau_heldout(mid)
        orc = oracle_point(mid, list(SEL), (45, 46, 47), "confirmation", {"test"})
        panel(ax, c, d, orc, title, winners)
    axes[0, 0].set_ylabel("net token saving (%)"); axes[1, 0].set_ylabel("net token saving (%)")
    axes[0, 0].legend(loc="lower right", fontsize=6.3, framealpha=0.95)
    fig.suptitle("Out-of-sample generalization (test split) across scale and architecture: dev-selected DEER points (C/B/T) stay in the gate on every model; consensus train candidates do not", fontsize=9)
    fig.tight_layout(rect=[0, 0, 1, 0.955]); savefig(fig, "fig_models")

    # ---- Fig BENCH (test split, dev models) ----
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.7), sharey=True)
    for ax, b in zip(axes, ["math500", "amc23", "aime24"]):
        c = macro(rows, lambda r, b=b: r["benchmark"] == b and r["split"] == "test" and selb(r) and r["model"] in DEVID)
        d = deer_by_tau_bank(lambda r, b=b: r["benchmark"] == b and r["split"] == "test")
        o1 = oracle_point(D7, [b], (45, 46, 47), "confirmation", {"test"}); o2 = oracle_point(Q3, [b], (45, 46, 47), "confirmation", {"test"})
        orc = ((o1[0] + o2[0]) / 2, (o1[1] + o2[1]) / 2) if o1 and o2 else (o1 or o2)
        panel(ax, c, d, orc, f"{b} (test)", winners)
    axes[0].set_ylabel("net token saving (%)")
    axes[1].legend(loc="lower right", fontsize=6.3, framealpha=0.95)
    fig.suptitle("Out-of-sample generalization (test split) across benchmarks: the consensus trade-off and DEER advantage hold on each", fontsize=9)
    fig.tight_layout(rect=[0, 0, 1, 0.955]); savefig(fig, "fig_bench")


if __name__ == "__main__":
    main()
