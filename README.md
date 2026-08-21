# codeframe

Qualitative coding in plain CSV files, with the provenance filed for you.

You read the material, copy whatever passages matter into a spreadsheet, and write
the code and any note beside each one. The tool works out where each quote came
from — which participant, which unit, which question or timestamp — so none of
that has to be recorded by hand, and it computes prevalence over a denominator
that means something.

Nothing is segmented in advance. Choosing a passage is what creates an excerpt, so
the coded corpus and the codebook grow together.

Standard library only. Everything is a CSV or a small JSON file, so the whole
project belongs under git and every figure regenerates from the source.

---

## Before you start

Python 3.9 or newer, and `openpyxl` if your raw data is `.xlsx`. That is all most
of this needs.

Four steps can call a model — `setup_project.py --review`, `valence.py`,
`findings.py --add`, and `findings.py --discussion --summarise`. Those need the
[Claude Code CLI](https://claude.com/product/claude-code), signed in:

```
claude auth login
```

```
claude auth status
```

There is no API key: the CLI signs in with your Claude account through a browser.
To check the whole setup at once — signed in, which account, which model:

```
python model.py
```

```
account: signed in - you@example.com (pro)

model: sonnet   (default)
```

If you would rather not sign in at all, read *[If you have no Claude
account](#if-you-have-no-claude-account)* below — nearly everything still works.

---

## The three steps

### 1. Set up the project

```
python setup_project.py --raw ../raw --to ../myproject
```

Reads whatever is in the raw folder — spreadsheets, CSVs, transcripts — profiles
every column, and writes `setup.json`: a proposed mapping saying which column is
the participant id, which says what each response is *about*, which hold the text
to code, which are categories to compare across, and which are numeric measures.
Every proposal carries the evidence it was made from. Nothing else is written.

`setup.json` is meant to be edited. The machine is good at finding candidates and
bad at knowing which of two plausible columns you meant.

Optionally, have a model check it first:

```
python setup_project.py --to ../myproject --review --dry-run
python setup_project.py --to ../myproject --review
```

Worth running for the two jobs the heuristics genuinely cannot do: telling a
rating scale from a category when both are small integers, and naming a column,
since a survey export writes the whole question into the header and that string
becomes a column name and a label on every finding.

Then build:

```
python setup_project.py --to ../myproject --apply
```

Writes `sources.csv`, `frame.csv`, and `frame.json`. Transcripts are imported only
once `transcripts_confirmed` is true, because a wrong id mislabels every quote
from that recording.

### 2. Code

Read and code in whatever you like — Excel, Sheets, a text editor. Save as CSV.
`coding_sheet_template.csv` shows the shape:

| column | |
|---|---|
| `quote` | required — the passage, pasted |
| `code` | required — one code, or several separated by `;` |
| `valence` | optional — `pos` / `neg` / `mixed` / `neutral`; blank stays blank |
| `note` | optional — kept with the coding |
| `pid`, `unit` | optional — only to disambiguate, when the report asks |

Column names are matched loosely: `Quote`, `CODE`, `Notes` all work.

```
python file_codings.py --data ../myproject --sheet coding.csv
python file_codings.py --data ../myproject --sheet coding.csv --apply
```

Produces `data/excerpts.csv` — every quote with its provenance and character
offsets — and `data/codings.csv`. Anything it could not place goes to
`data/unresolved.csv` with the reason.

Codes live in `codebook/codes.csv`, which you write as you go: an id, a lens, a
name, the include and exclude rules, and optionally a valence the code carries by
its nature.

**The lens is structural, not decoration.** It is what the discussion page groups
by, and what the coding rail filters and groups the codebook by, so a code with no
lens is one you will not see coming. Conventionally a code id is `PREFIX-SOMETHING`
and the prefix is the lens — `PLC-ANCHOR` under Place, `ENJ-EXPLORE` under
Enjoyment. A stub created by `--allow-new-codes` inherits the lens its prefix-mates
use, and `file_codings.py` lists any code still without one.

**Settle any valence you left blank:**

```
python valence.py --data ../myproject --dry-run
python valence.py --data ../myproject --apply
```

Two judgements kept apart. The *code* may declare a polarity, which needs no model
and sends nothing anywhere. The *model* reads the excerpt and judges what was
said. Where they agree it is written; where they disagree neither wins and the
excerpt is listed for you; where only one has a view, that one is used. Read the
disagreements — when several land on one code, the code's declared valence is
usually what is wrong.

**Or code in the browser:**

```
python serve.py --data ../myproject
```

Secondary to the spreadsheet, but good for reading a whole transcript with its
excerpts highlighted, and for coding the odd passage in place.

### 3. Findings

```
python findings.py --data ../myproject --generate
python findings.py --data ../myproject --codebook
python findings.py --data ../myproject --discussion --summarise
python findings.py --data ../myproject --add "differences between the two conditions for the top ten codes"
```

Every figure is a **spec** — a small JSON object saying what to compare — kept in
`findings/specs.json`. Rendering is deterministic from spec plus data, so the page
rebuilds from the corpus and two people with the same corpus get the same page.
Custom findings survive a regenerate.

Built-in kinds: `prevalence`, `valence`, `split` (code by category), `measures`
(where a code coincides with higher or lower scores), `cooccur` (which codes land
together, at `unit` or `excerpt` level), `dependence` (which kind of source the
evidence came from).

`--add` turns a request in words into a spec. It never returns a number and never
sees a quote.

**The codebook page** is `--codebook`: every code under its lens, with its
definition, include and exclude rules, prevalence, valence spread, and one passage
showing what it means. Code ids mentioned in an exclude rule become links, since
those rules are mostly cross-references and following them by hand is how a
codebook stops being read.

The example passage comes from the `anchor` column of `codes.csv` if you put an
`excerpt_id` there. If you do not, one is chosen — preferring a coding you
annotated, then the one closest to the median length for that code, because the
shortest is usually a fragment and the longest is usually somebody rambling. An
auto-chosen quote is labelled as such, so a pinned example is never mistaken for a
lucky one.

**The discussion page has two halves, and they come from different places.**

*About the study* comes from `codebook/notes.csv`, which you keep by hand — notes
about method rather than about any code. That the survey caught the moment and the
interview caught the reflection; that the weather was cold; that a column in the
raw export is wrong for nine people; that something you looked for was not there.
`notes_template.csv` shows the shape:

```
note_id, category, title, note, evidence
```

`category` is yours to invent — Instrument, Confound, Design, Attribution, Null
result, Source data, Coverage all earn their keep. `evidence` is optional and may
name a `source_id` or an `excerpt_id`; a third of these notes have no single
passage behind them, which is the point of keeping them separately.

These are shown **as written and never summarised**. They are already your prose,
and a model rewriting them could only add drift.

*By lens* comes from the `note` column beside each coding, grouped by the lens of
the code it sits on. `--summarise` writes one paragraph per lens from those, and
is most useful where it catches two notes disagreeing.

---

## The denominator

Rates are over the **participant frame** in `frame.csv` — one row per (pid, unit).
Those rows exist whether or not anything has been coded, so "31% of units" means
31% of the study, not 31% of whatever happened to get coded. This is what lets
prevalence stay meaningful while segmentation stays emergent.

A source belonging to no single unit — an interview covering a whole session, say
— can be read, quoted and coded like any other, but is counted against the
participant rather than a unit, and the reports say so rather than quietly
dropping it.

## What the project calls things

`frame.json` records `unit_label` (what one row of the frame is: a game, a visit,
a session) and `kinds` (the sorts of source in the corpus). Every tool reads its
nouns from there, so a study of museum visits says "36 visits" and offers a Kind
filter of `diary` and `focus_group`. `facets` is the shortlist of categories the
coding rail and the default findings splits use — drop a name from it to remove a
dropdown without touching the data.

## Rebuilding a project that already exists

`--apply` can be re-run at any time; everything derived regenerates from
`setup.json`. Two things are protected because they are decisions rather than
derived values:

**A trimmed `facets` list survives a rebuild.** If you have removed a category
from the coding rail, it stays removed.

**Renaming an existing frame column is refused.** Labels are proposed, not
derived, so two runs of `--review` over the same data can land on `device` and
`phone_os` for the same column. Either is a fine name; changing it under a project
that has already been built is not, because a `facets` entry or a saved finding
refers to columns by name, and a renamed column does not error — it silently stops
matching. `frame.json` records which header each label came from, so a rename is
told apart from a column appearing or disappearing, and the refusal names
everything that referred to the old name. Pass `--allow-rename` when you mean it.

## Bringing your own data

`setup_project.py` is one route in. Anything that writes a `sources.csv` with
these columns will do:

```
source_id, pid, unit, kind, label, text
```

plus a `frame.csv` keyed on `pid, unit`. Only `source_id`, `pid`, `unit` and
`text` are required.

## If you have no Claude account

Most of this does not need one. Only four steps ask a model:

```
setup_project.py --review          findings.py --add
valence.py                         findings.py --discussion --summarise
```

Setup, `--apply`, `file_codings.py`, `serve.py`, `valence.py --offline`,
`findings.py --generate` and `--discussion` all run on your machine alone. You can
take a project from raw spreadsheets to a full findings page without ever sending
anything: the mapping in `setup.json` is editable by hand, valence can come from
`codes.csv`, and every figure is computed locally in any case.

The four that do ask will tell you what to do rather than failing obscurely:

```
the claude CLI is installed but not signed in.

    claude auth login          (or  python model.py --login)
    claude auth status         to check it worked
```

`python model.py --login` hands the terminal over to `claude auth login`, which
opens a browser. `python model.py` on its own reports whether you are signed in
and as whom — that check runs locally, costs nothing, and sends nothing.

## Choosing the model

```
python model.py                 # what is set, and what else is available
python model.py opus --check    # set it, and prove the CLI accepts it
python model.py --clear         # back to the default
```

The choice is written to `config.json` beside the scripts and read by every step
that can call a model. Any of them still takes `--model` to override it for a
single run.

| alias | id | context | in / out per Mtok | |
|---|---|---|---|---|
| `fable` | `claude-fable-5` | 1M | $10 / $50 | most capable; for the hardest reasoning |
| `opus` | `claude-opus-5` | 1M | $5 / $25 | strong general reasoning |
| `sonnet` | `claude-sonnet-5` | 1M | $3 / $15 | the default here |
| `haiku` | `claude-haiku-4-5` | 200K | $1 / $5 | cheapest; for large repeated passes |

*Model list and prices cached 2026-06-24. Prices are first-party API rates, here
for relative scale — requests go through the Claude Code CLI, which bills against
whatever plan you are signed in with, so there is no API key to set.*

An alias resolves to the current model of that family, so `opus` keeps working
after a new Opus is released. A pinned id keeps a study reproducible. For work you
intend to write up, pin the id.

**Which to pick.** Nothing here asks a model to do arithmetic or to write a
finding — it proposes a column mapping, a chart spec, a valence, a summary
paragraph — so the cheaper models are not obviously worse at these jobs. Sonnet is
the default because it has been enough for all four. Reach for Opus when a mapping
is genuinely ambiguous or a corpus is unusual; reach for Haiku when you are
re-running a valence pass over hundreds of excerpts and cost is the constraint.

`--check` sends one trivial request and reports which model actually answered. A
model name is not validated until something is sent, and the worst moment to
discover a typo is part-way through a long pass.

## Where a model is involved

Three places, all optional, none of them load-bearing:

| | sends | never sends |
|---|---|---|
| `--review` | column names, statistics, category values | free text, masked identifiers |
| `valence.py` | unjudged excerpts and your notes | pids, source ids, judged excerpts |
| `--discussion --summarise` | your notes | the passages behind them |

**A model never produces a number.** It proposes a column mapping, a chart spec, a
valence, a summary paragraph — and every figure is computed locally from the
corpus. That is not fastidiousness: a model asked to do arithmetic over a corpus
it cannot see returns plausible figures, and plausible figures in a findings
section are worse than none.

Everything that sends anything takes `--dry-run`, which prints the exact payload
and sends nothing. Run it first on data you are answerable for.

## Safety

Every write goes through a temp file and an atomic replace. The tools write only
inside the project directory. `serve.py` binds to `127.0.0.1` and takes
`--read-only`.

Keep the project under git. The history of `codes.csv` is a record of how the
frame evolved, which is worth having when the methods section asks.

## Not yet

- **Reliability.** Two coders over the same passages, and an agreement figure.
- **Notes into prose.** Notes are bundled by lens on the discussion page; turning
  a lens into an argument is still yours.
- **Codebook assistance.** Proposing a starting codebook from a sample, or hunting
  candidates for an existing code. Both need the source text itself, so both need
  their own decision about what may leave the machine.
