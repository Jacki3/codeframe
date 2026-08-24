"""Export a project to REFI-QDA .qdpx, for NVivo, ATLAS.ti, MAXQDA and the rest.

    python export_qda.py --data ../myproject --dry-run    # check, write nothing
    python export_qda.py --data ../myproject              # write myproject.qdpx
    python export_qda.py --data ../myproject --codebook   # also a codes-only .qdc

WHAT A .qdpx IS

A ZIP holding project.qde - XML against the REFI-QDA Project schema - and a
Sources folder of plain text files it points at with internal:// URIs. It is the
one open format that carries codes, coded passages, cases with attributes and
memos together, so a project leaves here whole rather than as a codebook someone
has to code against again.

NVivo opens one with File > Open Project, choosing REFI-QDA Project in the
file-type list. Not File > Import: that is for NVivo's own projects, and
Import > Codebook takes a .qdc, which is codes and nothing else.

WHAT BECOMES A FILE

Merged, a file is one participant and one unit, with their sources under the
questions that produced them. A source belonging to no single unit - an
interview across a whole session - stays its own file. That is the split the
frame already makes, so files and cases come out one to one and someone opening
the project reads a document rather than gathering fragments. --no-merge gives
one file per source instead.

THE ONLY HARD PART IS CHARACTER OFFSETS

Everything else is bookkeeping. A coded passage is a start and end position into
a plain text file, so the text written and the offsets written have to agree, and
have to survive whatever the importer does on the way in. Four things can break
that, and none of them is left to hope:

  merging       Every offset moves by however much text now sits in front of it.
                Each one is checked against the merged document before anything
                is written, and a single mismatch stops the export.

  line endings  If the importer normalises LF to CRLF, every offset after the
                first newline shifts. --newline crlf writes CRLF and moves the
                offsets to match, so both conventions are available.

  a byte order  A BOM is one more character before the text starts, shifting
  mark          everything by one. Off by default; --bom if an importer wants it.

  wide          Positions are characters, but .NET counts UTF-16 code units, so
  characters    anything above the Basic Multilingual Plane counts twice there
                and once here. The export refuses to run if the corpus contains
                any, rather than writing a file that is quietly wrong from that
                character onward.

WHAT THE IMPORTER STILL HAS TO TELL YOU

Whether positions count from zero or one, and whether the end is the last
character or one past it, has varied between tools. Rather than assert a
convention, --dry-run prints the shortest passages with their offsets and exact
text. Import once, look at those, and you know. --base and --end-inclusive
switch the convention without touching anything else.

VALENCE

A coding in this schema carries no attributes, so a per-coding valence has
nowhere of its own to go. It is emitted as a second top-level code tree and
co-coded onto the passage. Because a matrix query counts what a passage
intersects, a passage carrying two codings of opposite valence would put both
valence nodes on one span and every code there would read as intersecting both.
So such a passage is emitted once per valence, at the same character range: a
few overlapping references, and Code x Valence stays exact. --no-valence leaves
the whole tree out.
"""
import argparse, collections, csv, io, os, sys, uuid, zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape, quoteattr

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

NS = "urn:QDA-XML:project:1.0"
# Fixed namespace so a re-export produces the same GUIDs and an importer can
# recognise it as the same project rather than a second copy of it.
SEED = uuid.UUID("6f1b0c2e-9a3d-5e47-8b21-4c7d0e9a1f36")
LENS_COLOUR = {"1": "#D97C2B", "2": "#3E7CB1", "3": "#6B7233", "4": "#8A6BA1"}
VALENCE_COLOUR = {"pos": "#3E7CB1", "neg": "#D97C2B",
                  "mixed": "#8A6BA1", "neutral": "#7A7A7A"}


def guid(kind, key):
    return str(uuid.uuid5(SEED, f"{kind}:{key}")).upper()


def who(pid):
    """A participant's label. Zero-padded when the ids are numbers, so the list
    sorts the way a person expects, and left alone when they are not."""
    pid = str(pid)
    return f"PID{int(pid):02d}" if pid.isdigit() else pid


def sortkey(key):
    """Sort (pid, unit) numerically where the pid is a number."""
    pid, unit = key
    return (0, int(pid), unit) if str(pid).isdigit() else (1, 0, f"{pid}{unit}")


def read(path):
    if not os.path.exists(path):
        return []
    csv.field_size_limit(10 ** 8)
    with io.open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def attrs(**kw):
    return "".join(f" {k.replace('_', '')}={quoteattr(str(v))}"
                   for k, v in kw.items() if v not in (None, ""))


class Doc:
    """A tiny XML writer. Element order in this schema is fixed, so the caller
    controls it and nothing here reorders anything behind your back."""

    def __init__(self):
        self.out = ['<?xml version="1.0" encoding="utf-8"?>']
        self.depth = 0

    def open(self, tag, **kw):
        self.out.append("  " * self.depth + f"<{tag}{attrs(**kw)}>")
        self.depth += 1

    def close(self, tag):
        self.depth -= 1
        self.out.append("  " * self.depth + f"</{tag}>")

    def leaf(self, tag, **kw):
        self.out.append("  " * self.depth + f"<{tag}{attrs(**kw)}/>")

    def text(self, tag, body):
        if (body or "").strip():
            self.out.append("  " * self.depth + f"<{tag}>{escape(body)}</{tag}>")

    def __str__(self):
        return "\n".join(self.out) + "\n"


def transform(text, crlf):
    """The bytes that go in the file, and a map from old offset to new."""
    if not crlf:
        return text, lambda i: i
    nl = [0] * (len(text) + 1)
    for i, ch in enumerate(text):
        nl[i + 1] = nl[i] + (1 if ch == "\n" else 0)
    return text.replace("\n", "\r\n"), lambda i: i + nl[i]


def documents(D, merge):
    """The files that will exist, and where each source's text sits inside one.

    Unmerged, a document is a source: one survey answer per file, 334 of them.
    That is faithful and unreadable - someone opening the project to see what a
    participant said has to gather six one-line files to read one session.

    Merged, a document is one participant and one unit: every source they gave
    about it, under its question, in one file. A source belonging to no single
    unit - an interview covering a whole session - is already a whole document
    and is left alone. That is the split the frame already makes, so files and
    cases come out one to one.

    The cost is arithmetic. Every excerpt offset has to move by however much text
    now sits in front of it, and an offset that moves wrongly is a coded
    reference pointing at the wrong words. So this returns the shift for every
    source and the caller checks each one against the original text.
    """
    docs, place = {}, {}                 # doc_id -> {...}, source_id -> (doc_id, shift)
    if not merge:
        for s in D["sources"]:
            docs[s["source_id"]] = {
                "name": f'{who(s["pid"])} · {s["unit"] or s["kind"] or "-"} · {s["source_id"]}',
                "text": s["text"], "desc": f'{s["kind"]}: {s["label"]}',
                "pid": s["pid"], "unit": s["unit"]}
            place[s["source_id"]] = (s["source_id"], 0)
        return docs, place

    grouped = collections.defaultdict(list)
    for s in D["sources"]:
        if not (s["unit"] or "").strip():
            docs[s["source_id"]] = {
                "name": f'{who(s["pid"])} · {s["kind"] or "source"}',
                "text": s["text"], "desc": f'{s["kind"]}: {s["label"]}',
                "pid": s["pid"], "unit": ""}
            place[s["source_id"]] = (s["source_id"], 0)
        else:
            grouped[(s["pid"], s["unit"])].append(s)

    for (pid, unit), members in sorted(grouped.items(), key=lambda kv: sortkey(kv[0])):
        members.sort(key=lambda s: s["source_id"])
        doc_id = f"D-{pid}-{unit}"
        parts, buf = [], f"{who(pid)} · {unit}\n\n"
        for s in members:
            label = (s["label"] or "").strip()
            head = D["questions"].get(label[:60], label)
            if head:
                buf += head + "\n"
            place[s["source_id"]] = (doc_id, len(buf))
            buf += s["text"] + "\n\n"
            parts.append(s["source_id"])
        docs[doc_id] = {"name": f"{who(pid)} · {unit}",
                        "text": buf.rstrip() + "\n",
                        "desc": f'{len(members)} source(s): ' + "; ".join(parts),
                        "pid": pid, "unit": unit}
    return docs, place


def load(root):
    P = lambda *a: os.path.join(root, *a)
    D = {
        "sources": read(P("sources.csv")),
        "excerpts": read(P("data", "excerpts.csv")),
        "codings": read(P("data", "codings.csv")),
        "codes": read(P("codebook", "codes.csv")),
        "notes": read(P("codebook", "notes.csv")),
        "frame": read(P("frame.csv")),
        "assign": read(P("coding_assignment.csv")),
        "questions": questions(P("setup.json")),
        "meta": meta(P("frame.json")),
    }
    if not D["sources"]:
        raise SystemExit(f"no sources.csv in {root}")
    return D


def meta(path):
    """frame.json, if the project has one. Carries unit_label and measures."""
    if not os.path.exists(path):
        return {}
    import json
    return json.load(io.open(path, encoding="utf-8"))


def questions(path):
    """Full question wording, recovered from setup.json.

    A source's label is the question truncated to sixty characters, which is
    fine as a label and poor as a heading in a document somebody is meant to
    read. The full wording is in the setup, so a merged file can carry the
    question as it was actually asked.
    """
    if not os.path.exists(path):
        return {}
    import json, re
    found = set()

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str) and len(o) > 30:
            found.add(o.strip())

    walk(json.load(io.open(path, encoding="utf-8")))
    out = {}
    for q in found:
        bare = re.sub(r"^\s*\d+[.)]\s*", "", q).strip()
        out[bare[:60]] = bare
    return out


def check(D, crlf, docs, place):
    """Everything that would make the export silently wrong.

    The offset checks run against the documents as they will be written, not
    against sources.csv, so merging is verified rather than assumed.
    """
    problems = []
    src = {s["source_id"]: s["text"] for s in D["sources"]}

    wide = {c for t in src.values() for c in t if ord(c) > 0xFFFF}
    if wide:
        problems.append(
            f"{len(wide)} character(s) above the BMP, which .NET counts as two "
            f"and Python as one: {' '.join(repr(c) for c in list(wide)[:5])}")

    for x in D["excerpts"]:
        t = src.get(x["source_id"])
        if t is None:
            problems.append(f'{x["excerpt_id"]}: no source {x["source_id"]}')
            continue
        a, b = int(x["start"]), int(x["end"])
        if t[a:b] != x["text"]:
            problems.append(f'{x["excerpt_id"]}: text does not match its offsets')
            continue
        doc_id, shift = place[x["source_id"]]
        body, remap = transform(docs[doc_id]["text"], crlf)
        if body[remap(a + shift):remap(b + shift)] != transform(x["text"], crlf)[0]:
            problems.append(
                f'{x["excerpt_id"]}: offsets do not land in {doc_id} '
                f'(shift {shift}) - merging or the newline rule moved them')

    known = {c["code_id"] for c in D["codes"]}
    for c in D["codings"]:
        if c["code_id"] not in known:
            problems.append(f'coding refers to unknown code {c["code_id"]}')
    xids = {x["excerpt_id"] for x in D["excerpts"]}
    for c in D["codings"]:
        if c["excerpt_id"] not in xids:
            problems.append(f'coding refers to unknown excerpt {c["excerpt_id"]}')
    return problems


def build(D, a):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    user = guid("user", "researcher")
    files = {}                                    # internal name -> text

    docs, place = documents(D, a.merge)
    by_doc = collections.defaultdict(list)
    for x in D["excerpts"]:
        doc_id, shift = place[x["source_id"]]
        by_doc[doc_id].append((x, shift))
    codings_for = collections.defaultdict(list)
    for c in D["codings"]:
        codings_for[c["excerpt_id"]].append(c)
    anchor_of = {c["anchor"]: c["code_id"] for c in D["codes"] if c.get("anchor")}
    pass_of = {r["pid"]: r.get("pass", "") for r in D["assign"]}
    coder_of = {r["pid"]: r.get("coder", "") for r in D["assign"]}

    d = Doc()
    d.out.append(f'<Project xmlns="{NS}"{attrs(name=a.name, origin="codeframe", creatingUserGUID=user, creationDateTime=now)}>')
    d.depth = 1

    d.open("Users")
    d.leaf("User", guid=user, id="researcher", name=a.coder)
    d.close("Users")

    # --- codes, nested one level under their lens -------------------------
    d.open("CodeBook")
    d.open("Codes")
    lenses = sorted({c["lens"] for c in D["codes"]})
    for lens in lenses:
        label = lens.split(".", 1)[-1].strip() or lens
        d.open("Code", guid=guid("lens", lens), name=label, isCodable="false",
               color=LENS_COLOUR.get(lens[:1], "#7A7A7A"))
        d.text("Description", f"Lens: {label}")
        for c in [c for c in D["codes"] if c["lens"] == lens]:
            d.open("Code", guid=guid("code", c["code_id"]), name=c["code_id"],
                   isCodable="true", color=LENS_COLOUR.get(lens[:1], "#7A7A7A"))
            parts = [c["name"], c["definition"]]
            if c.get("include"):
                parts.append("INCLUDE: " + c["include"])
            if c.get("exclude"):
                parts.append("EXCLUDE: " + c["exclude"])
            if c.get("valence"):
                parts.append("Declared valence: " + c["valence"])
            if c.get("note"):
                parts.append("Note: " + c["note"])
            d.text("Description", "\n\n".join(p for p in parts if p))
            d.close("Code")
        d.close("Code")
    if a.valence:
        d.open("Code", guid=guid("lens", "valence"), name="Valence",
               isCodable="false", color="#7A7A7A")
        d.text("Description",
               "Per-coding valence. A coding in this schema carries no "
               "attributes, so valence is co-coded onto the same passage. "
               "Cross it against the lens trees in a matrix query.")
        for v in ("pos", "neg", "mixed", "neutral"):
            d.open("Code", guid=guid("valence", v), name=v, isCodable="true",
                   color=VALENCE_COLOUR[v])
            d.text("Description", f"Coding judged {v}.")
            d.close("Code")
        d.close("Code")
    d.close("Codes")
    d.close("CodeBook")

    # --- variables ---------------------------------------------------------
    meas = set(D["meta"].get("measures") or [])
    cols = [c for c in (D["frame"][0] if D["frame"] else {}) if c not in ("pid", "unit")]
    d.open("Variables")
    for col in cols:
        d.leaf("Variable", guid=guid("var", col), name=col,
               typeOfVariable="Float" if col in meas else "Text")
    for col in ("pass", "coder"):
        d.leaf("Variable", guid=guid("var", col), name=col, typeOfVariable="Text")
    d.close("Variables")

    # --- cases: one per frame row, plus one per source with no unit --------
    d.open("Cases")
    unit_label = D["meta"].get("unit_label") or "unit"
    docs_of = collections.defaultdict(list)
    for s in D["sources"]:
        if (s["unit"] or "").strip():
            doc_id = place[s["source_id"]][0]
            if doc_id not in docs_of[(s["pid"], s["unit"])]:
                docs_of[(s["pid"], s["unit"])].append(doc_id)
    for r in D["frame"]:
        key = (r["pid"], r["unit"])
        d.open("Case", guid=guid("case", f"{key[0]}|{key[1]}"),
               name=f'{who(r["pid"])} · {r["unit"]}')
        d.text("Description",
               f'One {unit_label}: this participant and this {unit_label}.')
        for col in cols:
            if (r.get(col) or "").strip() == "":
                continue
            d.open("VariableValue")
            d.leaf("VariableRef", targetGUID=guid("var", col))
            d.text("FloatValue" if col in meas else "TextValue", r[col])
            d.close("VariableValue")
        for col, src in (("pass", pass_of), ("coder", coder_of)):
            if src.get(r["pid"]):
                d.open("VariableValue")
                d.leaf("VariableRef", targetGUID=guid("var", col))
                d.text("TextValue", src[r["pid"]])
                d.close("VariableValue")
        for sid in docs_of.get(key, []):
            d.leaf("SourceRef", targetGUID=guid("source", sid))
        d.close("Case")
    for s in D["sources"]:
        if (s["unit"] or "").strip():
            continue
        d.open("Case", guid=guid("case", f'loose|{s["source_id"]}'),
               name=f'{who(s["pid"])} · {s["kind"] or "source"}')
        d.text("Description",
               f'This source belongs to no single {unit_label}, so it is a case '
               f'of its own. Do not add it to this participant\'s {unit_label} '
               f'cases: its codings would then count against every one of them.')
        d.leaf("SourceRef", targetGUID=guid("source", s["source_id"]))
        d.close("Case")
    d.close("Cases")

    # --- sources, with their selections and codings ------------------------
    d.open("Sources")
    for doc_id, doc in docs.items():
        g = guid("source", doc_id)
        body, remap = transform(doc["text"], a.newline == "crlf")
        files[f"{g}.txt"] = body
        d.open("TextSource", guid=g, name=doc["name"],
               plainTextPath=f"internal://{g}.txt",
               creatingUser=user, creationDateTime=now)
        d.text("Description", doc["desc"])
        for x, shift in sorted(by_doc.get(doc_id, []),
                               key=lambda p: int(p[0]["start"]) + p[1]):
            start = remap(int(x["start"]) + shift) + a.base
            end = remap(int(x["end"]) + shift) + a.base - (1 if not a.end_exclusive else 0)
            xid = x["excerpt_id"]

            # One selection per valence, not per passage.
            #
            # A matrix query counts what a selection intersects, and a valence
            # node sits on the selection rather than on the coding. So a passage
            # carrying two codings of opposite valence - one participant praising
            # the checklist and faulting the free ordering in the same breath -
            # would put both valence nodes on one span, and every code on that
            # span would read as intersecting both. Splitting the span by valence
            # costs a few overlapping references and makes Code x Valence exact.
            groups = collections.OrderedDict()
            for c in codings_for[xid]:
                groups.setdefault(
                    (c.get("valence") or "").strip().lower() if a.valence else "",
                    []).append(c)
            multi = len(groups) > 1

            for v, gcs in groups.items():
                key = f"{xid}|{v}" if multi else xid
                d.open("PlainTextSelection", guid=guid("sel", key),
                       name=f"{xid} ({v})" if multi else xid,
                       startPosition=start, endPosition=end,
                       creatingUser=user, creationDateTime=now)
                desc = []
                if anchor_of.get(xid) in {c["code_id"] for c in gcs}:
                    desc.append(f"ANCHOR for {anchor_of[xid]}")
                if multi:
                    desc.append(
                        f"This passage carries codings of more than one valence; "
                        f"it is split so each valence has its own reference. "
                        f"This one holds the {v} codings.")
                for c in gcs:
                    if (c.get("note") or "").strip():
                        desc.append(f'{c["code_id"]}: {c["note"]}')
                d.text("Description", "\n".join(desc))
                for c in gcs:
                    d.open("Coding", guid=guid("coding", f'{xid}|{c["code_id"]}'),
                           creatingUser=user, creationDateTime=now)
                    d.leaf("CodeRef", targetGUID=guid("code", c["code_id"]))
                    d.close("Coding")
                if a.valence and v in VALENCE_COLOUR:
                    d.open("Coding", guid=guid("vcoding", f"{xid}|{v}"),
                           creatingUser=user, creationDateTime=now)
                    d.leaf("CodeRef", targetGUID=guid("valence", v))
                    d.close("Coding")
                d.close("PlainTextSelection")
        d.close("TextSource")
    d.close("Sources")

    # --- method notes as project memos -------------------------------------
    if D["notes"]:
        d.open("Notes")
        for n in D["notes"]:
            g = guid("note", n.get("note_id") or n.get("title"))
            body = n.get("note") or ""
            if n.get("evidence"):
                body += f"\n\nEvidence: {n['evidence']}"
            files[f"{g}.txt"] = transform(body, a.newline == "crlf")[0]
            d.leaf("Note", guid=g,
                   name=f'{n.get("note_id","")} {n.get("category","")}: {n.get("title","")}'.strip(),
                   plainTextPath=f"internal://{g}.txt",
                   creatingUser=user, creationDateTime=now)
        d.close("Notes")

    d.depth = 0
    d.out.append("</Project>")
    return str(d), files


CODEBOOK_NS = "urn:QDA-XML:codebook:1:0"


def build_codebook(D, a):
    """The codes on their own, as a REFI-QDA .qdc.

    A different and much smaller format than a project: codes and nothing else.
    NVivo's Import > Codebook asks for one of these, which is why people reach
    for it by mistake - it carries no sources, no codings, no cases and no
    memos, so importing it leaves every coding to redo by hand.

    It earns its place for the one job it is actually for: handing the codebook
    to another coder, in whatever tool they use, without handing over the data.
    """
    d = Doc()
    d.out.append(f'<CodeBook xmlns="{CODEBOOK_NS}"{attrs(origin="codeframe")}>')
    d.depth = 1
    d.open("Codes")
    for lens in sorted({c["lens"] for c in D["codes"]}):
        label = lens.split(".", 1)[-1].strip() or lens
        d.open("Code", guid=guid("lens", lens), name=label, isCodable="false",
               color=LENS_COLOUR.get(lens[:1], "#7A7A7A"))
        d.text("Description", f"Lens: {label}")
        for c in [c for c in D["codes"] if c["lens"] == lens]:
            d.open("Code", guid=guid("code", c["code_id"]), name=c["code_id"],
                   isCodable="true", color=LENS_COLOUR.get(lens[:1], "#7A7A7A"))
            parts = [c["name"], c["definition"]]
            if c.get("include"):
                parts.append("INCLUDE: " + c["include"])
            if c.get("exclude"):
                parts.append("EXCLUDE: " + c["exclude"])
            if c.get("valence"):
                parts.append("Declared valence: " + c["valence"])
            d.text("Description", "\n\n".join(p for p in parts if p))
            d.close("Code")
        d.close("Code")
    if a.valence:
        d.open("Code", guid=guid("lens", "valence"), name="Valence",
               isCodable="false", color="#7A7A7A")
        d.text("Description", "Per-coding valence, co-coded onto the passage.")
        for v in ("pos", "neg", "mixed", "neutral"):
            d.open("Code", guid=guid("valence", v), name=v, isCodable="true",
                   color=VALENCE_COLOUR[v])
            d.close("Code")
        d.close("Code")
    d.close("Codes")
    # No empty <Sets/>: it is optional, and an empty one is the kind of thing a
    # strict validator rejects for no gain.
    d.depth = 0
    d.out.append("</CodeBook>")
    return str(d)


def main():
    ap = argparse.ArgumentParser(description="Export a codeframe project to REFI-QDA .qdpx.")
    ap.add_argument("--data", required=True)
    ap.add_argument("--codebook", action="store_true",
                    help="also write a .qdc - codes only, no data")
    ap.add_argument("--merge", action="store_true", default=True,
                    help="one file per participant and unit, sources under their questions")
    ap.add_argument("--no-merge", dest="merge", action="store_false",
                    help="one file per source instead, 1:1 with sources.csv")
    ap.add_argument("--out")
    ap.add_argument("--name", default=None, help="project name inside the file")
    ap.add_argument("--coder", default="researcher")
    ap.add_argument("--newline", choices=["lf", "crlf"], default="lf")
    ap.add_argument("--bom", action="store_true", help="write a BOM on each text file")
    ap.add_argument("--base", type=int, default=0, choices=[0, 1],
                    help="first character is position 0 or 1")
    ap.add_argument("--end-exclusive", action="store_true", default=True)
    ap.add_argument("--end-inclusive", dest="end_exclusive", action="store_false",
                    help="endPosition names the last character, not one past it")
    ap.add_argument("--no-valence", dest="valence", action="store_false", default=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    a.data = os.path.abspath(a.data)
    a.name = a.name or os.path.basename(a.data)
    a.out = a.out or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  f"{a.name}.qdpx")

    D = load(a.data)
    docs, place = documents(D, a.merge)
    problems = check(D, a.newline == "crlf", docs, place)
    unit = D["meta"].get("unit_label") or "unit"

    # Selections are split by valence, so count them the way the file will.
    groups = collections.defaultdict(set)
    for c in D["codings"]:
        groups[c["excerpt_id"]].add((c.get("valence") or "").strip().lower()
                                    if a.valence else "")
    n_sel = sum(len(v) for v in groups.values()) or len(D["excerpts"])
    n_cod = len(D["codings"]) + (n_sel if a.valence else 0)
    split = sum(1 for v in groups.values() if len(v) > 1)
    print(f'{a.name}: {len(docs)} files ({len(D["sources"])} sources'
          f'{", merged by " + unit if a.merge else ", one per source"}), '
          f'{n_sel} selections, {n_cod} codings, {len(D["codes"])} codes, '
          f'{len(D["frame"])} {unit} cases, {len(D["notes"])} notes')
    if split:
        print(f'  {split} passage(s) carry more than one valence and are split, '
              f'so Code x Valence stays exact')
    print(f'  newline {a.newline}, positions {a.base}-based, end '
          f'{"exclusive" if a.end_exclusive else "inclusive"}, '
          f'BOM {"yes" if a.bom else "no"}, valence tree {"yes" if a.valence else "no"}')

    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems[:15]:
            print("  " + p)
        raise SystemExit(1)
    print("  offsets round-trip, every code and excerpt reference resolves")

    xml, files = build(D, a)
    ids = [l.split('guid="')[1].split('"')[0] for l in xml.splitlines() if 'guid="' in l]
    dupe = [g for g, n in collections.Counter(ids).items() if n > 1]
    if dupe:
        print(f"  {len(dupe)} duplicate GUID(s) - refusing to write")
        raise SystemExit(1)
    print(f"  {len(ids)} GUIDs, all distinct")

    print("\ncanaries - find these in the import and check they land exactly:")
    for x in sorted(D["excerpts"], key=lambda x: len(x["text"]))[:5]:
        doc_id, shift = place[x["source_id"]]
        _, remap = transform(docs[doc_id]["text"], a.newline == "crlf")
        s0 = remap(int(x["start"]) + shift) + a.base
        e0 = remap(int(x["end"]) + shift) + a.base - (0 if a.end_exclusive else 1)
        print(f'  {docs[doc_id]["name"]}  [{s0}:{e0}]  {x["text"]!r}')

    if a.dry_run:
        print(f"\nreport only - would write {a.out}")
        return

    bom = "﻿" if a.bom else ""
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.qde", xml.encode("utf-8"))
        for fn, body in files.items():
            z.writestr(f"Sources/{fn}", (bom + body).encode("utf-8"))
    print(f"\nwrote {a.out}  ({os.path.getsize(a.out) / 1024:.0f} KB, "
          f"{len(files) + 1} entries)")

    if a.codebook:
        p = os.path.splitext(a.out)[0] + ".qdc"
        io.open(p, "w", encoding="utf-8", newline="\n").write(build_codebook(D, a))
        n = len(D["codes"]) + (4 if a.valence else 0)
        print(f"wrote {p}  ({n} codes, and nothing else - no sources, no "
              f"codings, no cases)")


if __name__ == "__main__":
    main()
