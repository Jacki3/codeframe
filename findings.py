"""Step 3: turn the coded corpus into findings.

    python findings.py --data ../myproject --generate
    python findings.py --data ../myproject --discussion
    python findings.py --data ../myproject --discussion --summarise
    python findings.py --data ../myproject --add "differences between the two conditions for the top ten codes"

Every figure is a SPEC - a small JSON object saying what to compare - held in
findings/specs.json. Rendering is deterministic from spec plus data, so the page
can be rebuilt from the corpus at any time and two people with the same corpus
get the same page.

--add is the only part that involves a model, and what it returns is a spec: a
chart kind, a column to split on, how many codes. It never returns a number and
never sees a quote. Every figure on the page is computed here, from the corpus,
by the code below. That is not a stylistic preference - a model asked to do
arithmetic over a corpus it cannot see will produce plausible figures, and
plausible figures in a findings section are worse than no findings section.

THE DENOMINATOR

Rates are over the participant frame in frame.csv - one row per (pid, unit).
Those rows exist whether or not anything has been coded, so "31% of units"
means 31% of the study, not 31% of whatever happened to get coded. Sources that
belong to no single unit, such as an interview covering a whole session, can be
coded and quoted but are counted against the participant rather than a unit, and
the figures say so where it matters.
"""
import argparse, collections, csv, json, os, re, statistics, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

csv.field_size_limit(10 ** 8)
KINDS = ("prevalence", "valence", "split", "measures", "dependence",
         "cooccur")
VALENCE_ORDER = ("pos", "mixed", "neutral", "neg", "")
# colours for source kinds, assigned by position - a project may have any
KIND_CLASS = ("pos", "mixed", "neutral", "neg")


# ------------------------------------------------------------------ loading

def _read(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load(root):
    root = os.path.abspath(root)
    frame = _read(os.path.join(root, "frame.csv"))
    for r in frame:                        # unit and game are the same column
        r.setdefault("unit", r.get("game", ""))
    if not frame:
        raise SystemExit(f"no frame.csv in {root} - run setup_project.py --apply first")
    meta = {}
    p = os.path.join(root, "frame.json")
    if os.path.exists(p):
        meta = json.load(open(p, encoding="utf-8"))

    excerpts = {x["excerpt_id"]: x for x in _read(os.path.join(root, "data", "excerpts.csv"))}
    codings = _read(os.path.join(root, "data", "codings.csv"))
    codes = _read(os.path.join(root, "codebook", "codes.csv"))
    if not codings:
        raise SystemExit(f"nothing coded in {root} yet")

    keys = {(r["pid"], r.get("unit", "")) for r in frame}
    # plays touched per code, and the codings behind them
    plays, by_code = collections.defaultdict(set), collections.defaultdict(list)
    loose = collections.defaultdict(set)
    for c in codings:
        x = excerpts.get(c["excerpt_id"])
        if not x:
            continue
        k = (x["pid"], x.get("unit") or x.get("game", ""))
        by_code[c["code_id"]].append((c, x))
        (plays[c["code_id"]] if k in keys else loose[c["code_id"]]).add(
            k if k in keys else x["pid"])
    unit = meta.get("unit_label") or "unit"
    return {"root": root, "frame": frame, "keys": keys, "meta": meta,
            "unit": unit, "units": unit + ("s" if not unit.endswith("s") else ""),
            "kinds": meta.get("kinds") or sorted(
                {x.get("kind", "") for x in excerpts.values() if x.get("kind")}),
            "excerpts": excerpts, "codings": codings,
            "codes": {c["code_id"]: c for c in codes},
            "plays": plays, "by_code": by_code, "loose": loose,
            "frame_by": {(r["pid"], r.get("unit", "")): r for r in frame}}


def categories(D):
    """Frame columns worth splitting on, and their values in a stable order."""
    # "facets" is the shortlist chosen for the coding rail; honour that order here
    # too, so the default splits are the comparisons the study is actually about
    # rather than whichever categories happen to come first in the frame.
    declared = D["meta"].get("facets") or []
    declared += [c for c in (D["meta"].get("categories") or []) if c not in declared]
    out = {}
    for c in declared or []:
        vals = sorted({r[c] for r in D["frame"] if r.get(c)})
        if 1 < len(vals) <= 12:
            out[c] = vals
    if not out:                            # no frame.json: fall back to shape
        for c in D["frame"][0]:
            if c in ("pid", "unit", "game"):
                continue
            vals = sorted({r[c] for r in D["frame"] if r.get(c)})
            if 1 < len(vals) <= 12 and not all(
                    re.fullmatch(r"-?\d+(\.\d+)?", v) for v in vals):
                out[c] = vals
    return out


def measures(D):
    declared = D["meta"].get("measures") or []
    if declared:
        return [m for m in declared if m in D["frame"][0]]
    return [c for c in D["frame"][0]
            if c not in ("pid", "unit", "game")
            and all(re.fullmatch(r"-?\d+(\.\d+)?", r[c]) for r in D["frame"] if r.get(c))]


def ranked(D):
    return sorted(D["plays"], key=lambda c: (-len(D["plays"][c]), c))


def name_of(D, cid):
    return (D["codes"].get(cid) or {}).get("name", "")


# -------------------------------------------------------------- computation

def f_prevalence(D, spec):
    n = len(D["keys"])
    rows = []
    for cid in ranked(D)[:spec.get("top", 15)]:
        hits = len(D["plays"][cid])
        rows.append({"code": cid, "name": name_of(D, cid), "plays": hits,
                     "pct": round(100 * hits / n, 1),
                     "loose": len(D["loose"].get(cid, ()))})
    return {"rows": rows, "total": n,
            "note": f"Share of the {n} {D['units']} in the frame where the code appears "
                    "at least once."}


def f_valence(D, spec):
    rows = []
    for cid in ranked(D)[:spec.get("top", 15)]:
        tally = collections.Counter(c["valence"] for c, _ in D["by_code"][cid])
        total = sum(tally.values())
        rows.append({"code": cid, "name": name_of(D, cid), "total": total,
                     "parts": [(v, tally.get(v, 0)) for v in VALENCE_ORDER if tally.get(v)],
                     "declared": (D["codes"].get(cid) or {}).get("valence", "")})
    return {"rows": rows,
            "note": "Shares of each code's codings. A blank segment is a coding "
                    "nobody has judged yet, which is not the same as neutral."}


def f_split(D, spec):
    by = spec.get("by")
    cats = categories(D)
    if by not in cats:
        raise SystemExit(f"cannot split by '{by}' - available: {', '.join(cats)}")
    vals = cats[by]
    # denominator per group: how many frame rows carry that value
    denom = {v: sum(1 for r in D["frame"] if r.get(by) == v) for v in vals}
    rows = []
    for cid in ranked(D)[:spec.get("top", 15)]:
        pcts = []
        for v in vals:
            hit = sum(1 for k in D["plays"][cid] if D["frame_by"][k].get(by) == v)
            pcts.append(round(100 * hit / denom[v], 1) if denom[v] else 0.0)
        rows.append({"code": cid, "name": name_of(D, cid), "pcts": pcts,
                     "gap": round(max(pcts) - min(pcts), 1)})
    rows.sort(key=lambda r: -r["gap"])
    return {"rows": rows, "values": vals, "denom": [denom[v] for v in vals], "by": by,
            "note": f"Each cell is the share of that {by} group's {D['units']} carrying "
                    "the code. Rows are ordered by the spread between the extremes, so "
                    "the codes that separate the groups most come first."}


def f_measures(D, spec):
    ms = measures(D)
    if not ms:
        return {"rows": [], "note": "No numeric measures in the frame."}
    top = spec.get("top", 12)
    min_n = spec.get("min_n", 5)
    only = set(spec.get("measures") or ms)
    out = []
    for cid in ranked(D)[:top]:
        got = D["plays"][cid]
        for m in ms:
            if m not in only:
                continue
            with_, without = [], []
            for k, r in D["frame_by"].items():
                v = r.get(m, "")
                if not re.fullmatch(r"-?\d+(\.\d+)?", v or ""):
                    continue
                (with_ if k in got else without).append(float(v))
            if len(with_) < min_n or len(without) < min_n:
                continue
            d = statistics.mean(with_) - statistics.mean(without)
            out.append({"code": cid, "name": name_of(D, cid), "measure": m,
                        "with": round(statistics.mean(with_), 2),
                        "without": round(statistics.mean(without), 2),
                        "diff": round(d, 2), "n": len(with_)})
    out.sort(key=lambda r: -abs(r["diff"]))
    if not out:
        best = max((len(D["plays"][c]) for c in ranked(D)[:top]), default=0)
        return {"rows": [], "min_n": min_n,
                "empty": f"No code is on {min_n} {D['units']} yet - the most-used one is "
                         f"on {best}. Comparing means below that would be arithmetic, "
                         f"not evidence.",
                "note": "This figure fills in as coding accumulates; the threshold is "
                        "there so it cannot report on one or two people."}
    return {"rows": out[:spec.get("show", 14)], "min_n": min_n,
            "note": f"Mean score on {D['units']} carrying the code against those without, "
                    f"for codes seen on at least {min_n} {D['units']} either side. A "
                    "difference is a difference, not a cause: the same passage that "
                    "earned the code may be what depressed the score."}


def f_dependence(D, spec):
    rows = []
    for cid in ranked(D)[:spec.get("top", 15)]:
        kinds = collections.Counter(x.get("kind", "") for _, x in D["by_code"][cid])
        total = sum(kinds.values())
        if not total:
            continue
        rows.append({"code": cid, "name": name_of(D, cid), "total": total,
                     "parts": [(k, n) for k, n in kinds.most_common()]})
    return {"rows": rows,
            "note": "Where each code's evidence came from. A code living almost "
                    "entirely in one kind of source is a code the other kinds did not "
                    "reach, which matters whenever the kinds do not cover the same "
                    "people."}


def f_cooccur(D, spec):
    """Which codes travel together.

    Two levels, and they say different things. At excerpt level the same passage
    carries both codes, which is a claim about one thing somebody said. At unit
    level the same person said both about the same unit, which is a claim about
    an experience rather than a sentence. Unit is the default because it shares
    its denominator with every other figure here.
    """
    level = spec.get("level") if spec.get("level") in ("unit", "excerpt") else "unit"
    codes = ranked(D)[:spec.get("top", 12)]
    sets = ({c: {x["excerpt_id"] for _, x in D["by_code"][c]} for c in codes}
            if level == "excerpt" else {c: set(D["plays"][c]) for c in codes})

    matrix = [[len(sets[a]) if a == b else len(sets[a] & sets[b]) for b in codes]
              for a in codes]
    pairs = []
    for i, a in enumerate(codes):
        for b in codes[i + 1:]:
            both, union = len(sets[a] & sets[b]), len(sets[a] | sets[b])
            if both:
                pairs.append({"a": a, "b": b, "both": both,
                              "jaccard": round(both / union, 2) if union else 0.0})
    pairs.sort(key=lambda p: (-p["both"], -p["jaccard"]))
    where = "the same excerpt" if level == "excerpt" else f"the same {D['unit']}"
    return {"codes": codes, "matrix": matrix, "pairs": pairs[:10], "level": level,
            "empty": f"No two of these codes share {where} yet.",
            "note": f"How many times two codes land on {where}. The diagonal is each "
                    "code's own total, so a row reads as: of the N this code appears "
                    "on, how many also carry each other code. Jaccard in the list "
                    "below is the overlap as a share of everything either code "
                    "touches, which stops a common code looking related to all of "
                    "them. Co-occurrence is not influence: two codes can share a "
                    f"{D['unit']} because the same person is talkative."}


COMPUTE = {"prevalence": f_prevalence, "valence": f_valence, "split": f_split,
           "measures": f_measures, "dependence": f_dependence,
           "cooccur": f_cooccur}


# ----------------------------------------------------------------- defaults

def default_specs(D):
    cats = categories(D)
    specs = [{"id": "prevalence", "kind": "prevalence", "top": 15,
              "title": "How often each code appears"},
             {"id": "valence", "kind": "valence", "top": 15,
              "title": "Which direction each code runs"}]
    for by in list(cats)[:3]:
        specs.append({"id": f"split-{by}", "kind": "split", "by": by, "top": 15,
                      "title": f"Codes by {by.replace('_', ' ')}"})
    if measures(D):
        specs.append({"id": "measures", "kind": "measures", "top": 12, "show": 14,
                      "title": "What goes with higher and lower scores"})
    specs.append({"id": "cooccur", "kind": "cooccur", "top": 12, "level": "unit",
                  "title": "Which codes travel together"})
    specs.append({"id": "dependence", "kind": "dependence", "top": 15,
                  "title": "Where each code's evidence came from"})
    return specs


# ------------------------------------------------------------------ styling

CSS = """
:root{color-scheme:light;
 --ground:#F2F2EF;--surface:#FFF;--surface-2:#F8F8F5;--ink:#22212A;--ink-2:#56545F;
 --ink-3:#86848F;--rule:#E0DFDA;--accent:#6B7233;--accent-ink:#4E541F;
 --accent-wash:#EDEFE0;--pos:#3E7F4E;--neg:#B4593C;--mixed:#B08A2E;--neutral:#7A7885;
 --none:#C9C7C0;--mono:Consolas,"Cascadia Mono","SF Mono",Menlo,monospace;
 --body:"Segoe UI",-apple-system,BlinkMacSystemFont,Arial,sans-serif}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;
 --ground:#17171B;--surface:#1F1F25;--surface-2:#25252C;--ink:#EDECEE;--ink-2:#A9A7B2;
 --ink-3:#75737E;--rule:#31313A;--accent:#A8B45C;--accent-ink:#C3CE84;
 --accent-wash:#2A2D1E;--pos:#6FAE7E;--neg:#D18A6E;--mixed:#D6B45F;--neutral:#9997A3;
 --none:#42414A}}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font:16px/1.6 var(--body)}
.wrap{max-width:980px;margin:0 auto;padding:34px 24px 100px}
h1{font-size:25px;margin:0 0 4px}
h2{font-size:18px;margin:44px 0 0;padding-top:20px;border-top:1px solid var(--rule)}
h3{font-size:16px;margin:0 0 3px}
.sub{color:var(--ink-3);font-family:var(--mono);font-size:11.5px;margin:0 0 26px;line-height:1.7}
nav{margin:0 0 26px;font-family:var(--mono);font-size:12px}
nav a{color:var(--accent-ink);margin-right:14px}
.fig{background:var(--surface);border:1px solid var(--rule);border-radius:4px;
 padding:19px 22px;margin:16px 0 0}
figcaption{color:var(--ink-3);font-size:12.5px;margin-top:13px;line-height:1.6}
.bar-row{display:grid;grid-template-columns:210px 1fr 62px;gap:11px;align-items:center;
 margin-bottom:5px;font-size:13.5px}
.lab{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:var(--mono);
 font-size:11.5px;color:var(--ink-2)}
.bar-track{display:block;background:var(--surface-2);border-radius:2px;height:17px;overflow:hidden}
.bar-fill{display:block;height:100%;background:var(--accent);border-radius:2px}
.num{font-family:var(--mono);font-size:11.5px;color:var(--ink-3);text-align:right}
.stack{display:flex;height:17px;border-radius:2px;overflow:hidden;background:var(--surface-2)}
.stack i{display:block;height:100%}
.pos{background:var(--pos)}.neg{background:var(--neg)}.mixed{background:var(--mixed)}
.neutral{background:var(--neutral)}.none{background:var(--none)}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:13px;min-width:420px}
th{font-family:var(--mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;
 color:var(--ink-3);text-align:left;padding:0 6px 7px;font-weight:400}
th.r,td.r{text-align:right}
td{padding:4px 6px;border-top:1px solid var(--rule)}
td.code{font-family:var(--mono);font-size:11px;color:var(--ink-2);white-space:nowrap}
.cell{text-align:center;font-family:var(--mono);font-size:11px;border-radius:2px}
.key{font-family:var(--mono);font-size:11px;color:var(--ink-3);margin-top:11px}
.key i{display:inline-block;width:11px;height:11px;border-radius:2px;vertical-align:-1px;
 margin:0 4px 0 12px}
.q{background:var(--surface-2);border-left:3px solid var(--accent);border-radius:2px;
 padding:9px 13px;margin:9px 0;font-size:14px;color:var(--ink-2)}
.q cite{display:block;font-family:var(--mono);font-size:10.5px;color:var(--ink-3);
 font-style:normal;margin-top:6px}
.note{font-size:14px;margin:5px 0 14px}
.tag{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.08em;
 color:var(--accent-ink);background:var(--accent-wash);padding:2px 7px;border-radius:2px}
.ai{border-left:3px solid var(--mixed);padding-left:13px;margin:11px 0}
.ai .tag{color:var(--mixed);background:transparent;padding:0}
.empty{color:var(--ink-3);font-style:italic;font-size:14px}
"""


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def heat(pct, top):
    if not pct:
        return "color:var(--ink-3)"
    a = 0.10 + 0.75 * (pct / top if top else 0)
    return f"background:color-mix(in srgb, var(--accent) {a*100:.0f}%, transparent)"


# ------------------------------------------------------------------ figures

def draw(D, spec, res):
    H = [f'<figure class="fig"><h3>{esc(spec.get("title", spec["kind"]))}</h3>']
    if spec.get("asked"):
        H.append(f'<p class="sub" style="margin:2px 0 12px">asked: '
                 f'&ldquo;{esc(spec["asked"])}&rdquo;</p>')
    k = spec["kind"]

    if k == "prevalence":
        top = max([r["pct"] for r in res["rows"]] or [1])
        for r in res["rows"]:
            H.append(
                f'<div class="bar-row"><span class="lab" title="{esc(r["name"])}">'
                f'{esc(r["code"])}</span>'
                f'<span class="bar-track"><span class="bar-fill" '
                f'style="width:{100*r["pct"]/top:.1f}%" '
                f'title="{esc(r["code"])}: {r["plays"]} of {res["total"]} {D["units"]}">'
                f'</span></span><span class="num">{r["pct"]}%</span></div>')

    elif k == "valence":
        for r in res["rows"]:
            segs = "".join(
                f'<i class="{v or "none"}" style="width:{100*n/r["total"]:.1f}%" '
                f'title="{esc(v or "not judged")}: {n}"></i>' for v, n in r["parts"])
            H.append(f'<div class="bar-row"><span class="lab" title="{esc(r["name"])}">'
                     f'{esc(r["code"])}</span><span class="stack">{segs}</span>'
                     f'<span class="num">{r["total"]}</span></div>')
        H.append('<p class="key">'
                 + "".join(f'<i class="{c}"></i>{c}' for c in
                           ("pos", "mixed", "neutral", "neg"))
                 + '<i class="none"></i>not judged</p>')

    elif k == "split":
        top = max([p for r in res["rows"] for p in r["pcts"]] or [1])
        H.append('<div class="scroll"><table><tr><th>code</th>'
                 + "".join(f'<th class="r">{esc(v)}<br><span style="opacity:.6">'
                           f'n={n}</span></th>' for v, n in zip(res["values"], res["denom"]))
                 + '<th class="r">spread</th></tr>')
        for r in res["rows"]:
            H.append(f'<tr><td class="code" title="{esc(r["name"])}">{esc(r["code"])}</td>'
                     + "".join(f'<td class="cell" style="{heat(p, top)}">{p}%</td>'
                               for p in r["pcts"])
                     + f'<td class="r num">{r["gap"]}</td></tr>')
        H.append('</table></div>')

    elif k == "measures":
        if not res["rows"]:
            H.append(f'<p class="empty">{esc(res.get("empty", "Nothing to report."))}</p>')
        else:
            H.append('<div class="scroll"><table><tr><th>code</th><th>measure</th>'
                     '<th class="r">with</th>'
                     '<th class="r">without</th><th class="r">diff</th><th class="r">n</th></tr>')
            for r in res["rows"]:
                col = "var(--pos)" if r["diff"] > 0 else "var(--neg)"
                H.append(f'<tr><td class="code" title="{esc(r["name"])}">{esc(r["code"])}</td>'
                         f'<td>{esc(r["measure"])}</td><td class="r num">{r["with"]}</td>'
                         f'<td class="r num">{r["without"]}</td>'
                         f'<td class="r num" style="color:{col}">{r["diff"]:+}</td>'
                         f'<td class="r num">{r["n"]}</td></tr>')
            H.append('</table></div>')

    elif k == "cooccur":
        cs = res["codes"]
        hi = max([n for i, row in enumerate(res["matrix"])
                  for j, n in enumerate(row) if i != j] or [1])
        H.append('<div class="scroll"><table><tr><th>code</th>'
                 + "".join(f'<th class="r">{i+1}</th>' for i in range(len(cs)))
                 + '</tr>')
        for i, (cid, row) in enumerate(zip(cs, res["matrix"])):
            cells = "".join(
                f'<td class="cell" style="{"color:var(--ink-3)" if i == j else heat(n, hi)}"'
                f' title="{esc(cid)} + {esc(cs[j])}: {n}">{n or ""}</td>'
                for j, n in enumerate(row))
            H.append(f'<tr><td class="code">{i+1}. {esc(cid)}</td>{cells}</tr>')
        H.append('</table></div>')
        if res["pairs"]:
            H.append('<p class="key" style="margin-top:14px">strongest pairs</p>'
                     '<div class="scroll"><table><tr><th>pair</th>'
                     '<th class="r">together</th><th class="r">jaccard</th></tr>')
            for p in res["pairs"]:
                H.append(f'<tr><td class="code">{esc(p["a"])} + {esc(p["b"])}</td>'
                         f'<td class="r num">{p["both"]}</td>'
                         f'<td class="r num">{p["jaccard"]}</td></tr>')
            H.append('</table></div>')
        else:
            H.append(f'<p class="empty">{esc(res["empty"])}</p>')

    elif k == "dependence":
        for r in res["rows"]:
            segs = "".join(
                f'<i class="{KIND_CLASS[D["kinds"].index(kk) % len(KIND_CLASS)] if kk in D["kinds"] else "neutral"}" '
                f'style="width:{100*n/r["total"]:.1f}%" title="{esc(kk)}: {n}"></i>'
                for kk, n in r["parts"])
            H.append(f'<div class="bar-row"><span class="lab" title="{esc(r["name"])}">'
                     f'{esc(r["code"])}</span><span class="stack">{segs}</span>'
                     f'<span class="num">{r["total"]}</span></div>')
        kinds = sorted({kk for r in res["rows"] for kk, _ in r["parts"]})
        H.append('<p class="key">' + "".join(
            f'<i class="{KIND_CLASS[D["kinds"].index(kk) % len(KIND_CLASS)] if kk in D["kinds"] else "neutral"}"></i>{esc(kk)}'
            for kk in kinds) + '</p>')

    H.append(f'<figcaption>{esc(res["note"])}</figcaption></figure>')
    return "".join(H)


def page(D, specs, results, title="Findings"):
    n_cod = len(D["codings"])
    n_x = len({c["excerpt_id"] for c in D["codings"]})
    touched = len({k for cid in D["plays"] for k in D["plays"][cid]})
    H = [f'<!doctype html><html lang="en"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         f'<title>{esc(title)}</title><style>{CSS}</style></head><body><div class="wrap">',
         f'<h1>{esc(title)}</h1>',
         f'<p class="sub">{len(D["keys"])} {D["units"]} &middot; '
         f'{len({r["pid"] for r in D["frame"]})} participants &middot; '
         f'{len(D["codes"])} codes &middot; {n_x} excerpts &middot; {n_cod} codings<br>'
         f'{touched} of {len(D["keys"])} {D["units"]} have at least one coding'
         f'</p>',
         '<nav><a href="findings.html">Findings</a>'
         '<a href="discussion.html">Discussion</a></nav>']
    for spec, res in zip(specs, results):
        H.append(draw(D, spec, res))
    H.append('</div></body></html>')
    return "".join(H)


# -------------------------------------------------------------- the commands

def out_dir(root):
    d = os.path.join(root, "findings")
    os.makedirs(d, exist_ok=True)
    return d


def write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def specs_path(root):
    return os.path.join(out_dir(root), "specs.json")


def load_specs(root):
    p = specs_path(root)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []


def build(D, specs):
    results, kept = [], []
    for s in specs:
        try:
            results.append(COMPUTE[s["kind"]](D, s))
            kept.append(s)
        except SystemExit as e:
            print(f"  skipped {s.get('id', s['kind'])}: {e}")
    return kept, results


def cmd_generate(root, keep_custom=True):
    D = load(root)
    existing = [s for s in load_specs(root) if s.get("custom")] if keep_custom else []
    specs = default_specs(D) + existing
    specs, results = build(D, specs)
    write(specs_path(root), json.dumps(specs, indent=1))
    p = os.path.join(out_dir(root), "findings.html")
    write(p, page(D, specs, results))
    print(f"wrote {p}")
    for s in specs:
        print(f"  {s['id']:<20} {s.get('title', '')}"
              + ("   [custom]" if s.get("custom") else ""))
    return D


# ---- discussion ----

def gather_notes(D):
    """Every note in the project, with the evidence it was written against."""
    out = collections.defaultdict(list)
    for c in D["codings"]:
        note = (c.get("note") or "").strip()
        if not note:
            continue
        x = D["excerpts"].get(c["excerpt_id"], {})
        out[c["code_id"]].append({
            "note": note, "valence": c.get("valence", ""),
            "text": (x.get("text") or "").strip(),
            "where": f'PID{x.get("pid", "?")}'
                     + (f' &middot; {x["game"]}' if x.get("game") else "")
                     + (f' &middot; {x["kind"]}' if x.get("kind") else "")})
    return out


def standing_notes(root, D):
    """Notes about the study rather than about a code.

    codebook/notes.csv, if you keep one. A coding note is tied to a passage and
    answers "what is going on here"; these answer "what should a reader know
    before believing any of it" - that the survey caught the moment and the
    interview caught the reflection, that the weather was cold, that a column in
    the raw export is wrong for nine people, that a null result is a real result.

    They are the half of a discussion that has no code to hang from, and without
    somewhere to put them they get written in a notebook and lost. Four of the
    twelve that prompted this cite no evidence at all, which is why evidence is
    optional here.

        note_id, category, title, note, evidence

    evidence is optional and may name an excerpt or a source; anything else is
    shown as written.
    """
    rows = _read(os.path.join(root, "codebook", "notes.csv"))
    if not rows:
        return []
    srcs = {s["source_id"]: s for s in _read(os.path.join(root, "sources.csv"))}
    out = []
    for r in rows:
        ev = (r.get("evidence") or r.get("evidence_segment_id") or "").strip()
        quote = where = ""
        x = D["excerpts"].get(ev)
        if x:
            quote, where = (x.get("text") or "").strip(), f'PID{x.get("pid", "?")}'
        elif ev in srcs:
            s = srcs[ev]
            quote = (s.get("text") or "").strip()[:400]
            where = f'PID{s.get("pid", "?")} · {s.get("label", "")}'.strip(" ·")
        out.append({"id": (r.get("note_id") or "").strip(),
                    "category": (r.get("category") or "Uncategorised").strip(),
                    "title": (r.get("title") or "").strip(),
                    "note": (r.get("note") or "").strip(),
                    "evidence": ev, "quote": quote, "where": where})
    return out


def draw_standing(notes):
    if not notes:
        return ""
    by_cat = collections.defaultdict(list)
    for n in notes:
        by_cat[n["category"]].append(n)
    H = ['<h2>About the study</h2>',
         f'<p class="sub" style="margin:6px 0 0">{len(notes)} notes in '
         f'{len(by_cat)} categories, shown as written. These are about method, '
         f'not about any one code, and they frame how to read everything below.</p>']
    for cat in sorted(by_cat):
        H.append(f'<figure class="fig"><h3>{esc(cat)}</h3>')
        for n in by_cat[cat]:
            H.append('<p class="note">'
                     + (f'<span class="tag">{esc(n["id"])}</span> ' if n["id"] else "")
                     + f'<b>{esc(n["title"])}</b></p>')
            if n["note"]:
                H.append(f'<p class="note" style="color:var(--ink-2)">'
                         f'{esc(n["note"])}</p>')
            if n["quote"]:
                H.append(f'<blockquote class="q">{esc(n["quote"][:400])}'
                         f'{"&hellip;" if len(n["quote"]) > 400 else ""}'
                         f'<cite>{esc(n["where"] or n["evidence"])}</cite></blockquote>')
            elif n["evidence"]:
                H.append(f'<p class="sub" style="margin:2px 0 10px">evidence: '
                         f'{esc(n["evidence"])} — not found in this project</p>')
        H.append('</figure>')
    return "".join(H)


def discussion_page(D, notes, summaries, standing=()):
    by_lens = collections.defaultdict(list)
    for cid in sorted(notes, key=lambda c: -len(D["plays"].get(c, ()))):
        by_lens[(D["codes"].get(cid) or {}).get("lens") or "Uncategorised"].append(cid)

    total = sum(len(v) for v in notes.values())
    H = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         f'<title>Discussion</title><style>{CSS}</style></head><body><div class="wrap">',
         '<h1>Discussion</h1>',
         f'<p class="sub">'
         + (f'{len(standing)} notes about the study &middot; ' if standing else '')
         + f'{total} coding notes across {len(notes)} codes</p>',
         '<nav><a href="findings.html">Findings</a>'
         '<a href="discussion.html">Discussion</a></nav>',
         draw_standing(standing),
         ('<h2>By lens</h2><p class="sub" style="margin:6px 0 0">Notes written '
          'beside a coding, grouped by the lens of the code they sit on. Each is '
          'shown with the passage it was written against.</p>' if total else '')]
    if not total:
        H.append('<p class="empty">No notes yet. Add a note beside a coding in your '
                 'sheet and re-run.</p>')
    for lens, cids in by_lens.items():
        H.append(f'<h2>{esc(lens)}</h2>')
        if summaries.get(lens):
            H.append(f'<div class="ai"><span class="tag">summary &middot; generated</span>'
                     f'<p class="note">{esc(summaries[lens])}</p></div>')
        for cid in cids:
            c = D["codes"].get(cid) or {}
            H.append(f'<figure class="fig"><h3>{esc(cid)} &middot; {esc(c.get("name", ""))}'
                     f'</h3><p class="sub" style="margin:2px 0 10px">'
                     f'{len(D["plays"].get(cid, ()))} {D["units"]} &middot; '
                     f'{len(notes[cid])} note{"s" if len(notes[cid]) != 1 else ""}</p>')
            if c.get("definition"):
                H.append(f'<p class="note" style="color:var(--ink-2)">'
                         f'{esc(c["definition"])}</p>')
            for n in notes[cid]:
                H.append(f'<p class="note"><span class="tag">{esc(n["valence"] or "unjudged")}'
                         f'</span> {esc(n["note"])}</p>')
                if n["text"]:
                    H.append(f'<blockquote class="q">{esc(n["text"][:420])}'
                             f'{"&hellip;" if len(n["text"]) > 420 else ""}'
                             f'<cite>{n["where"]}</cite></blockquote>')
            H.append('</figure>')
    H.append('</div></body></html>')
    return "".join(H)


SUMMARY_TASK = """You are helping a researcher organise their own coding notes for
the discussion section of a qualitative study.

You are given, for one lens of the analysis, the notes the researcher wrote beside
their codings, with the code each note sits under. Write ONE short paragraph -
three or four sentences - drawing out what these notes have in common and where
they pull against each other.

Rules that matter more than fluency:
  - Say only what the notes say. Do not add interpretation they did not make.
  - Never state a number, a count, a percentage or a proportion. The figures are
    computed elsewhere and yours would be guesses.
  - Where notes disagree, say so plainly rather than smoothing it over. A tension
    between two notes is the most useful thing you can surface.
  - No preamble, no "in conclusion", no restating the lens name.

Reply with JSON only: {"summary": "<the paragraph>"}"""


def summarise(D, notes, lens_of, model):
    from review import ask
    by_lens = collections.defaultdict(list)
    for cid, ns in notes.items():
        by_lens[lens_of(cid)].append(
            {"code": cid, "notes": [n["note"] for n in ns]})
    out, cost = {}, 0
    for lens, items in by_lens.items():
        reply, env = ask({"lens": lens, "codes": items}, model=model, task=SUMMARY_TASK)
        s = str(reply.get("summary", "")).strip()
        if s:
            out[lens] = s
        cost += env.get("total_cost_usd") or 0
        print(f"  {lens}: {'summarised' if s else 'no summary returned'}")
    if cost:
        print(f"  cost: ${cost:.2f}")
    return out


def cmd_discussion(root, do_summarise, model):
    D = load(root)
    notes = gather_notes(D)
    standing = standing_notes(root, D)
    print(f"notes    : {sum(len(v) for v in notes.values())} coding notes "
          f"across {len(notes)} codes")
    if standing:
        cats = sorted({n["category"] for n in standing})
        print(f"           {len(standing)} about the study: {', '.join(cats)}")
        missing = [n["id"] or n["title"][:28] for n in standing
                   if n["evidence"] and not n["quote"]]
        if missing:
            print(f"           {len(missing)} cite evidence not in this project: "
                  + ", ".join(missing[:4]))
    else:
        print("           no codebook/notes.csv - see the header of that file's "
              "template for what it is for")
    summaries = {}
    if do_summarise and notes:
        print(f"\nsending your notes to {model} - the notes only, not the passages")
        summaries = summarise(
            D, notes, lambda c: (D["codes"].get(c) or {}).get("lens") or "Uncategorised",
            model)
    elif do_summarise:
        print("nothing to summarise.")
    p = os.path.join(out_dir(root), "discussion.html")
    write(p, discussion_page(D, notes, summaries, standing))
    print(f"\nwrote {p}")
    if not do_summarise:
        print("Pass --summarise to add a generated paragraph per lens.")


# ---- a new finding from a request ----

ADD_TASK = """You are turning a researcher's request into a chart specification for
a qualitative analysis page. You do not compute anything and you never state a
number: the figures are calculated from the corpus by the program that calls you.
Your only job is to say WHAT to compare.

You are given the columns the study can be split by with their values, the numeric
measures available, and the codes with how many units of the study each is on.

Choose one kind:

  prevalence  how often each code appears, as a share of all units.
  valence     the mix of pos/neg/mixed/neutral within each code's codings.
  split       a code-by-group table, one column per value of a category. This is
              the one for "differences between X and Y" requests. Set "by" to the
              category column name.
  measures    where a code coincides with higher or lower scores on the numeric
              measures. Optionally set "measures" to a subset of their names.
  dependence  which source kind each code's evidence came from.
  cooccur     which codes land together. Set "level" to "excerpt" for codes on
              the same passage, or "unit" (the default) for codes on the same
              unit of the study. This is the one for "which codes appear
              together", "what goes with X", and overlap questions.

Reply with JSON only:

{"kind": "<one of the above>",
 "by": "<category column, only for split>",
 "top": <how many codes, default 15>,
 "measures": ["<measure name>"],
 "level": "<unit or excerpt, only for cooccur>",
 "title": "<a short, plain title for the figure, sentence case, no numbers>",
 "why": "<one sentence on why this kind answers the request>"}

Use column and measure names exactly as given. If the request cannot be answered
by any of these kinds, reply {"error": "<what is missing, in one sentence>"}."""


def cmd_add(root, request, model):
    from review import ask
    D = load(root)
    cats = categories(D)
    payload = {
        "request": request,
        "categories": {k: v for k, v in cats.items()},
        "measures": measures(D)[:60],
        "codes": [{"code": c, "name": name_of(D, c), "units": len(D["plays"][c])}
                  for c in ranked(D)],
        "total_units": len(D["keys"]),
    }
    print(f'asking {model} how to answer: "{request}"')
    reply, env = ask(payload, model=model, task=ADD_TASK)
    if reply.get("error"):
        raise SystemExit(f"cannot build that: {reply['error']}")
    kind = reply.get("kind")
    if kind not in KINDS:
        raise SystemExit(f"unusable kind {kind!r} - expected one of {', '.join(KINDS)}")
    spec = {"id": f"custom-{len(load_specs(root)) + 1}", "kind": kind,
            "title": str(reply.get("title") or request)[:90],
            "top": int(reply.get("top") or 15), "custom": True, "asked": request,
            "why": str(reply.get("why", ""))[:200]}
    if kind == "split":
        by = reply.get("by")
        if by not in cats:
            raise SystemExit(f"cannot split by {by!r} - available: {', '.join(cats)}")
        spec["by"] = by
    if kind == "cooccur" and reply.get("level") in ("unit", "excerpt"):
        spec["level"] = reply["level"]
    if kind == "measures" and reply.get("measures"):
        keep = [m for m in reply["measures"] if m in measures(D)]
        if keep:
            spec["measures"] = keep

    # compute it before keeping it: a spec that cannot be built is not a finding
    COMPUTE[kind](D, spec)
    specs = load_specs(root) + [spec]
    write(specs_path(root), json.dumps(specs, indent=1))
    specs, results = build(D, specs)
    write(os.path.join(out_dir(root), "findings.html"), page(D, specs, results))
    cost = env.get("total_cost_usd")
    print(f"\nadded {spec['id']}: {spec['title']}")
    print(f"  kind: {kind}" + (f" by {spec['by']}" if spec.get("by") else ""))
    if spec["why"]:
        print(f"  why : {spec['why']}")
    print(f"\nwrote {os.path.join(out_dir(root), 'findings.html')}"
          + (f"  (${cost:.2f})" if cost else ""))


def main():
    ap = argparse.ArgumentParser(description="Build findings from a coded corpus.")
    ap.add_argument("--data", required=True)
    ap.add_argument("--generate", action="store_true", help="build the default findings")
    ap.add_argument("--discussion", action="store_true", help="build the discussion page")
    ap.add_argument("--summarise", action="store_true",
                    help="with --discussion: add a generated paragraph per lens")
    ap.add_argument("--add", metavar="REQUEST", help="add one finding from a request")
    ap.add_argument("--model", default=None,
                    help="override the model set by model.py, for this run")
    a = ap.parse_args()
    from model import current
    a.model = a.model or current()
    if a.add:
        cmd_add(a.data, a.add, a.model)
    elif a.discussion:
        cmd_discussion(a.data, a.summarise, a.model)
    elif a.generate:
        cmd_generate(a.data)
    else:
        ap.error("give --generate, --discussion, or --add")


if __name__ == "__main__":
    main()
