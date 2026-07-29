#!/usr/bin/env python3
"""Compile every [asy] figure in the human-eval problems to inline SVG.

Competition-math problems (MATH500/AMC/AIME) carry their diagrams as Asymptote
source inside [asy]...[/asy]. We compile each unique block to an inline <svg>
(via `asy -f svg`, which uses latex+dvisvgm) so annotators see the actual figure
instead of code. Output: fig_svgs.json = {block_hash: svg}. Deterministic,
idempotent, re-run safe. Requires `asy` + `dvisvgm` on PATH.
"""
import json, re, hashlib, subprocess, tempfile, glob, gzip, random, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FC = HERE.parent
ASY_RE = re.compile(r"\[asy\](.*?)\[/asy\]", re.S | re.I)

def block_hash(inner): return hashlib.sha1(inner.encode("utf-8")).hexdigest()[:16]

def taskA_problems():
    cases = json.load(open(FC/"results/stage1_logging/analysis/false_consensus_cases.json"))
    return [c["problem"] for c in cases]

def taskB_problems():
    SEED = 20260729; N_EQUIV, N_CLOSE, N_RANDOM = 34, 26, 30
    DEV = ["development__deepseek-ai-deepseek-r1-distill-qwen-7b__{b}__seed_42",
           "development__qwen-qwen3-8b__{b}__seed_42"]
    BENCH = ["math500", "amc23", "aime24"]
    def load(fp):
        o = gzip.open if fp.endswith(".gz") else open
        return json.load(o(fp, "rt"))
    recs = []
    for t in DEV:
        for b in BENCH:
            for fp in glob.glob(str(FC/"results/governor_v2"/t.format(b=b)/"main"/"traj"/"problem_*.json*")):
                r = load(fp)
                recs.append(dict(pid=r["problem_id"], b=b,
                                 model=("deepseek-7b" if "deepseek" in t else "qwen3-8b"),
                                 problem=r["problem"], target=str(r["target"]),
                                 fa=str(r.get("final_answer")), fc=bool(r["final_correct"])))
    def norm(s):
        s = s.lower(); s = re.sub(r"\\boxed|\\left|\\right|\\!|\\,|\\ |\$|\\text|[{}\s]", "", s)
        return s.replace("\\frac", "").replace("\\dfrac", "")
    def jacc(a, b):
        A, B = set(norm(a)), set(norm(b)); return len(A & B)/len(A | B) if (A | B) else 0.0
    for r in recs:
        r["_same"] = norm(r["fa"]) == norm(r["target"]); r["_j"] = jacc(r["fa"], r["target"])
    equiv = [r for r in recs if r["fc"] and not r["_same"]]
    close = [r for r in recs if (not r["fc"]) and r["_j"] >= 0.5]
    rng = random.Random(SEED); rng.shuffle(equiv); rng.shuffle(close)
    sample = equiv[:N_EQUIV] + close[:N_CLOSE]
    chosen = {(r["model"], r["b"], r["pid"]) for r in sample}
    pool = [r for r in recs if (r["model"], r["b"], r["pid"]) not in chosen]
    rng.shuffle(pool); sample += pool[:N_RANDOM]; rng.shuffle(sample)
    return [r["problem"] for r in sample]

# Try minimal->broad imports; pick the first that compiles (avoids name clashes
# when a simple import suffices). NOTE: this brew asy build ships geometry/graph/
# markers/patterns but NOT olympiad, so olympiad is not attempted here.
PREAMBLES = ["",
             "import graph;\n",
             "import geometry;\n",
             "import graph;\nimport geometry;\n",
             "import graph;\nimport geometry;\nimport markers;\nimport patterns;\n"]

def compile_svg(inner):
    """Return (svg_str, err) via asy->PDF->pdftocairo(vector SVG).

    asy's native -f svg goes through a ghostscript PostScript path that is broken
    with new gs (tex.pro not found); its -f pdf path works. pdftocairo turns that
    PDF into a self-contained vector SVG (glyphs as paths, no external refs).
    Try the block as-is first, then with progressively broader MATH imports.
    """
    # figures that set neither size() nor unitsize() render at asy's tiny default,
    # where fixed-size label text overlaps into an unreadable pile -> give them one.
    size_pre = "" if re.search(r"\b(size|unitsize)\s*\(", inner) else "size(300);\n"
    last = ""
    for pre in PREAMBLES:
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/"f.asy").write_text(pre + size_pre + inner, encoding="utf-8")
            try:
                p = subprocess.run(["asy", "-f", "pdf", "-o", "f", "f.asy"],
                                   cwd=d, capture_output=True, text=True, timeout=90)
            except subprocess.TimeoutExpired:
                last = "asy timeout"; continue
            pdf = Path(d)/"f.pdf"
            if not (pdf.exists() and pdf.stat().st_size > 0):
                last = ((p.stderr or "") + (p.stdout or "")).strip()[-400:]; continue
            try:
                q = subprocess.run(["pdftocairo", "-svg", "f.pdf", "f.svg"],
                                   cwd=d, capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired:
                last = "pdftocairo timeout"; continue
            svg = Path(d)/"f.svg"
            if svg.exists() and svg.stat().st_size > 0:
                return svg.read_text(encoding="utf-8", errors="replace"), None
            last = (q.stderr or "").strip()[-300:]
    return None, last

def sanitize(svg):
    svg = re.sub(r"<\?xml.*?\?>", "", svg, flags=re.S).strip()
    svg = re.sub(r"<!DOCTYPE.*?>", "", svg, flags=re.S).strip()
    # asy figures are tiny (pt); scale to a comfortable on-screen size, keep viewBox
    m = re.search(r'width="([\d.]+)pt"\s+height="([\d.]+)pt"', svg)
    if m:
        w = float(m.group(1))
        disp = min(480, max(160, round(w * 3)))
        svg = svg.replace(m.group(0), f'style="width:{disp}px;height:auto;max-width:100%"', 1)
    return svg

def main():
    if not shutil.which("asy"):
        print("ERROR: asy not on PATH", file=sys.stderr); sys.exit(2)
    uniq = {}
    for text in taskA_problems() + taskB_problems():
        for inner in ASY_RE.findall(text):
            uniq[block_hash(inner)] = inner
    print(f"unique [asy] blocks: {len(uniq)}")
    out, fails = {}, []
    for i, (h, inner) in enumerate(sorted(uniq.items()), 1):
        svg, err = compile_svg(inner)
        if svg:
            out[h] = sanitize(svg)
            print(f"[{i}/{len(uniq)}] OK   {h}  ({len(out[h])} B)")
        else:
            fails.append((h, err))
            print(f"[{i}/{len(uniq)}] FAIL {h}  {err[:120]!r}")
    json.dump(out, open(HERE/"fig_svgs.json", "w"))
    print(f"\nrendered {len(out)}/{len(uniq)} figures; {len(fails)} failed -> fig_svgs.json")
    for h, err in fails:
        print("  FAIL", h, repr(err)[:200])

if __name__ == "__main__":
    main()
