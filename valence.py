"""Fill in the valence of codings that have none.

    python valence.py --data ../myproject --dry-run   # what would be sent
    python valence.py --data ../myproject             # propose
    python valence.py --data ../myproject --apply     # write the settled ones

Two judgements, deliberately kept apart until they can be compared.

    the code    codes.csv may declare a valence. Most codes carry their own
                polarity - a frustration code is negative wherever it lands -
                and that is a property of the code you wrote, so establishing
                it needs no model and sends nothing anywhere.

    the model   reads the excerpt and judges what was actually said.

Where the two agree, the valence is settled and --apply writes it. Where they
disagree, neither wins: the excerpt goes to a review list for you, because a
passage whose tone departs from what its code implies is usually the one worth
reading. Where only one of them has an opinion, that one is used.

A valence you typed yourself is never touched, proposed against, or sent.

WHAT LEAVES THE MACHINE

Unlike review.py, this sends verbatim participant speech - the excerpt text and
your note on it. That is the most sensitive material in the project, so:

  - only excerpts with no valence are sent, never the whole corpus
  - no pid, no source id, no filename, no category goes with them; the model
    sees a passage and a code definition and nothing that ties either to a person
  - --dry-run prints the exact payload and sends nothing
  - nothing is written without --apply

If that trade is not one you want to make, declare valences in codes.csv and run
with --offline. The code-level pass needs no network at all.
"""
import argparse, collections, csv, json, os, sys

# Quotes carry curly apostrophes and dashes; a cp1252 console mangles them on the
# way to the screen even though the files are fine.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

VALENCE = ("pos", "neg", "mixed", "neutral")
PROPOSAL_FIELDS = ["excerpt_id", "code_id", "code_valence", "model_valence",
                   "agreement", "settled", "why", "text"]

TASK = """You are judging the valence of coded passages from a qualitative
research study - how the speaker felt about the thing the code names, as
expressed in the passage itself.

For each item you are given the passage, the code applied to it, and that code's
definition. Judge the passage, not the code: the code says what the passage is
about, and your job is to say what attitude the speaker took to it.

Use exactly one of:

  pos      the speaker is favourable about it
  neg      the speaker is unfavourable about it
  mixed    the speaker expresses both, or is favourable with a real reservation
  neutral  the speaker describes it without evaluating it

Judge only from what is in the passage. Do not infer an attitude from the code's
name - a code about frustration can appear in a passage where someone says they
did not find it frustrating. "mixed" is for genuine two-sidedness, not for
uncertainty: if the passage does not evaluate the thing at all, that is neutral.
If the passage is too short or too fragmentary to tell, say neutral and say so in
the reason.

Reply with JSON only, no prose around it:

{"judgements": [{"id": "<the id given>", "valence": "<pos|neg|mixed|neutral>",
                 "why": "<one short sentence, quoting the words that decided it>"}]}

Return one entry for every id you were given, in the same order."""


def read(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write(path, fields, rows):
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in fields} for r in rows])
    os.replace(tmp, path)


def load(root):
    codings = read(os.path.join(root, "data", "codings.csv"))
    excerpts = {x["excerpt_id"]: x for x in read(os.path.join(root, "data", "excerpts.csv"))}
    codes = {c["code_id"]: c for c in read(os.path.join(root, "codebook", "codes.csv"))}
    if not codings:
        raise SystemExit(f"no codings in {root} - file some first with file_codings.py")
    return codings, excerpts, codes


def targets(codings, excerpts, codes):
    """Codings with no valence, paired with the text and the code's own view."""
    out = []
    for i, c in enumerate(codings):
        if (c.get("valence") or "").strip():
            continue                       # judged by hand; leave it alone
        x = excerpts.get(c["excerpt_id"])
        if not x or not (x.get("text") or "").strip():
            continue
        code = codes.get(c["code_id"], {})
        out.append({
            "row": i, "excerpt_id": c["excerpt_id"], "code_id": c["code_id"],
            "code_valence": (code.get("valence") or "").strip().lower(),
            "name": code.get("name", ""), "definition": code.get("definition", ""),
            "text": x["text"].strip(), "note": (c.get("note") or "").strip(),
        })
    return out


def payload_for(batch):
    """What is sent. Passage, code, definition - and nothing that identifies anyone.

    The id is the position in the batch, not the excerpt id. An excerpt id is
    built from its source id, which carries the participant number, so sending it
    would attach a pid to every passage for no benefit - the mapping back is
    local and this side already knows it.
    """
    return [{"id": f"i{n}", "code": t["code_id"], "code_name": t["name"],
             "code_definition": t["definition"], "passage": t["text"],
             **({"coder_note": t["note"]} if t["note"] else {})}
            for n, t in enumerate(batch)]


def judge(batch, model, timeout):
    from review import ask
    reply, env = ask({"items": payload_for(batch)}, model=model, timeout=timeout,
                     task=TASK)
    # Keyed on excerpt AND code: one passage can carry several codes, and they can
    # honestly differ in valence - someone can be glad they learned something and
    # annoyed at how long it took.
    out = {}
    for j in reply.get("judgements") or []:
        v = str(j.get("valence", "")).strip().lower()
        n = str(j.get("id", ""))[1:]
        if v in VALENCE and n.isdigit() and int(n) < len(batch):
            t = batch[int(n)]
            out[(t["excerpt_id"], t["code_id"])] = (v, str(j.get("why", ""))[:200])
    return out, env.get("total_cost_usd") or 0


def cached(root):
    """Model judgements already made, so a re-run neither re-sends nor forgets.

    Re-sending an excerpt costs money and exposes the same speech twice for an
    answer already given. It also matters that --offline does not wipe what a
    previous run learned: that file is the record of where the code and the model
    disagreed, which is the part worth keeping.
    """
    out = {}
    for r in read(os.path.join(root, "data", "valence_proposals.csv")):
        if r.get("model_valence"):
            out[(r["excerpt_id"], r["code_id"])] = (r["model_valence"], r.get("why", ""))
    return out


def settle(code_v, model_v):
    """Which valence stands, and what to call the relationship between the two."""
    if code_v and model_v:
        if code_v == model_v:
            return model_v, "agree"
        return "", "disagree"             # neither wins; a human decides
    if model_v:
        return model_v, "model only"
    if code_v:
        return code_v, "code only"
    return "", "no opinion"


def main():
    ap = argparse.ArgumentParser(description="Propose a valence for unjudged codings.")
    ap.add_argument("--data", required=True, help="project directory")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--batch", type=int, default=25, help="excerpts per request")
    ap.add_argument("--offline", action="store_true",
                    help="use codes.csv only; send nothing anywhere")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the payload and send nothing")
    ap.add_argument("--apply", action="store_true", help="write; otherwise report only")
    a = ap.parse_args()

    root = os.path.abspath(a.data)
    codings, excerpts, codes = load(root)
    todo = targets(codings, excerpts, codes)
    judged = sum(1 for c in codings if (c.get("valence") or "").strip())

    print(f"codings  : {len(codings)} total, {judged} judged by hand, {len(todo)} without a valence")
    if not todo:
        print("nothing to do.")
        return
    missing = sorted({t["code_id"] for t in todo if not t["code_valence"]})
    print(f"codes.csv: {len(todo) - sum(1 for t in todo if not t['code_valence'])} "
          f"of those have a code-level valence to compare against")
    if missing:
        print(f"           no valence declared for: {', '.join(missing[:8])}"
              + (" ..." if len(missing) > 8 else ""))

    model_v, cost = cached(root), 0
    fresh = [t for t in todo if (t["excerpt_id"], t["code_id"]) not in model_v]

    if a.dry_run:
        print()
        print(json.dumps({"items": payload_for(fresh[:a.batch])}, indent=1)[:6000])
        n = len(fresh)
        print(f"\n{n} excerpt(s) would be sent in "
              f"{(n + a.batch - 1) // a.batch} request(s)"
              + (f"; {len(todo) - n} already judged and would not be re-sent" if n < len(todo) else "")
              + ". Nothing was sent.")
        return

    if model_v:
        print(f"cached   : {len(todo) - len(fresh)} already judged by the model, "
              f"not re-sent")
    if a.offline:
        if fresh:
            print(f"\noffline - {len(fresh)} excerpt(s) not sent; "
                  f"using codes.csv alone for those")
    elif fresh:
        print(f"\nsending {len(fresh)} excerpt(s) to {a.model} "
              f"in batches of {a.batch}")
        for i in range(0, len(fresh), a.batch):
            batch = fresh[i:i + a.batch]
            got, c = judge(batch, a.model, 600)
            model_v.update(got)
            cost += c
            print(f"  {i + len(batch):>4} / {len(fresh)}   "
                  f"({len(got)}/{len(batch)} judged)")

    rows, counts = [], collections.Counter()
    for t in todo:
        mv, why = model_v.get((t["excerpt_id"], t["code_id"]), ("", ""))
        val, agreement = settle(t["code_valence"], mv)
        counts[agreement] += 1
        rows.append({"excerpt_id": t["excerpt_id"], "code_id": t["code_id"],
                     "code_valence": t["code_valence"], "model_valence": mv,
                     "agreement": agreement, "settled": val, "why": why,
                     "text": t["text"][:300]})

    p_out = os.path.join(root, "data", "valence_proposals.csv")
    write(p_out, PROPOSAL_FIELDS, rows)

    print()
    for k in ("agree", "model only", "code only", "disagree", "no opinion"):
        if counts[k]:
            print(f"  {k:<12} {counts[k]}")
    if counts["agree"] and counts["disagree"] + counts["agree"]:
        rate = 100 * counts["agree"] / (counts["agree"] + counts["disagree"])
        print(f"\n  agreement where both had a view: {rate:.0f}% "
              f"({counts['agree']} of {counts['agree'] + counts['disagree']})")
    if cost:
        print(f"  cost: ${cost:.2f}")

    if counts["disagree"]:
        print(f"\n{counts['disagree']} disagreement(s) - these are left blank for you:")
        for r in rows:
            if r["agreement"] == "disagree":
                print(f"  {r['excerpt_id']}  {r['code_id']}: "
                      f"code says {r['code_valence']}, model says {r['model_valence']}")
                print(f"    {r['why']}")
                print(f"    \"{r['text'][:110]}...\"")

    settled = [r for r in rows if r["settled"]]
    if not a.apply:
        print(f"\nwrote {p_out}")
        print(f"report only - {len(settled)} valence(s) would be written. "
              f"Re-run with --apply.")
        return

    by_x = {}
    for r in rows:
        if r["settled"]:
            by_x.setdefault(r["excerpt_id"], {})[r["code_id"]] = r["settled"]
    n = 0
    for c in codings:
        if (c.get("valence") or "").strip():
            continue
        v = by_x.get(c["excerpt_id"], {}).get(c["code_id"])
        if v:
            c["valence"] = v
            n += 1
    fields = list(codings[0].keys())
    write(os.path.join(root, "data", "codings.csv"), fields, codings)
    print(f"\nwrote {p_out}")
    print(f"wrote {len(codings)} codings, {n} valence(s) filled in")
    if counts["disagree"]:
        print(f"{counts['disagree']} left blank pending your decision - "
              f"edit codings.csv, or set the code's valence in codes.csv and re-run.")


if __name__ == "__main__":
    main()
