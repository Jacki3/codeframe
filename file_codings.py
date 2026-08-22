"""Take a spreadsheet of quotes and file them against the source documents.

You read the transcripts and survey answers, copy whatever passages matter into a
spreadsheet, and write the code and any note beside each one. This finds where
each quote came from and attaches the provenance - PID, game, tool, design type,
survey question or interview timestamp - so you never have to record any of that
by hand.

    python file_codings.py --data ../myproject --sheet coding.csv
    python file_codings.py --data ../myproject --sheet coding.csv --apply

Without --apply it reports what it would do and writes nothing.

THE SHEET
    quote     required. Paste of the passage, as you copied it.
    code      required. One code, or several separated by ; or |
    valence   optional. pos / neg / mixed / neutral. Left blank it stays
              blank - "neutral" is a claim that the participant expressed no
              attitude, which is not the same as not having judged one yet
    note      optional. Free text, kept with the coding.
    pid,game  optional. Only needed to disambiguate a quote that appears in more
              than one document - the report tells you when that happens.

Column names are matched loosely, so "Quote", "CODE", "Notes" all work.

MATCHING
    Quotes are matched on normalised text: smart quotes and dashes folded to
    plain ones, all whitespace collapsed, case ignored. That absorbs almost
    everything copy-and-paste does to a passage.

    An exact normalised match in exactly one document resolves. Anything else -
    no match, or a match in several documents - is reported rather than guessed
    at, with the closest candidate and a similarity score so you can see what
    went wrong. Nothing ambiguous is ever filed silently.
"""
import argparse, collections, csv, difflib, io, os, re, sys, unicodedata, json

# Quotes carry curly apostrophes and dashes; a cp1252 console mangles them on the
# way to the screen even though the files are fine.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

VALENCE = {"pos", "neg", "mixed", "neutral"}
FUZZY_FLOOR = 0.88          # below this, do not even offer it as a candidate

# columns we will accept for each field, lowercased and stripped of punctuation
ALIASES = {
    "quote": {"quote", "quotation", "text", "excerpt", "passage", "extract", "data"},
    "code": {"code", "codes", "coding", "label"},
    "valence": {"valence", "direction", "polarity", "sentiment"},
    "note": {"note", "notes", "comment", "comments", "memo", "remark", "remarks"},
    "pid": {"pid", "participant", "participantid", "id"},
    "game": {"game", "title"},
}


def norm_key(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def normalise(text):
    """Fold a passage to a comparable form, and map each character back.

    Returns (normalised, index) where index[i] is the offset in the original of
    normalised character i - which is what lets an excerpt record real offsets
    into the source rather than into some cleaned-up copy of it.
    """
    out, idx, prev_space = [], [], True
    for i, ch in enumerate(unicodedata.normalize("NFKC", text)):
        if ch in "‘’ʼ′":
            ch = "'"
        elif ch in "“”″":
            ch = '"'
        elif ch in "‐‑‒–—―":
            ch = "-"
        if ch.isspace():
            if prev_space:
                continue
            ch, prev_space = " ", True
        else:
            prev_space = False
        out.append(ch.lower())
        idx.append(i)
    while out and out[-1] == " ":
        out.pop(); idx.pop()
    return "".join(out), idx


def read_text(path):
    """Decode a spreadsheet however it happened to be saved.

    Excel's plain "Save as CSV" writes the system ANSI codepage, not UTF-8, so a
    curly apostrophe arrives as a lone 0x92 byte and strict UTF-8 decoding dies
    on it. Try the likely encodings in order; only if all of them fail do we fall
    back to lossy decoding, because one mangled character should not stop the
    other two hundred rows from filing.
    """
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8 with replacements"


def read_sheet(path):
    """Read the coding spreadsheet, mapping whatever column names it uses."""
    text, enc = read_text(path)
    if enc not in ("utf-8-sig", "utf-8"):
        print(f"note: {os.path.basename(path)} is {enc}, not UTF-8 - read anyway.")
        print("      Excel's plain 'Save as CSV' does this; 'CSV UTF-8' avoids it.\n")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.DictReader(io.StringIO(text, newline=""), dialect=dialect))
    if not rows:
        raise SystemExit(f"{path} has no rows")

    found, unknown = {}, []
    for col in rows[0].keys():
        k = norm_key(col)
        for field, names in ALIASES.items():
            if k in names and field not in found:
                found[field] = col
                break
        else:
            unknown.append(col)
    for req in ("quote", "code"):
        if req not in found:
            raise SystemExit(
                f"{path} needs a '{req}' column. Found: {', '.join(rows[0].keys())}")
    return rows, found, unknown


def _read(path):
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def lens_for(cid, codes):
    """The lens the other codes sharing this id's prefix use, if they agree enough."""
    prefix = str(cid).split("-")[0].upper()
    seen = collections.Counter(
        (c.get("lens") or "").strip() for c in codes
        if str(c.get("code_id", "")).split("-")[0].upper() == prefix
        and (c.get("lens") or "").strip())
    return seen.most_common(1)[0][0] if seen else ""


def main():
    ap = argparse.ArgumentParser(description="File coded quotes against source documents.")
    ap.add_argument("--data", required=True, help="project directory holding sources.csv")
    ap.add_argument("--sheet", required=True, help="your coding spreadsheet (csv)")
    ap.add_argument("--coder", default="researcher")
    ap.add_argument("--apply", action="store_true", help="write; otherwise report only")
    ap.add_argument("--allow-new-codes", action="store_true",
                    help="accept codes not yet in codes.csv, and add them as stubs")
    a = ap.parse_args()

    root = os.path.abspath(a.data)
    _meta_p = os.path.join(root, "frame.json")
    _meta = (json.load(open(_meta_p, encoding="utf-8"))
             if os.path.exists(_meta_p) else {})
    _unit = _meta.get("unit_label") or "unit"
    _units = _unit + ("s" if not _unit.endswith("s") else "")
    from project import alias_unit
    sources = alias_unit(list(csv.DictReader(
        open(os.path.join(root, "sources.csv"), encoding="utf-8"))))
    if not sources:
        raise SystemExit(f"no sources.csv in {root}")
    frame_path = os.path.join(root, "frame.csv")
    frame = {}
    if os.path.exists(frame_path):
        for r in alias_unit(list(csv.DictReader(open(frame_path, encoding="utf-8")))):
            frame[(r["pid"], r["game"])] = r
    # a sheet coded before a merge still names the old id; the register says
    # where it went, so map it forward rather than reporting an unknown code
    from retire import load_register
    _reg, _ = load_register(root)
    codes_path = os.path.join(root, "codebook", "codes.csv")
    codes = list(csv.DictReader(open(codes_path, encoding="utf-8"))) \
        if os.path.exists(codes_path) else []
    known = {c["code_id"].strip().upper() for c in codes}

    # normalise every source once
    prepared = []
    for s in sources:
        n, idx = normalise(s["text"])
        prepared.append((s, n, idx))

    rows, col, unknown_cols = read_sheet(a.sheet)
    if unknown_cols:
        print(f"note: ignoring extra column(s): {', '.join(unknown_cols)}\n")

    excerpts, codings, problems = {}, [], []
    new_codes = set()

    for n_row, r in enumerate(rows, 2):          # 2 = first row after the header
        quote = (r.get(col["quote"]) or "").strip()
        raw_codes = (r.get(col["code"]) or "").strip()
        if not quote and not raw_codes:
            continue
        if not quote or not raw_codes:
            problems.append((n_row, quote[:60], "row is missing a quote or a code", "", ""))
            continue

        cids = [c.strip().upper() for c in re.split(r"[;|,]", raw_codes) if c.strip()]
        # Map a merged code forward BEFORE checking it against the codebook. A
        # sheet coded last month names the id that existed last month, and
        # rejecting it as unknown would make every merge invalidate work in
        # progress.
        cids = [_reg.get(c) or c for c in cids]
        bad = [c for c in cids if c not in known]
        if bad and not a.allow_new_codes:
            problems.append((n_row, quote[:60],
                             f"code not in codebook: {', '.join(bad)}", "", ""))
            continue
        new_codes.update(bad)

        # Blank means blank. Defaulting it to "neutral" silently converts every
        # coding you had not judged into a positive claim that the participant
        # expressed no attitude, and the two are indistinguishable afterwards -
        # which quietly corrupts any favourable/unfavourable split built on it.
        val = (r.get(col.get("valence", "")) or "").strip().lower()
        val = {"positive": "pos", "negative": "neg", "p": "pos", "n": "neg",
               "m": "mixed", "x": "neutral"}.get(val, val)
        if val and val not in VALENCE:
            problems.append((n_row, quote[:60], f"unknown valence '{val}'", "", ""))
            continue
        note = (r.get(col.get("note", "")) or "").strip()

        # optional hints, used only to break a tie
        hint_pid = (r.get(col.get("pid", "")) or "").strip().lstrip("PIDpid ")
        hint_game = (r.get(col.get("game", "")) or "").strip().lower()

        nq, _ = normalise(quote)
        if len(nq) < 8:
            problems.append((n_row, quote[:60], "quote too short to place reliably", "", ""))
            continue

        hits = []
        for s, n, idx in prepared:
            pos = n.find(nq)
            while pos != -1:
                hits.append((s, idx[pos], idx[pos + len(nq) - 1] + 1))
                pos = n.find(nq, pos + 1)

        if hint_pid or hint_game:
            narrowed = [h for h in hits
                        if (not hint_pid or h[0]["pid"] == hint_pid)
                        and (not hint_game or hint_game in h[0]["game"].lower())]
            if narrowed:
                hits = narrowed

        if len(hits) != 1:
            if not hits:
                best, score = None, 0.0
                for s, n, _ in prepared:
                    m = difflib.SequenceMatcher(None, nq, n).find_longest_match(0, len(nq), 0, len(n))
                    r2 = difflib.SequenceMatcher(None, nq, n[m.b:m.b + len(nq)]).ratio()
                    if r2 > score:
                        best, score = s, r2
                reason = ("no match found" if score < FUZZY_FLOOR
                          else "no exact match; closest shown - check for a typo or an edit")
                problems.append((n_row, quote[:60], reason,
                                 best["source_id"] if best else "", f"{score:.2f}"))
            else:
                where = ", ".join(sorted({f"PID{h[0]['pid']}/{h[0]['game']}" for h in hits}))
                problems.append((n_row, quote[:60],
                                 f"appears in {len(hits)} documents - add a pid or {_unit} "
                                 f"column to disambiguate ({where})", "", ""))
            continue

        s, start, end = hits[0]
        xid = f"X-{s['source_id']}-{start}-{end}"
        excerpts[xid] = {
            "excerpt_id": xid, "source_id": s["source_id"], "pid": s["pid"],
            "unit": s["game"], "game": s["game"],
            "kind": s["kind"], "label": s["label"],
            "start": start, "end": end, "text": s["text"][start:end],
        }
        for cid in cids:
            codings.append({"excerpt_id": xid, "code_id": cid, "valence": val,
                            "coder": a.coder, "note": note, "sheet_row": n_row})

    # ---- report ----
    # frame.csv is the denominator when it exists. Deriving it from sources
    # instead counts an interview - which covers a whole session and so carries
    # no single unit - as a unit of its own, and inflates every rate computed
    # against it.
    plays = set(frame) or {(s["pid"], s["game"]) for s in sources}
    covered = {(x["pid"], x["game"]) for x in excerpts.values()} & plays
    # An interview covers a whole session, so it carries no single unit and its
    # excerpts belong to no one unit of the study. They are still evidence about
    # participant, so they are counted separately rather than quietly dropped.
    loose = {x["pid"] for x in excerpts.values() if (x["pid"], x["game"]) not in plays}
    print(f"sheet    : {len(rows)} rows from {os.path.basename(a.sheet)}")
    print(f"filed    : {len(excerpts)} excerpts, {len(codings)} codings")
    unset = sum(1 for c in codings if not c["valence"])
    if unset:
        print(f"valence  : {len(codings) - unset} judged, {unset} left blank")
    print(f"coverage : {len(covered)} of {len(plays)} {_units} touched")
    if loose:
        print(f"           plus {len(loose)} participant(s) coded from sources "
              f"with no unit, e.g. interviews")
    if new_codes:
        print(f"new codes: {', '.join(sorted(new_codes))}")
    print(f"problems : {len(problems)}")
    for p in problems[:15]:
        print(f"  row {p[0]:>4}  {p[2]}")
        print(f"           \"{p[1]}…\"" + (f"   closest {p[3]} ({p[4]})" if p[3] else ""))
    if len(problems) > 15:
        print(f"  ... and {len(problems) - 15} more, all listed in unresolved.csv")

    if not a.apply:
        print("\nreport only - nothing written. Re-run with --apply when the problems are cleared.")
        return

    d = os.path.join(root, "data")
    os.makedirs(d, exist_ok=True)

    def write(path, fields, rowset):
        tmp = path + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows([{k: r.get(k, "") for k in fields} for r in rowset])
        os.replace(tmp, path)

    # Filing a sheet replaces THIS coder's codings and leaves everyone else's
    # alone. Rewriting the whole file made a second coder wipe the first, which
    # is silent, total, and exactly what reliability work needs not to happen.
    kept = [r for r in _read(os.path.join(d, "codings.csv"))
            if (r.get("coder") or "").strip() != a.coder]
    if kept:
        others = sorted({(r.get("coder") or "(unnamed)") for r in kept})
        print(f"\nkept {len(kept)} coding(s) by {', '.join(others)}")

    # an excerpt is a passage, not a judgement, so excerpts are merged rather
    # than replaced - two coders marking the same span share one excerpt
    prior = {x["excerpt_id"]: x for x in _read(os.path.join(d, "excerpts.csv"))}
    still = {c["excerpt_id"] for c in kept}
    merged = {k: v for k, v in prior.items() if k in still}
    merged.update(excerpts)

    write(os.path.join(d, "excerpts.csv"),
          ["excerpt_id", "source_id", "pid", "unit", "kind", "label",
           "start", "end", "text"],
          sorted(merged.values(), key=lambda x: (x["source_id"], int(x["start"]))))
    write(os.path.join(d, "codings.csv"),
          ["excerpt_id", "code_id", "valence", "coder", "note", "sheet_row"],
          kept + codings)
    write(os.path.join(d, "unresolved.csv"),
          ["sheet_row", "quote", "reason", "closest_source", "similarity"],
          [{"sheet_row": p[0], "quote": p[1], "reason": p[2],
            "closest_source": p[3], "similarity": p[4]} for p in problems])

    if new_codes and a.allow_new_codes:
        from project import CODE_FIELDS
        fields = list(codes[0].keys()) if codes else list(CODE_FIELDS)
        for cid in sorted(new_codes):
            stub = {k: "" for k in fields}
            stub["code_id"] = cid
            stub["name"] = cid.replace("-", " ").title()
            # A code id is conventionally PREFIX-SOMETHING, and the prefix is
            # almost always the lens. Inheriting it means a stub does not land in
            # "Uncategorised" on the discussion page, which is where a lens-less
            # code goes to be forgotten.
            stub["lens"] = lens_for(cid, codes)
            stub["note"] = "stub created by file_codings.py - needs a definition"
            codes.append(stub)
        write(codes_path, fields, codes)
        print(f"\nadded {len(new_codes)} code stub(s) to codebook/codes.csv - "
              f"they need definitions")
        guessed = [c for c in codes if c["code_id"] in new_codes and c.get("lens")]
        if guessed:
            print(f"  lens guessed from the id prefix for {len(guessed)}: "
                  + ", ".join(f"{c['code_id']} -> {c['lens']}" for c in guessed[:4]))

    # A code with no lens is invisible to the discussion page, which groups by it.
    no_lens = sorted(c["code_id"] for c in codes if not (c.get("lens") or "").strip())
    if no_lens:
        print(f"\n{len(no_lens)} code(s) have no lens and will group under "
              f"\"Uncategorised\" in the discussion:")
        print("  " + ", ".join(no_lens[:8]) + (" ..." if len(no_lens) > 8 else ""))

    print(f"\nwrote data/excerpts.csv, data/codings.csv, data/unresolved.csv")


if __name__ == "__main__":
    main()
