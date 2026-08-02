#!/usr/bin/env python3
"""Three composite generalization figures: DEER vs consensus (+ oracle) across
splits, models, and benchmarks. Reads committed banks; computes DEER-heldout and
the oracle upper bound from the probe banks."""
from __future__ import annotations
import glob, gzip, json, statistics, sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent
GOV = HERE.parent / "governor_v2"
RES = HERE.parent / "results"
BANK = RES / "governor_v2_ws_sweep"
sys.path.insert(0, str(GOV)); sys.path.insert(0, str(HERE.parent / "related_work"))
from replay_rules import answers_equal, valid_answer, normalize_answer, load_split_map  # noqa
from deer_threshold_sweep import THRESHOLDS, direct_submit_decision, eq, replay_problem, iter_bank  # noqa

SEL = {"math500": 16384, "amc23": 16384, "aime24": 32768}
GATES = [("conservative", 1.0, 0.10, "#16a34a"), ("balanced", 2.0, 0.20, "#2563eb"),
         ("token_efficient", 3.5, 0.30, "#9333ea")]
DEVID = {"deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "Qwen/Qwen3-8B"}
SLUG = {"deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": "deepseek-ai-deepseek-r1-distill-qwen-7b",
        "Qwen/Qwen3-8B": "qwen-qwen3-8b",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B": "deepseek-ai-deepseek-r1-distill-qwen-32b",
        "deepseek-ai/DeepSeek-R1-Distill-Llama-8B": "deepseek-ai-deepseek-r1-distill-llama-8b"}
split_map = load_split_map(GOV / "generated/split_manifest.json")


def load_gz(p):
    with gzip.open(p, "rt") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


# ---------- consensus ----------
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
    out = {}
    for rid, e in by.items():
        d = [float(x["accuracy_drop_pp"]) for x in e]
        s = [float(x["saving_fraction"]) for x in e]
        out[rid] = (statistics.fmean(d), statistics.fmean(s) * 100.0)
    return out


def frontier(pts):
    pts = sorted(pts, key=lambda t: (t[0], -t[1]))
    fr, best = [], float("-inf")
    for d, s in pts:
        if s > best:
            fr.append((d, s)); best = s
    return fr


# ---------- DEER ----------
def deer_dev_macro(keep):
    by = defaultdict(list)
    for r in load_gz(BANK / "deer/deer_threshold_sweep.jsonl.gz"):
        if keep(r):
            by[r["threshold"]].append(r)
    out = []
    for t, e in by.items():
        out.append((statistics.fmean(float(x["accuracy_drop_pp"]) for x in e),
                    statistics.fmean(float(x["saving_fraction"]) for x in e) * 100.0))
    return sorted(out)


def deer_heldout_macro(model_id):
    slug = SLUG[model_id]
    hb = RES / "related_work/deer_confidence_bank_cap30_heldout/test"
    per = defaultdict(list)
    for env in sorted(hb.glob(f"*__*__seed_*")):
        key, bench, stag = env.name.split("__")
        want = "qwen32b" if "32B" in model_id else "llama8b"
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
        base = {}
        for pid, m in midx.items():
            comp = m["finished_naturally"] and m["tokens_used"] <= budget
            base[pid] = {"baseline_complete": comp,
                         "baseline_correct": (eq(m["final_answer"], m["target"]) if comp and m["final_answer"] is not None else False),
                         "baseline_tokens": min(m["tokens_used"], budget)}
        for thr in THRESHOLDS:
            vals = [replay_problem(recs[pid], midx[pid], base[pid], thr, budget) for pid in recs]
            bl = statistics.fmean(v["baseline_decode_tokens"] for v in vals)
            tot = statistics.fmean(v["total_decode_tokens"] for v in vals)
            drop = 100 * (statistics.fmean(v["baseline_correct"] for v in vals) - statistics.fmean(v["correct"] for v in vals))
            per[thr].append((drop, (bl - tot) / bl if bl else 0.0))
    out = []
    for t, e in per.items():
        out.append((statistics.fmean(x[0] for x in e), statistics.fmean(x[1] for x in e) * 100.0))
    return sorted(out)


# ---------- oracle (earliest-correct-probe upper bound) ----------
def oracle_point(model_id, benchmarks, seeds, prefix, splits):
    slug = SLUG[model_id]
    per_env = []
    for bench in benchmarks:
        budget = SEL[bench]
        for seed in seeds:
            d = RES / f"governor_v2/{prefix}__{slug}__{bench}__seed_{seed}"
            traj = d / "main/traj"; probes = d / "dense_simple32/probes"
            if not traj.exists() or not probes.exists():
                continue
            drops = []; savs = []; base_c = []; orc_c = []
            for tp in traj.glob("problem_*.json"):
                t = json.loads(tp.read_text()); pid = int(t["problem_id"])
                if split_map.get((bench, pid)) not in splits:
                    continue
                target = t["target"]; toks = int(t["tokens_used"]); fin = bool(t["finished_naturally"])
                comp = fin and toks <= budget
                bc = (answers_equal(t.get("final_answer"), target) if comp and t.get("final_answer") is not None else False)
                bl = min(toks, budget)
                pf = probes / f"problem_{pid}.json"
                chosen = None; cum = 0
                if pf.exists():
                    pl = json.loads(pf.read_text())
                    for pr in sorted(pl.get("probes", []), key=lambda z: int(z["token_position"])):
                        if int(pr["token_position"]) > budget:
                            break
                        cum += int(pr.get("probe_out_tokens", 0))
                        a = str(pr.get("probe_answer", ""))
                        if valid_answer(normalize_answer(a), bench, "schema") and answers_equal(a, target):
                            chosen = (int(pr["token_position"]), cum); break
                if chosen is not None:
                    tot = chosen[0] + chosen[1]; oc = True
                else:
                    tot = bl; oc = bool(bc)
                base_c.append(bc); orc_c.append(oc)
                savs.append((bl - tot) / bl if bl else 0.0)
            if base_c:
                per_env.append((100 * (statistics.fmean(base_c) - statistics.fmean(orc_c)),
                                statistics.fmean(savs) * 100.0))
    if not per_env:
        return None
    return (statistics.fmean(p[0] for p in per_env), statistics.fmean(p[1] for p in per_env))


# ---------- plotting ----------
def panel(ax, cons, deer, oracle, title, highlight=None):
    for name, cap, floor, c in GATES:
        ax.add_patch(Rectangle((0, floor * 100), cap, 100 - floor * 100, facecolor=c, alpha=0.05,
                     edgecolor=c, lw=0.7, ls="--", zorder=1))
    cp = list(cons.values())
    ax.scatter([d for d, s in cp], [s for d, s in cp], s=5, c="#c2c6ce", alpha=0.55, linewidths=0,
               zorder=2, label=f"consensus (n={len(cp)})")
    if highlight:
        hp = [cons[i] for i in highlight if i in cons]
        if hp:
            ax.scatter([d for d, s in hp], [s for d, s in hp], s=14, c="#f59e0b", alpha=0.9,
                       linewidths=0, zorder=3, label=f"train-gate winners (n={len(hp)})")
    cf = frontier(cp)
    ax.step([d for d, s in cf], [s for d, s in cf], where="post", color="#dc2626", lw=1.4, zorder=4,
            label="consensus frontier")
    if deer:
        ax.plot([d for d, s in deer], [s for d, s in deer], "-D", color="#059669", ms=3.5, lw=1.3,
                zorder=5, label="DEER")
    if oracle:
        ax.scatter([oracle[0]], [oracle[1]], marker="*", s=140, c="#7c3aed", edgecolor="white",
                   linewidths=0.6, zorder=6, label="oracle")
    ax.set_xlim(-12, 30); ax.set_ylim(-5, 78)
    ax.axhline(0, color="#e5e7eb", lw=0.6, zorder=0); ax.axvline(0, color="#e5e7eb", lw=0.6, zorder=0)
    ax.set_xlabel("accuracy drop (pp)"); ax.set_title(title, fontsize=9)
    ax.grid(True, alpha=0.13)


def savefig(fig, name):
    out = HERE / "figures/gen"; out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{name}.pdf"); fig.savefig(out / f"{name}.png", dpi=140); plt.close(fig)
    print("wrote", name)


def main():
    rows = cons_rows()
    selb = lambda r: int(r["budget"]) == SEL[r["benchmark"]] if "budget" in r else True
    dev_models = ["deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "Qwen/Qwen3-8B"]

    # train-gate conservative winners (consensus), tracked across splits
    train_cons = macro(rows, lambda r: r["split"] == "train" and selb(r) and r["model"] in DEVID)
    tw = {i for i, (d, s) in train_cons.items() if d <= 1.0 and s >= 10.0}

    # ---- Fig 1: splits ----
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4), sharey=True)
    for ax, sp in zip(axes, ["train", "dev", "test"]):
        c = macro(rows, lambda r, sp=sp: r["split"] == sp and selb(r) and r["model"] in DEVID)
        d = deer_dev_macro(lambda r, sp=sp: r["split"] == sp)
        orc = oracle_point("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", list(SEL), (42, 43, 44) if sp != "test" else (45, 46, 47),
                           "development" if sp != "test" else "confirmation", {sp}) if sp else None
        # oracle over both dev models: average two models' points
        o2 = oracle_point("Qwen/Qwen3-8B", list(SEL), (42, 43, 44) if sp != "test" else (45, 46, 47),
                          "development" if sp != "test" else "confirmation", {sp})
        if orc and o2:
            orc = ((orc[0] + o2[0]) / 2, (orc[1] + o2[1]) / 2)
        panel(ax, c, d, orc, f"{sp} split", highlight=tw if sp != "train" else tw)
    axes[0].set_ylabel("net token saving (%)")
    axes[0].legend(loc="lower right", fontsize=6.5, framealpha=0.95)
    fig.suptitle("Selection across splits: train-gate winners (orange) fall out of the gate on dev/test; DEER and the oracle stay in the safe-and-saving corner", fontsize=9.5)
    fig.tight_layout(rect=[0, 0, 1, 0.96]); savefig(fig, "fig_splits")

    # ---- Fig 2: models (4) ----
    model_cfg = [("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "DeepSeek-7B (dev)", "dev", (42, 43, 44), "development"),
                 ("Qwen/Qwen3-8B", "Qwen3-8B (dev)", "dev", (42, 43, 44), "development"),
                 ("deepseek-ai/DeepSeek-R1-Distill-Qwen-32B", "Qwen-32B (held-out scale, test)", "test", (45, 46, 47), "confirmation"),
                 ("deepseek-ai/DeepSeek-R1-Distill-Llama-8B", "Llama-8B (held-out arch, test)", "test", (45, 46, 47), "confirmation")]
    fig, axes = plt.subplots(1, 4, figsize=(19, 4.3), sharey=True)
    for ax, (mid, title, sp, seeds, pref) in zip(axes, model_cfg):
        c = macro(rows, lambda r, mid=mid, sp=sp: r["model"] == mid and r["split"] == sp and selb(r))
        if mid in DEVID:
            d = deer_dev_macro(lambda r, mid=mid, sp=sp: r["model"] == mid and r["split"] == sp)
        else:
            d = deer_heldout_macro(mid)
        orc = oracle_point(mid, list(SEL), seeds, pref, {sp})
        panel(ax, c, d, orc, title)
    axes[0].set_ylabel("net token saving (%)")
    axes[0].legend(loc="lower right", fontsize=6.5, framealpha=0.95)
    fig.suptitle("Generalization across model scale and architecture: consensus never enters the conservative gate; DEER clears it on every model", fontsize=9.5)
    fig.tight_layout(rect=[0, 0, 1, 0.96]); savefig(fig, "fig_models")

    # ---- Fig 3: benchmarks (3) ----
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4), sharey=True)
    for ax, b in zip(axes, ["math500", "amc23", "aime24"]):
        c = macro(rows, lambda r, b=b: r["benchmark"] == b and r["split"] == "dev" and selb(r) and r["model"] in DEVID)
        d = deer_dev_macro(lambda r, b=b: r["benchmark"] == b and r["split"] == "dev")
        o1 = oracle_point("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", [b], (42, 43, 44), "development", {"dev"})
        o2 = oracle_point("Qwen/Qwen3-8B", [b], (42, 43, 44), "development", {"dev"})
        orc = ((o1[0] + o2[0]) / 2, (o1[1] + o2[1]) / 2) if o1 and o2 else (o1 or o2)
        panel(ax, c, d, orc, f"{b} (dev)")
    axes[0].set_ylabel("net token saving (%)")
    axes[0].legend(loc="lower right", fontsize=6.5, framealpha=0.95)
    fig.suptitle("Generalization across benchmarks (dev): the consensus trade-off and the DEER advantage hold on each", fontsize=9.5)
    fig.tight_layout(rect=[0, 0, 1, 0.96]); savefig(fig, "fig_bench")


if __name__ == "__main__":
    main()
