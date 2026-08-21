"""Optional step between inspect and apply: have Claude check the mapping.

    python setup_project.py --to ../myproject --review --dry-run   # see the payload
    python setup_project.py --to ../myproject --review             # send it

The heuristics in setup_project.py are good at finding candidates and bad at two
things. They cannot tell a rating scale from a category when both are small
integers, because distinct-count alone does not separate them. And they cannot
name a column: a survey export labels a column with the whole question, sometimes
two questions concatenated -

    "1. What is your participant ID number ()? ... x 3. What was the title of
     the game you just played?"

- and that string then becomes a column in frame.csv and a label in every finding
that splits by it. Both are judgements about wording, which is the part a model
is actually good at.

It runs through the Claude Code CLI rather than the API, so there is no key to
manage, none to leak into the repository, and nothing to set up beyond the CLI
you already have.

WHAT LEAVES THE MACHINE

This project holds pseudonymous participant speech and a roster of real names, so
the payload is built by column class rather than by trust:

    prose           statistics only, never the text. A free-text answer is the
                    participant speaking, and it is not sent.
    identifying     masked to a shape. A name becomes "Aa Aa", an address
                    "aa@aa.aa.aa", a student number "aa##".
    category        real values. These are "Male", "Android", a game title.
    numeric         real values. These are scores.
    headers         as written. The question wording is the researcher's, not
                    the participant's.

--dry-run prints the exact payload and sends nothing. Read it before running this
against data you are answerable for.

NOTHING IS OVERWRITTEN SILENTLY. The reply is merged into setup.json, every
change is recorded in a "review" block with the reason given for it, and the
previous mapping is kept alongside so you can put any of it back.
"""
import json, os, re, shutil, subprocess, sys

# Quotes carry curly apostrophes and dashes; a cp1252 console mangles them on the
# way to the screen even though the files are fine.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

TEXTUAL = 40      # mean length at which a column is certainly prose
WRITTEN = 20      # ...and at which it is prose if nobody repeated the value
EMAIL = re.compile(r"[^@ ]+@[^@ ]+[.][A-Za-z]{2,}")
STUDENT = re.compile(r"[A-Za-z]{0,2}[0-9]{6,9}")
NAME_HINT = re.compile(r"name|email|e-mail|student|address|phone|postcode|birth",
                       re.I)


# ---------------------------------------------------------------- redaction

def shape(v):
    """A value with its content removed but its form intact.

    Enough for a model to see that a column holds email addresses; not enough
    for it to learn whose.
    """
    s = str(v)[:48]
    s = re.sub("[A-Za-z]+", lambda m: "Aa" if m.group(0)[0].isupper() else "aa", s)
    return re.sub("[0-9]+", "##", s)


def identifying(col):
    if any(EMAIL.search(str(e)) or STUDENT.fullmatch(str(e).strip())
           for e in col["examples"]):
        return True
    # A header hint on its own is not enough. An identifier is near-unique by
    # nature, so a column holding a handful of repeated values cannot be one:
    # here "Phone" is the device the participant played on, not a phone number.
    return bool(NAME_HINT.search(col["header"])) and col["distinct"] > 12


def classify(col, n_rows):
    """Which redaction rule applies. Prose is checked first: it is the strictest.

    Deliberately not the same test propose() uses to decide a column is text.
    That one also requires the values to be mostly unique, which is right for
    guessing a role and wrong for deciding what may be sent: a comments box that
    only a handful of people filled in is still prose, still the participant
    speaking, and would otherwise pass as a category and go out in the clear.
    Length alone decides here. profile() truncates examples at 60 characters, so
    an example of exactly that length is a value that was longer.
    """
    longest = max((len(str(e)) for e in col["examples"]), default=0)
    reuse = col["filled"] / col["distinct"] if col["distinct"] else 0
    if col["mean_len"] >= TEXTUAL or longest >= 60:
        return "prose"
    # Between those two, length alone cannot separate a long option label from a
    # short written answer - "Neither agree nor disagree" is 26 characters and so
    # is a one-line comment. Reuse can: an option is picked by many people, a
    # written answer by one. Anything moderately long that nobody else repeated
    # is treated as something a participant wrote.
    if col["mean_len"] >= WRITTEN and reuse < 3:
        return "prose"
    if identifying(col):
        return "identifying"
    return "numeric" if col["numeric"] else "category"


def table_of(spec):
    r = spec.get("responses") or {}
    for t in spec.get("found", []):
        if t["file"] == r.get("file") and t["sheet"] == r.get("sheet"):
            return t
    return None


def digest(spec):
    """Build the payload. This function is the whole of what can be sent."""
    r, table = spec["responses"], table_of(spec)
    if table is None:
        raise SystemExit("setup.json has no responses table to review")

    role = {}
    for k, name in (("text", "text"), ("categories", "category"),
                    ("measures", "measure")):
        for h in r.get(k) or []:
            role[h] = name
    if r.get("pid"):
        role[r["pid"]] = "pid"
    if r.get("unit"):
        role[r["unit"]] = "unit"

    cols = []
    for c in table["columns"]:
        klass = classify(c, table["rows"])
        item = {"header": c["header"], "filled": c["filled"],
                "distinct": c["distinct"], "mean_len": c["mean_len"],
                "numeric": c["numeric"],
                "proposed": role.get(c["header"], "ignored"),
                "why": table["proposed"]["why"].get(c["header"], "")}
        if klass == "prose":
            item["values"] = "withheld: free text, the participant speaking"
        elif klass == "identifying":
            item["values"] = [shape(e) for e in c["examples"][:3]]
            item["values_are"] = "masked shapes, not the real values"
        else:
            item["values"] = c["examples"][:6]
        cols.append(item)

    return {"table": {"file": table["file"], "sheet": table["sheet"],
                      "rows": table["rows"], "columns": len(cols)},
            "columns": cols}


# ---------------------------------------------------------------- the ask

TASK = """You are checking a proposed column mapping for a qualitative research
project. The mapping decides what gets read and quoted, what the findings can be
split by, and what the denominator is, so a wrong role is expensive to undo later.

You are given a profile of every column in the response table: the header, how
many rows are filled, how many distinct values, the mean length, and - depending
on what the column holds - its real values, masked shapes, or nothing at all.
Free text is withheld on purpose. Judge those columns from the statistics.

Give every column one role:

  pid        who responded. Repeats when one person answers about several units.
  unit       what a response is about: a game, a condition, a session. (pid,unit)
             is one row of the frame and the denominator for every rate.
  text       prose to be read and quoted from. Each becomes a source document.
  category   something to split findings by: device, gender, group, play order.
  measure    a numeric score: a scale item, a subscale, a timing.
  ignore     administrative, empty, or duplicated columns.
  exclude    identifying - names, emails, student numbers, addresses. These must
             never become a source document or a frame column.

Two judgements the heuristics get wrong, which are the reason you are being asked:

  A rating scale stored as small integers looks exactly like a category, and a
  coded category stored as a number looks exactly like a scale. The distinct
  count cannot separate them. The header usually can.

  Give every column you assign to unit, category or measure a short lower-case
  label, one or two words, underscores not spaces. The header becomes a column
  name in the frame and a label in every finding, and survey exports write whole
  questions into headers.

If the headers show that several measures belong to one scale, group them under a
shared name so subscales can be computed later.

Reply with JSON only, no prose around it, in exactly this shape:

{"pid": "<header>",
 "unit": "<header or null>",
 "text": ["<header>"],
 "categories": ["<header>"],
 "measures": ["<header>"],
 "exclude": ["<header>"],
 "labels": {"<header>": "<short_label>"},
 "measure_groups": {"<group_name>": ["<header>"]},
 "changes": [{"column": "<header>", "from": "<proposed role>", "to": "<your role>",
              "why": "<one sentence>"}],
 "concerns": ["<anything you could not resolve from the profile>"]}

Use headers exactly as they are given to you. List a column under "changes" only
where your role differs from the proposed one. If you are unsure about a column,
keep the proposed role and say so in "concerns" - a flagged uncertainty is useful
and a confident wrong answer is not."""


OFFLINE_NOTE = """
Nothing else needs an account. Only four steps ask a model:
    setup_project.py --review          findings.py --add
    valence.py                         findings.py --discussion --summarise
Setup, --apply, file_codings.py, serve.py, valence.py --offline,
findings.py --generate and --discussion all run on your machine alone,
and every step that does send something takes --dry-run."""


def explain(env):
    """Turn the CLI's own error into something the reader can act on."""
    msg = str(env.get("result") or env.get("terminal_reason") or "").strip()
    low = msg.lower()
    if "not logged in" in low or "/login" in low:
        return ("the claude CLI is installed but not signed in.\n\n"
                "    claude auth login          (or  python model.py --login)\n"
                "    claude auth status         to check it worked\n" + OFFLINE_NOTE)
    if "unrecognized_model" in low or "model" in low:
        return (f"the claude CLI would not accept that model:\n    {msg[:200]}\n\n"
                "    run  python model.py  to see the names known to work.")
    return f"the claude CLI reported a problem:\n    {msg[:400]}\n" + OFFLINE_NOTE


def ask(payload, model=None, timeout=600, task=None, tools=None):
    from model import current
    model = model or current()
    exe = shutil.which("claude")
    if not exe:
        raise SystemExit(
            "the claude CLI was not found on PATH.\n\n"
            "    install it from claude.com/product/claude-code,\n"
            "    then run  claude auth login\n" + OFFLINE_NOTE)
    prompt = (task or TASK) + "\n\nINPUT\n" + json.dumps(payload, indent=1)
    # Tools are granted one at a time and only where the job needs them: matching
    # a theme to an image means the model has to see the image, and there is no
    # way to do that without letting it read the file.
    cmd = [exe, "-p", "--output-format", "json", "--model", model]
    if tools:
        cmd += ["--allowedTools", ",".join(tools)]
    p = subprocess.run(
        cmd,
        input=prompt, capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace")

    # Read the envelope BEFORE the exit code. The CLI exits non-zero and puts a
    # perfectly good explanation inside the JSON - "Not logged in" being the one
    # every new user meets - and checking the exit code first buries it under
    # eight hundred characters of usage counters.
    env = None
    if (p.stdout or "").strip():
        try:
            env = json.loads(p.stdout)
        except json.JSONDecodeError:
            env = None
    if env is not None and env.get("is_error"):
        raise SystemExit(explain(env))
    if p.returncode != 0:
        raise SystemExit(f"claude exited {p.returncode}:\n{(p.stderr or p.stdout)[:800]}")
    if env is None:
        raise SystemExit(f"could not read the CLI response:\n{p.stdout[:800]}")
    return unwrap(env.get("result") or ""), env


def unwrap(body):
    """Pull the JSON object out of the reply, fenced or not."""
    m = re.search(r"```(?:json)?(.*?)```", body, re.S)
    if m:
        body = m.group(1)
    a, b = body.find("{"), body.rfind("}")
    if a < 0 or b < a:
        raise SystemExit(f"no JSON object in the reply:\n{body[:800]}")
    try:
        return json.loads(body[a:b + 1])
    except json.JSONDecodeError as e:
        raise SystemExit(f"the reply was not valid JSON ({e}):\n{body[a:b + 1][:800]}")


# ---------------------------------------------------------------- merging

def slug(v):
    return re.sub("[^a-z0-9]+", "_", str(v).lower()).strip("_")[:24]


def merge(spec, reply, model):
    """Apply the reply to setup.json, keeping what it replaced.

    Every header is checked against the table before it is used. A model that
    invents a column name, or shortens one, must not be able to silently drop a
    real column from the mapping - so unknown headers are refused and reported
    rather than written.
    """
    r, table = spec["responses"], table_of(spec)
    valid = {c["header"] for c in table["columns"]}
    before = {k: r.get(k) for k in ("pid", "unit", "text", "categories", "measures")}

    unknown = sorted({h for k in ("text", "categories", "measures", "exclude")
                      for h in (reply.get(k) or []) if h not in valid})

    def keep(names):
        return [h for h in (names or []) if h in valid]

    excluded = set(keep(reply.get("exclude")))
    if reply.get("pid") in valid:
        r["pid"] = reply["pid"]
    if reply.get("unit") in valid or reply.get("unit") is None:
        r["unit"] = reply.get("unit")
    for k, src in (("text", "text"), ("categories", "categories"),
                   ("measures", "measures")):
        r[k] = [h for h in keep(reply.get(src)) if h not in excluded]
    r["exclude"] = sorted(excluded)

    # Labels rename frame columns, so two headers must never collapse onto one.
    labels, seen = {}, {}
    for h, v in (reply.get("labels") or {}).items():
        s = slug(v)
        if h in valid and s and s not in ("pid", "unit"):
            if s in seen:
                continue                       # collision: both keep their header
            seen[s] = h
            labels[h] = s
    r["labels"] = labels

    spec["review"] = {
        "by": "claude code cli", "model": model,
        "changes": reply.get("changes") or [],
        "concerns": reply.get("concerns") or [],
        "measure_groups": reply.get("measure_groups") or {},
        "refused_unknown_headers": unknown,
        "mapping_before": before,
    }
    return spec["review"]


# ---------------------------------------------------------------- driver

def review(dst, model=None, dry_run=False):
    path = os.path.join(dst, "setup.json")
    if not os.path.exists(path):
        raise SystemExit(f"no setup.json in {dst} - run the inspect phase first")
    spec = json.load(open(path, encoding="utf-8"))
    if not spec.get("responses"):
        raise SystemExit("setup.json has no responses table to review")

    from model import current
    model = model or current()
    payload = digest(spec)
    withheld = sum(1 for c in payload["columns"] if not isinstance(c["values"], list))
    masked = sum(1 for c in payload["columns"] if c.get("values_are"))

    if dry_run:
        print(json.dumps(payload, indent=1))
        print(f"\n{len(payload['columns'])} columns: "
              f"{withheld} withheld as free text, {masked} masked to shapes.")
        print("Nothing was sent. Drop --dry-run to send exactly this.")
        return

    print(f"sending {len(payload['columns'])} column profiles to {model} "
          f"({withheld} withheld, {masked} masked)")
    reply, env = ask(payload, model)
    r = merge(spec, reply, model)

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=1)
    os.replace(tmp, path)

    print()
    if r["changes"]:
        print(f"{len(r['changes'])} change(s):")
        for c in r["changes"]:
            print(f"  {str(c.get('column'))[:52]:<54} "
                  f"{c.get('from')} -> {c.get('to')}")
            print(f"    {c.get('why', '')}")
    else:
        print("no role changes proposed.")
    labels = spec["responses"].get("labels") or {}
    if labels:
        print(f"\n{len(labels)} column(s) renamed for the frame:")
        for h, s in list(labels.items())[:12]:
            print(f"  {s:<20} {h[:60]}")
        if len(labels) > 12:
            print(f"  ... and {len(labels) - 12} more")
    if r["measure_groups"]:
        print("\nmeasure groups:")
        for g, hs in r["measure_groups"].items():
            print(f"  {g:<20} {len(hs)} columns")
    if r["concerns"]:
        print("\nflagged, decide these yourself:")
        for c in r["concerns"]:
            print(f"  - {c}")
    if r["refused_unknown_headers"]:
        print(f"\nrefused {len(r['refused_unknown_headers'])} header(s) that are "
              f"not in the table:")
        for h in r["refused_unknown_headers"][:5]:
            print(f"  {h[:70]}")

    cost = env.get("total_cost_usd")
    print(f"\nwrote {path}" + (f"  (${cost:.2f})" if cost else ""))
    print("The previous mapping is kept in review.mapping_before.")
    print("Read the changes, correct anything wrong, then re-run with --apply.")
