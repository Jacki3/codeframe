"""Check the corpus is what you think it is, and how far two coders agree.

    python audit.py --data ../myproject
    python audit.py --data ../myproject --reliability
    python audit.py --data ../myproject --reliability --against jb

Nothing here calls a model and nothing leaves the machine.

WHY AN AUDIT

Every number the findings report is computed from sources.csv and frame.csv, and
nothing else checks that those two files say what you believe. An import that
silently drops a third of the interview text produces a complete, plausible,
wrong set of findings, and the only symptom is that the corpus looks a bit thin -
which is easy to explain away. This lists what is actually there, and every
inconsistency it can find, so a bad import is loud rather than quiet.

WHY RELIABILITY IS AWKWARD HERE, AND WHAT IS REPORTED INSTEAD

Agreement figures assume both coders judged the same units. In an excerpt-first
model there are no units until somebody selects one, so if a second coder never
marks a passage there is no way to tell whether they disagreed with it or never
read it. Treating an unselected passage as a "no" would invent agreement out of
absence and inflate every figure.

So the comparison is made over the excerpts BOTH coders touched, and everything
outside that set is reported separately rather than folded in. Cohen's kappa on
that intersection is a real figure about a real overlap; the same statistic over
the union would not be.
"""
import argparse, collections, csv, io, json, os, re, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

csv.field_size_limit(10 ** 8)


def read(root, *parts):
    p = os.path.join(root, *parts)
    if not os.path.exists(p):
        return []
    with io.open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def unit_of(row):
    return row.get("unit") or row.get("game") or ""


# ------------------------------------------------------------------- audit

def audit(root):
    """Everything that can be checked without a model, in one report."""
    sources = read(root, "sources.csv")
    frame = read(root, "frame.csv")
    excerpts = read(root, "data", "excerpts.csv")
    codings = read(root, "data", "codings.csv")
    codes = read(root, "codebook", "codes.csv")
    meta = {}
    p = os.path.join(root, "frame.json")
    if os.path.exists(p):
        meta = json.load(io.open(p, encoding="utf-8"))
    unit_label = meta.get("unit_label") or "unit"
    units_label = unit_label + ("s" if not unit_label.endswith("s") else "")

    if not sources:
        raise SystemExit(f"no sources.csv in {root}")

    problems, notes = [], []
    print(f"project: {root}\n")

    # ---- the corpus ----
    kinds = collections.Counter(s.get("kind", "") for s in sources)
    words = sum(len((s.get("text") or "").split()) for s in sources)
    pids = {s["pid"] for s in sources}
    print("corpus")
    print(f"  {len(sources)} sources, {words:,} words, {len(pids)} participants")
    for k, n in kinds.most_common():
        w = sum(len((s.get("text") or "").split())
                for s in sources if s.get("kind") == k)
        med = sorted(len((s.get("text") or "").split())
                     for s in sources if s.get("kind") == k)[n // 2]
        print(f"    {k or '(no kind)':<14} {n:>5} sources  {w:>8,} words  "
              f"median {med:>5}")

    empty = [s["source_id"] for s in sources if not (s.get("text") or "").strip()]
    tiny = [s["source_id"] for s in sources
            if 0 < len((s.get("text") or "").split()) < 3]
    if empty:
        problems.append(f"{len(empty)} source(s) have no text at all: "
                        + ", ".join(empty[:5]))
    if tiny:
        notes.append(f"{len(tiny)} source(s) are under three words - probably "
                     f"'n/a' answers: " + ", ".join(tiny[:5]))

    # ---- the frame ----
    print(f"\nframe")
    keys = {(r["pid"], unit_of(r)) for r in frame}
    print(f"  {len(frame)} {units_label} over "
          f"{len({r['pid'] for r in frame})} participants")
    src_keys = collections.Counter((s["pid"], unit_of(s)) for s in sources)
    no_source = sorted(k for k in keys if not src_keys.get(k))
    loose = sorted({k for k in src_keys if k not in keys})
    if no_source:
        problems.append(
            f"{len(no_source)} {units_label} in the frame have no source at all - "
            f"they are in every denominator and can never be coded: "
            + ", ".join(f"{p}/{u}" for p, u in no_source[:5]))
    if loose:
        unitless = [k for k in loose if not k[1]]
        real = [k for k in loose if k[1]]
        if unitless:
            print(f"  {sum(src_keys[k] for k in unitless)} source(s) belong to "
                  f"no single {unit_label} (counted against the participant)")
        if real:
            problems.append(
                f"{len(real)} source(s) name a {unit_label} that is not in the "
                f"frame - they will be silently excluded from every rate: "
                + ", ".join(f"{p}/{u}" for p, u in real[:5]))

    # ---- excerpt integrity ----
    if excerpts:
        print(f"\nexcerpts")
        by_source = {s["source_id"]: s for s in sources}
        missing, drift, oob = [], [], []
        for x in excerpts:
            s = by_source.get(x["source_id"])
            if not s:
                missing.append(x["excerpt_id"]); continue
            try:
                a, b = int(x["start"]), int(x["end"])
            except (ValueError, KeyError):
                continue
            text = s.get("text") or ""
            if not (0 <= a < b <= len(text)):
                oob.append(x["excerpt_id"])
            elif (x.get("text") or "").strip() and text[a:b] != x["text"]:
                drift.append(x["excerpt_id"])
        print(f"  {len(excerpts)} excerpts, {len(codings)} codings")
        if missing:
            problems.append(f"{len(missing)} excerpt(s) point at a source that no "
                            f"longer exists: " + ", ".join(missing[:5]))
        if oob:
            problems.append(f"{len(oob)} excerpt(s) have offsets outside their "
                            f"source: " + ", ".join(oob[:5]))
        if drift:
            problems.append(
                f"{len(drift)} excerpt(s) no longer match the text at their "
                f"offsets - the source changed under them, so every quote from "
                f"these is suspect: " + ", ".join(drift[:5]))

        dup = [q for q, n in collections.Counter(
            (x.get("text") or "").strip().lower() for x in excerpts).items()
            if q and n > 1]
        if dup:
            notes.append(f"{len(dup)} passage(s) were coded more than once as "
                         f"separate excerpts")

    # ---- the codebook ----
    print(f"\ncodebook")
    known = {c["code_id"] for c in codes}
    used = collections.Counter(c["code_id"] for c in codings)
    retired = {r["old_id"]: r.get("new_id", "")
               for r in read(root, "codebook", "retired_codes.csv")}
    print(f"  {len(codes)} codes, {len(used)} of them used")
    orphan = sorted(c for c in used if c not in known and c not in retired)
    unused = sorted(c for c in known if not used.get(c))
    nolens = sorted(c["code_id"] for c in codes
                    if not (c.get("lens") or "").strip())
    if orphan:
        problems.append(
            f"{len(orphan)} code(s) are used by codings but are not in "
            f"codes.csv - renamed without retiring? " + ", ".join(orphan[:5])
            + "  (see retire.py)")
    if unused:
        notes.append(f"{len(unused)} code(s) have nothing coded to them: "
                     + ", ".join(unused[:6]))
    if nolens:
        notes.append(f"{len(nolens)} code(s) have no lens and will group under "
                     f"\"Uncategorised\": " + ", ".join(nolens[:6]))
    if retired:
        print(f"  {len(retired)} retired code(s) on the register")

    # ---- coverage ----
    if codings:
        by_x = {x["excerpt_id"]: x for x in excerpts}
        touched = {(by_x[c["excerpt_id"]]["pid"], unit_of(by_x[c["excerpt_id"]]))
                   for c in codings if c["excerpt_id"] in by_x}
        in_frame = touched & keys
        per_pid = collections.Counter(
            by_x[c["excerpt_id"]]["pid"] for c in codings if c["excerpt_id"] in by_x)
        silent = sorted({s["pid"] for s in sources} - set(per_pid), key=str)
        print(f"\ncoverage")
        print(f"  {len(in_frame)} of {len(keys)} {units_label} have a coding "
              f"({100*len(in_frame)/len(keys):.0f}%)" if keys else "")
        print(f"  {len(per_pid)} of {len(pids)} participants are quoted")
        if silent:
            notes.append(f"{len(silent)} participant(s) have nothing coded at all: "
                         + ", ".join(silent[:8]))
        if per_pid:
            top = per_pid.most_common(1)[0]
            share = 100 * top[1] / len(codings)
            if share > 25:
                notes.append(
                    f"PID{top[0]} accounts for {share:.0f}% of all codings - "
                    f"worth knowing before quoting them as typical")

    # ---- verdict ----
    print()
    for n in notes:
        print(f"  note: {n}")
    for p_ in problems:
        print(f"  PROBLEM: {p_}")
    if not problems:
        print("  no inconsistencies found"
              + (f", {len(notes)} thing(s) worth a look" if notes else ""))
    return len(problems)


# ------------------------------------------------------------- reliability

def kappa(a, b, c, d):
    """Cohen's kappa from a 2x2 table. None when it cannot be defined."""
    n = a + b + c + d
    if not n:
        return None
    po = (a + d) / n
    pe = ((a + b) / n) * ((a + c) / n) + ((c + d) / n) * ((b + d) / n)
    if pe >= 1:
        return None
    return (po - pe) / (1 - pe)


def strength(k):
    if k is None:
        return "not defined"
    for floor, word in ((0.81, "almost perfect"), (0.61, "substantial"),
                        (0.41, "moderate"), (0.21, "fair"), (0.0, "slight")):
        if k >= floor:
            return word
    return "worse than chance"


def reliability(root, other=None):
    codings = read(root, "data", "codings.csv")
    excerpts = {x["excerpt_id"]: x for x in read(root, "data", "excerpts.csv")}
    if not codings:
        raise SystemExit(f"nothing coded in {root} yet")

    coders = sorted({(c.get("coder") or "").strip() or "(unnamed)"
                     for c in codings})
    print(f"coders on record: {', '.join(coders)}\n")
    if len(coders) < 2:
        raise SystemExit(
            "only one coder in codings.csv, so there is nothing to compare.\n"
            "  A second coder files their own sheet with --coder theirname:\n"
            "    python file_codings.py --data <p> --sheet theirs.csv "
            "--coder jb --apply")
    if other and other not in coders:
        raise SystemExit(f"no coder called {other!r} - found: {', '.join(coders)}")
    a_name = coders[0]
    b_name = other or coders[1]
    if a_name == b_name:
        a_name = next(c for c in coders if c != b_name)

    def codes_by(name):
        out = collections.defaultdict(set)
        for c in codings:
            who = (c.get("coder") or "").strip() or "(unnamed)"
            if who == name:
                out[c["excerpt_id"]].add(c["code_id"])
        return out

    A, B = codes_by(a_name), codes_by(b_name)
    both = sorted(set(A) & set(B))
    only_a, only_b = sorted(set(A) - set(B)), sorted(set(B) - set(A))

    print(f"comparing {a_name!r} against {b_name!r}")
    print(f"  {len(both)} excerpt(s) both coded - the comparable set")
    print(f"  {len(only_a)} only {a_name}, {len(only_b)} only {b_name}")
    if not both:
        raise SystemExit(
            "\nno excerpt was coded by both, so there is no overlap to measure.\n"
            "  Agreement needs the two coders to have judged the same passages.")
    outside = len(only_a) + len(only_b)
    if outside:
        print(f"\n  {outside} excerpt(s) fall outside the comparison. An excerpt "
              f"one coder\n  never marked may be a disagreement or may be a "
              f"passage they never read,\n  and nothing in the data says which - "
              f"so they are excluded rather than\n  counted as agreement.")

    # per-code agreement over the comparable set
    every = sorted({c for s in list(A.values()) + list(B.values()) for c in s})
    rows = []
    for cid in every:
        a = sum(1 for x in both if cid in A[x] and cid in B[x])
        b = sum(1 for x in both if cid in A[x] and cid not in B[x])
        c = sum(1 for x in both if cid not in A[x] and cid in B[x])
        d = len(both) - a - b - c
        if a + b + c == 0:
            continue
        k = kappa(a, b, c, d)
        rows.append({"code": cid, "both": a, "only_a": b, "only_b": c,
                     "kappa": k, "agree": (a + d) / len(both)})
    rows.sort(key=lambda r: (r["kappa"] is None, r["kappa"]))

    print(f"\nper code, over the {len(both)} shared excerpts")
    print(f"  {'code':<22} {'both':>5} {'only ' + a_name[:6]:>12} "
          f"{'only ' + b_name[:6]:>12} {'kappa':>7}")
    for r in rows:
        k = "  n/a" if r["kappa"] is None else f"{r['kappa']:.2f}"
        print(f"  {r['code']:<22} {r['both']:>5} {r['only_a']:>12} "
              f"{r['only_b']:>12} {k:>7}")

    # overall: did the two apply the same set of codes to each shared excerpt?
    exact = sum(1 for x in both if A[x] == B[x])
    ks = [r["kappa"] for r in rows if r["kappa"] is not None]
    print(f"\noverall")
    print(f"  {exact} of {len(both)} shared excerpts got exactly the same codes "
          f"({100*exact/len(both):.0f}%)")
    if ks:
        mean = sum(ks) / len(ks)
        print(f"  mean kappa across {len(ks)} code(s): {mean:.2f} ({strength(mean)})")
        print(f"  lowest: {rows[0]['code']} at {rows[0]['kappa']:.2f}")

    # the useful part: what they actually disagreed about
    dis = [(x, sorted(A[x] - B[x]), sorted(B[x] - A[x])) for x in both
           if A[x] != B[x]]
    if dis:
        print(f"\n{len(dis)} excerpt(s) to reconcile")
        for x, ao, bo in dis[:12]:
            text = (excerpts.get(x, {}).get("text") or "").strip()
            print(f"  {x}")
            if ao:
                print(f"    {a_name} only: {', '.join(ao)}")
            if bo:
                print(f"    {b_name} only: {', '.join(bo)}")
            if text:
                print(f'    "{text[:96]}{"..." if len(text) > 96 else ""}"')
        if len(dis) > 12:
            print(f"  ... and {len(dis) - 12} more")

    # valence, where both judged one
    vals = collections.defaultdict(dict)
    for c in codings:
        who = (c.get("coder") or "").strip() or "(unnamed)"
        if who in (a_name, b_name) and (c.get("valence") or "").strip():
            vals[(c["excerpt_id"], c["code_id"])][who] = c["valence"]
    pairs = [v for v in vals.values() if len(v) == 2]
    if pairs:
        same = sum(1 for v in pairs if v[a_name] == v[b_name])
        print(f"\nvalence: {same} of {len(pairs)} judged by both agree "
              f"({100*same/len(pairs):.0f}%)")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Check the corpus, and measure agreement between coders.")
    ap.add_argument("--data", required=True)
    ap.add_argument("--reliability", action="store_true",
                    help="compare two coders instead of auditing the corpus")
    ap.add_argument("--against", metavar="CODER",
                    help="with --reliability: which coder to compare against")
    a = ap.parse_args()
    root = os.path.abspath(a.data)
    if not os.path.isdir(root):
        raise SystemExit(f"no such project: {root}")
    if a.reliability:
        raise SystemExit(reliability(root, a.against))
    n = audit(root)
    if n:
        print(f"\n{n} problem(s) found. None of them stop the tool running, "
              f"which is why they are worth reading.")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
