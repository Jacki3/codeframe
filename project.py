"""Project state: source documents in, excerpts and codings out.

A project directory holds four files:

    sources.csv          the raw material. Imported once, never edited here.
    codebook/codes.csv   the frame. Starts empty and grows as you code.
    data/excerpts.csv    passages you have selected: source + character range
    data/codings.csv     which code sits on which excerpt

Nothing is segmented in advance. Selecting a passage is what creates an excerpt,
so the corpus of coded material and the codebook grow together.

The denominator for any rate is the PARTICIPANT FRAME in frame.csv - one row per
(pid, unit) - not the number of excerpts. Those rows exist whether or not anyone
has coded a word, which is what lets prevalence stay meaningful while segmentation
stays emergent. Sources that belong to no single unit, such as an interview
covering a whole session, are read and coded like any other but do not add rows
to the frame.
"""
import csv, json, os, re

VALENCE = ("pos", "neg", "mixed", "neutral")
CODE_FIELDS = ["code_id", "lens", "name", "definition", "valence",
               "include", "exclude", "note"]
EXCERPT_FIELDS = ["excerpt_id", "source_id", "start", "end", "text"]
CODING_FIELDS = ["excerpt_id", "code_id", "valence", "coder", "note"]


def _read(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def alias_unit(rows):
    """Let 'unit' and 'game' name the same column.

    setup_project.py calls it unit, because what a response is about is not
    always a game - it may be a condition, a session, a site, a visit. Older
    projects and hand-written adapters call the same column game. Renaming either
    breaks the other, so both names are put on every row and a project from either
    route can be coded by the same tools. What the unit is CALLED on screen comes
    from unit_label in frame.json, not from this alias.
    """
    for r in rows:
        if not r.get("unit"):
            r["unit"] = r.get("game", "")
        if not r.get("game"):
            r["game"] = r.get("unit", "")
    return rows


def _write(path, fields, rows):
    """Atomic: a crash mid-write leaves the previous file intact."""
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in fields} for r in rows])
    os.replace(tmp, path)


class Project:
    def __init__(self, root, coder="researcher"):
        self.root = os.path.abspath(root)
        self.coder = coder
        self.p_sources = os.path.join(self.root, "sources.csv")
        self.p_codes = os.path.join(self.root, "codebook", "codes.csv")
        self.p_excerpts = os.path.join(self.root, "data", "excerpts.csv")
        self.p_codings = os.path.join(self.root, "data", "codings.csv")
        self.reload()

    def reload(self):
        self.frame = {(r["pid"], r["game"]): r
                      for r in alias_unit(_read(os.path.join(self.root, "frame.csv")))}
        self.sources = alias_unit(_read(self.p_sources))
        if not self.sources:
            raise SystemExit(
                f"no sources.csv in {self.root}\n"
                "Build a project first:  python setup_project.py --to <dir> --apply")
        self.codes = _read(self.p_codes)
        self.excerpts = _read(self.p_excerpts)
        self.codings = _read(self.p_codings)
        self._by_source = {s["source_id"]: s for s in self.sources}

        # Which frame columns to carry into the browser. A generic project has no
        # idea what they will be called, and it may hold eighty numeric measures
        # that would swamp the payload without being any use to a coder. Anything
        # that behaves like a category is a facet; the rest stays in frame.csv
        # until the findings need it.
        seen = {}
        for r in self.frame.values():
            for k, v in r.items():
                if k not in ("pid", "unit", "game"):
                    seen.setdefault(k, set()).add(v)
        # frame.json says which columns are categories, because the setup step
        # knew. "facets" is the editable preference: drop a column from that list
        # to take its dropdown out of the rail without touching the data.
        meta = {}
        p_meta = os.path.join(self.root, "frame.json")
        if os.path.exists(p_meta):
            with open(p_meta, encoding="utf-8") as f:
                meta = json.load(f)
        self.unit = meta.get("unit_label") or "unit"
        self.units = self.unit + ("s" if not self.unit.endswith("s") else "")
        declared = meta.get("facets") or meta.get("categories")
        if declared:
            self.facets = [k for k in declared if k in seen]
            return

        cands = [(k, vals) for k, vals in seen.items() if 1 < len(vals) <= 12]
        # A rating scale has as few distinct values as a category does, so the
        # count cannot separate them - a battery of eighty 0-4 items would fill
        # this list and push the real categories out. What separates them is that
        # a category is words and a scale is numbers, so words come first.
        def numeric(vals):
            return all(re.fullmatch(r"-?\d+(\.\d+)?", (v or "0").strip())
                       for v in vals)
        cands.sort(key=lambda kv: numeric(kv[1]))
        self.facets = [k for k, _ in cands[:8]]

    # ---- codes ----------------------------------------------------------

    def add_code(self, f):
        cid = (f.get("code_id") or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{2,5}-[A-Z0-9-]+", cid):
            raise ValueError("code id should look like ENJ-SOMETHING")
        if any(c["code_id"] == cid for c in self.codes):
            raise ValueError(f"{cid} already exists")
        for k in ("lens", "name"):
            if not (f.get(k) or "").strip():
                raise ValueError(f"{k} is required")
        row = {k: (f.get(k) or "").strip() for k in CODE_FIELDS}
        row["code_id"] = cid
        self.codes.append(row)
        _write(self.p_codes, CODE_FIELDS, self.codes)
        return row

    def update_code(self, cid, f):
        for c in self.codes:
            if c["code_id"] == cid:
                for k in CODE_FIELDS[1:]:
                    if k in f:
                        c[k] = (f.get(k) or "").strip()
                _write(self.p_codes, CODE_FIELDS, self.codes)
                return c
        raise ValueError(f"unknown code {cid}")

    # ---- excerpts and codings -------------------------------------------

    def save_excerpt(self, source_id, start, end, codes, note):
        """Create or update one excerpt and the codes on it.

        The id is derived from the source and the character range, so selecting
        the same passage twice updates it rather than duplicating it.
        """
        src = self._by_source.get(source_id)
        if not src:
            raise ValueError(f"unknown source {source_id}")
        start, end = int(start), int(end)
        if not (0 <= start < end <= len(src["text"])):
            raise ValueError("selection is outside the document")
        known = {c["code_id"] for c in self.codes}
        for cid, v in codes:
            if cid not in known:
                raise ValueError(f"unknown code {cid}")
            # "" is allowed and means not judged yet. Forcing a choice here would
            # make the first option in the list the default, which is how a
            # coding acquires an attitude nobody assigned to it.
            if v and v not in VALENCE:
                raise ValueError(f"bad valence {v}")

        xid = f"X-{source_id}-{start}-{end}"
        text = src["text"][start:end]
        self.excerpts = [x for x in self.excerpts if x["excerpt_id"] != xid]
        self.excerpts.append({"excerpt_id": xid, "source_id": source_id,
                              "start": str(start), "end": str(end), "text": text})
        self.excerpts.sort(key=lambda x: (x["source_id"], int(x["start"])))

        self.codings = [c for c in self.codings if c["excerpt_id"] != xid]
        for cid, v in codes:
            self.codings.append({"excerpt_id": xid, "code_id": cid, "valence": v,
                                 "coder": self.coder, "note": note.strip()})
        self._flush()
        return xid

    def delete_excerpt(self, xid):
        self.excerpts = [x for x in self.excerpts if x["excerpt_id"] != xid]
        self.codings = [c for c in self.codings if c["excerpt_id"] != xid]
        self._flush()

    def _flush(self):
        _write(self.p_excerpts, EXCERPT_FIELDS, self.excerpts)
        _write(self.p_codings, CODING_FIELDS, self.codings)

    # ---- payload --------------------------------------------------------

    def _facets_for(self, s):
        """Facet values for one source document.

        A source with no unit - an interview covering a whole session - matches
        no single frame row, and would otherwise come back blank on every facet
        and disappear the moment any dropdown is set. Its participant-level
        attributes are still knowable: take whatever that participant's rows
        agree on. The facets that vary by unit stay blank, because for a source
        spanning two games they genuinely have no single answer.
        """
        row = self.frame.get((s["pid"], s["game"]))
        if row is not None:
            return {k: row.get(k, "") for k in self.facets}
        rows = [r for (pid, _), r in self.frame.items() if pid == s["pid"]]
        out = {}
        for k in self.facets:
            vals = {r.get(k, "") for r in rows}
            out[k] = vals.pop() if len(vals) == 1 else ""
        return out

    def payload(self):
        by_x = {}
        for c in self.codings:
            by_x.setdefault(c["excerpt_id"], {"codes": [], "note": c.get("note", "")})
            by_x[c["excerpt_id"]]["codes"].append([c["code_id"], c["valence"]])

        excerpts = {}
        for x in self.excerpts:
            rec = by_x.get(x["excerpt_id"], {"codes": [], "note": ""})
            excerpts.setdefault(x["source_id"], []).append({
                "id": x["excerpt_id"], "start": int(x["start"]), "end": int(x["end"]),
                "codes": rec["codes"], "note": rec["note"]})

        # frame.csv is the denominator when it exists: an interview covers a
        # whole session and carries no single unit, so deriving the frame from
        # sources would count each one as a unit of its own.
        plays = sorted(self.frame) or sorted({(s["pid"], s["game"])
                                              for s in self.sources})
        # prevalence over the participant frame, not over excerpt count
        play_of_source = {s["source_id"]: (s["pid"], s["game"]) for s in self.sources}
        hit = {}
        for x in self.excerpts:
            play = play_of_source.get(x["source_id"])
            for cid, _ in by_x.get(x["excerpt_id"], {"codes": []})["codes"]:
                hit.setdefault(cid, set()).add(play)

        return {
            "sources": [dict(
                {k: s[k] for k in ("source_id", "pid", "game", "kind", "label", "text")},
                **self._facets_for(s))
                for s in self.sources],
            "facets": self.facets,
            "excerpts": excerpts,
            "codes": [{"id": c["code_id"], "lens": c["lens"], "name": c["name"],
                       "definition": c.get("definition", ""), "include": c.get("include", ""),
                       "exclude": c.get("exclude", ""),
                       "plays": len(hit.get(c["code_id"], ())),
                       "pct": round(100 * len(hit.get(c["code_id"], ())) / len(plays), 1)}
                      for c in self.codes],
            "lenses": sorted({c["lens"] for c in self.codes if c["lens"]}),
            "meta": {"root": self.root, "plays": len(plays),
                     "unit": self.unit, "units": self.units,
                     "participants": len({s["pid"] for s in self.sources}),
                     "sources": len(self.sources), "excerpts": len(self.excerpts),
                     "coder": self.coder},
        }
