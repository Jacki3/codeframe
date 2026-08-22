"""Draw a sample of the corpus and propose a starting codebook from it.

    python propose_codes.py --data ../myproject --lenses "Enjoyment,Place" --dry-run
    python propose_codes.py --data ../myproject --lenses "Enjoyment,Place" --sample 10
    python propose_codes.py --data ../myproject --lenses "..." --sample 10 --apply

READ THIS BEFORE USING IT

This is the one part of codeframe that undermines the rest, and it is included
because a blank codebook is a genuinely hard place to start, not because it is a
good idea to lean on.

    It sends participant speech. A sample of raw source text goes to a model -
    more of it than any other step here, and unlike valence.py it is not confined
    to passages you have already chosen. On a corpus you are answerable for,
    --dry-run first and read what comes out.

    It is expensive. Ten percent of a decent corpus is tens of thousands of words
    per run, and a codebook worth having takes several runs.

    It costs you the thing that makes an inductive codebook worth anything.
    A frame you built by reading is a frame you can defend line by line. A frame
    you accepted is one you will be asked to justify and will not be able to,
    because the reasoning happened somewhere you cannot see. Reviewers ask how
    codes were derived; "a model proposed them from a sample" is an answer that
    invites the next question.

    It anchors you. Reading a proposed code makes it much harder to notice the
    code you would have written instead. That effect is strongest at the start,
    which is exactly when you would reach for this.

Because of that last point, nothing here writes to codes.csv. Proposals land in
codebook/proposed_codes.csv with a `source` column marking them as machine-
proposed, and moving one into the codebook is a thing you do by hand, having read
the passages it came from. --apply only writes the proposals file.

The sample is drawn with a fixed seed and the ids are recorded, so the same
command twice gives the same sample and a methods section can say which passages
were involved.
"""
import argparse, collections, csv, io, json, os, random, re, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

csv.field_size_limit(10 ** 8)
FIELDS = ["code_id", "lens", "name", "definition", "valence", "include",
          "exclude", "anchor", "note", "source", "drawn_from"]


def read(root, *parts):
    p = os.path.join(root, *parts)
    if not os.path.exists(p):
        return []
    with io.open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def draw(sources, pct, n, seed):
    """A reproducible sample, proportional by kind and spread across participants.

    Two ways to get this wrong, and the second is not obvious. Taking N at random
    over-samples whoever talked most, so within a kind the draw goes round-robin
    by participant.

    But sampling round-robin ACROSS kinds is worse. Ten interviews and three
    hundred surveys are not equal populations, and giving each kind a turn takes
    every interview first - on this project a nominal 5% sample came out as 80%
    of the corpus by word count, because the interviews hold most of the words.
    Each kind is therefore sampled in proportion to its own size, and the word
    count is reported next to the source count so the difference is visible
    before anything is sent.
    """
    usable = [s for s in sources if len((s.get("text") or "").split()) >= 12]
    rng = random.Random(seed)

    by_kind = collections.defaultdict(lambda: collections.defaultdict(list))
    for s in usable:
        by_kind[s.get("kind", "")][s["pid"]].append(s)
    for kind in by_kind:
        for pid in by_kind[kind]:
            by_kind[kind][pid].sort(key=lambda s: s["source_id"])
            rng.shuffle(by_kind[kind][pid])

    picked = []
    for kind in sorted(by_kind):
        pool = by_kind[kind]
        in_kind = sum(len(v) for v in pool.values())
        if n:                       # an explicit count is shared out by size
            want = max(1, round(n * in_kind / len(usable)))
        else:
            want = max(1, round(in_kind * pct / 100)) if pct > 0 else 0
        want = min(want, in_kind)
        taken, exhausted = 0, False
        while taken < want and not exhausted:
            exhausted = True
            for pid in sorted(pool, key=str):
                if pool[pid] and taken < want:
                    picked.append(pool[pid].pop())
                    taken += 1
                    exhausted = False
    return picked


TASK = """You are reading a sample of material from a qualitative study and
proposing a STARTING codebook - candidate codes a researcher will read, argue
with, rewrite and mostly discard. You are not producing the codebook.

You are given passages and the lenses the researcher is working with. A lens is
the analytic question a code belongs to. Propose codes only under the lenses
given; if something important sits outside all of them, say so in "outside"
rather than inventing a lens.

What makes a code useful here:

  It names a thing people said, not a topic. "Learning was the reward" is a
  code; "learning" is a folder.
  It could be absent. A code that everything satisfies distinguishes nothing.
  Its boundary is stated. The include and exclude rules are what stop two coders
  drifting apart, and exclude is where the real work is - name the neighbouring
  code somebody would reach for instead.
  It is grounded. Quote the passage that made you propose it.

Propose between four and twelve codes per lens, fewer if the sample does not
support more. Do not pad. A code you are unsure of belongs in the list with the
doubt written into its note, not left out and not dressed up.

Ids are PREFIX-SOMETHING in capitals, where the prefix is a short abbreviation of
the lens, so a reader can tell at a glance which lens a code sits under.

Reply with JSON only:

{"codes": [{"code_id": "ENJ-EXAMPLE", "lens": "<one of the lenses given>",
            "name": "<a short phrase, sentence case>",
            "definition": "<one or two sentences: what the passage must be doing>",
            "include": "<phrases and situations that qualify>",
            "exclude": "<what to use instead, naming the other code where you can>",
            "evidence": "<the passage that prompted this, quoted>",
            "note": "<any doubt you have about it>"}],
 "outside": ["<anything striking that no lens covers>"],
 "sample_read": "<one sentence on what the sample seemed to be about>"}"""


def main():
    ap = argparse.ArgumentParser(
        description="Propose a starting codebook from a sample. Read the "
                    "docstring first.")
    ap.add_argument("--data", required=True)
    ap.add_argument("--lenses", required=True,
                    help="comma-separated, e.g. \"Enjoyment,Place,Perceptions\"")
    ap.add_argument("--sample", type=float, default=10.0,
                    help="percent of usable sources to read (default 10)")
    ap.add_argument("--n", type=int, help="a number of sources instead of a percent")
    ap.add_argument("--seed", type=int, default=1,
                    help="same seed, same sample - record it in your methods")
    ap.add_argument("--kind", help="only sample this source kind")
    ap.add_argument("--dry-run", action="store_true",
                    help="show the sample and the payload; send nothing")
    ap.add_argument("--apply", action="store_true",
                    help="write codebook/proposed_codes.csv")
    ap.add_argument("--model", default=None)
    a = ap.parse_args()

    root = os.path.abspath(a.data)
    sources = read(root, "sources.csv")
    if not sources:
        raise SystemExit(f"no sources.csv in {root}")
    if a.kind:
        sources = [s for s in sources if s.get("kind") == a.kind]
        if not sources:
            raise SystemExit(f"no sources of kind {a.kind!r}")
    lenses = [l.strip() for l in a.lenses.split(",") if l.strip()]
    if not lenses:
        raise SystemExit("give at least one lens")

    picked = draw(sources, a.sample, a.n, a.seed)
    words = sum(len(s["text"].split()) for s in picked)
    kinds = collections.Counter(s.get("kind", "") for s in picked)
    print(f"sample: {len(picked)} of {len(sources)} sources, {words:,} words, "
          f"{len({s['pid'] for s in picked})} participants, seed {a.seed}")
    print("  " + ", ".join(f"{k or '(no kind)'} {n}" for k, n in kinds.most_common()))
    print(f"  lenses: {', '.join(lenses)}")

    existing = read(root, "codebook", "codes.csv")
    if existing:
        print(f"\n  codes.csv already has {len(existing)} codes. Proposals go to "
              f"proposed_codes.csv\n  and are never merged in automatically.")

    payload = {"lenses": lenses,
               "passages": [{"id": s["source_id"], "kind": s.get("kind", ""),
                             "text": s["text"]} for s in picked]}
    if a.dry_run:
        print()
        print(json.dumps(payload, indent=1)[:5000])
        print(f"\n{len(picked)} passages, {words:,} words would be sent. "
              f"Nothing was sent.")
        return

    print(f"\n  This sends {words:,} words of participant speech.")
    from model import current
    from review import ask
    model = a.model or current()
    print(f"  reading the sample with {model}")
    reply, env = ask(payload, model=model, task=TASK, timeout=900)

    codes = reply.get("codes") or []
    if not codes:
        raise SystemExit("no codes came back")
    ids = {s["source_id"] for s in picked}
    rows = []
    for c in codes:
        cid = re.sub(r"[^A-Z0-9-]", "", str(c.get("code_id", "")).upper())
        lens = str(c.get("lens", "")).strip()
        if not cid or lens not in lenses:
            continue
        rows.append({
            "code_id": cid, "lens": lens, "name": str(c.get("name", ""))[:80],
            "definition": str(c.get("definition", ""))[:400],
            "valence": "", "include": str(c.get("include", ""))[:300],
            "exclude": str(c.get("exclude", ""))[:300], "anchor": "",
            "note": ("PROPOSED, not read by a human. "
                     + str(c.get("note", ""))[:200]).strip(),
            "source": "machine-proposed",
            "drawn_from": f"seed {a.seed}, {len(picked)} sources",
        })

    by_lens = collections.Counter(r["lens"] for r in rows)
    print(f"\n{len(rows)} candidate code(s) proposed")
    for l in lenses:
        print(f"  {l:<20} {by_lens.get(l, 0)}")
    if reply.get("sample_read"):
        print(f"\n  the sample seemed to be about: {reply['sample_read'][:160]}")
    for o in (reply.get("outside") or [])[:4]:
        print(f"  outside your lenses: {str(o)[:120]}")
    cost = env.get("total_cost_usd")
    if cost:
        print(f"  cost: ${cost:.2f}")

    if not a.apply:
        print("\nreport only - nothing written. Re-run with --apply to save them.")
        return

    p = os.path.join(root, "codebook", "proposed_codes.csv")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in FIELDS} for r in rows])
    os.replace(tmp, p)
    print(f"\nwrote {p}")
    print("  Nothing was added to codes.csv, and nothing will be.")
    print("  Read the passages these came from, keep the few that survive that,")
    print("  rewrite them in your own words, and move those into codes.csv by hand.")
    print("  A code you have not argued with is one you cannot defend.")


if __name__ == "__main__":
    main()
