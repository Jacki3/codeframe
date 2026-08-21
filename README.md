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

## What is here

| | |
|---|---|
| `setup_project.py` | profile raw data, propose a mapping, build the project |
| `review.py` | the optional model check of that mapping, and the only place a request is sent |
| `file_codings.py` | file a coding spreadsheet against the corpus |
| `valence.py` | settle valences left blank |
| `project.py` | project state, shared by the tools |
| `serve.py` | the browser coding tool |
| `findings.py` | build the findings, codebook and discussion pages |
| `siteinfo.py` | what the site calls itself |
| `theme.py` | the themes it ships with |
| `model.py` | which model the model-backed steps use |

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

## Every command

Nine scripts. Only `--from`, `--review`, `--add`, `--summarise` and `valence.py`
ever call a model; everything else runs on your machine alone.

**Setting up** — `setup_project.py`

```
python setup_project.py --raw ../raw --to ../myproject [--skip folder,folder]
python setup_project.py --to ../myproject --review [--dry-run] [--model NAME]
python setup_project.py --to ../myproject --apply [--allow-rename]
```

**Coding** — `file_codings.py`, `valence.py`, `serve.py`

```
python file_codings.py --data ../myproject --sheet coding.csv [--apply] [--allow-new-codes] [--coder NAME]
python valence.py --data ../myproject [--dry-run | --offline] [--apply] [--batch N]
python serve.py --data ../myproject [--port N] [--read-only] [--no-open] [--coder NAME]
```

**Building the site** — `findings.py`

```
python findings.py --data ../myproject --generate
python findings.py --data ../myproject --codebook
python findings.py --data ../myproject --discussion [--summarise]
python findings.py --data ../myproject --add "a request in words"
```

**Any of those four writes all three pages.** They share a masthead, a nav, a
theme and a figures strip, so a change to any of those changes all three —
updating a heading should not be a three-command job. The flag chooses what to
*recompute*, not what to write. Generated summaries are cached in
`findings/summaries.json`, so a rebuild never drops paragraphs you paid for.

**Appearance and identity** — `siteinfo.py`, `theme.py`, `model.py`

```
python siteinfo.py --data ../myproject --init
python siteinfo.py --data ../myproject --title T --version V --project P --description D --authors "A, B" --footer F
python theme.py --data ../myproject [--list] [--default NAME] [--drop NAME] [--reset]
python theme.py --data ../myproject --from SOURCE [--name NAME] [--force]
python theme.py --data ../myproject --favicon logo.png
python model.py [NAME] [--check] [--login] [--clear]
```

After any of those, rebuild with `findings.py --generate` to see the change.

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

**Any of these rebuilds all three pages.** They share a masthead, a nav, a theme
and a figures strip, so a change to any of those changes all three — and updating
a heading should not be a three-command job.

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

**Lenses combine and codes can be picked.** Clicking a second lens chip adds it
rather than replacing the first, so you can read enjoyment and place together.
Every code has a checkbox: tick several — shift-click for a run — then *Show only
picked* to read just those side by side, whatever lens they belong to. Search
narrows within the selection, and the tally says how much of the codebook you are
looking at.

Each code carries a prevalence bar on a **0–100 scale**, not scaled to the most
common code: a bar scaled to the leader makes the top code look total whatever it
actually reached, which is the wrong impression to give about a corpus where
nothing passes a third. A rare code therefore draws a sliver, so a non-zero value
gets a minimum width — *rare* and *never* must not look the same, and only zero
draws nothing.

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

## What the site calls itself

```
python siteinfo.py --data ../myproject --init
python siteinfo.py --data ../myproject --title "Qualitative codebook" --version v0.4
```

Read from `<project>/site.json`. Nothing is required — with no file at all the
title is the project folder's own name, which is right often enough to be a
sensible default and wrong in a way that is obvious the moment you look.

| | |
|---|---|
| `title` | the h1 |
| `version` | beside it, greyed |
| `project` | the eyebrow above it — the study or programme this belongs to |
| `description` | the standfirst under it |
| `authors` | shown in the footer |
| `footer` | a licence, a DOI, a date — whatever else belongs at the bottom |

Every page opens with that masthead, then the headline figures, then the nav.
The codebook and discussion pages carry a **search box** (press `/`, Escape
clears) and **filter-by-lens chips** with counts; matching happens in the page,
with no reload and no server, and a lens heading with nothing left under it hides
itself. Everything is searchable, including the method notes — searching
*weather* on the discussion page finds the note about the cold.

## How the pages look

The reader's choice follows them between pages two ways: it is stored in
`localStorage`, and the nav links carry it as `?theme=`. The second matters more
than it sounds — `localStorage` is per-origin, so opening the pages from a
`file://` path or inside a preview pane can give each page its own empty store,
and the choice would be forgotten on every click. A small script in `<head>`
reads the URL first, then storage, and applies the theme before the page paints,
so there is no flash of the default either.



A project ships **several themes, not one**. Every page carries all of them plus a
picker, so the reader chooses — and "Match my system" hands control back to their
own light/dark setting. The choice is remembered per reader in `localStorage`.
That matters: somebody who needs high contrast should not have to ask you for a
rebuild.

```
python theme.py --data ../myproject --list
python theme.py --data ../myproject --default chalk
python theme.py --data ../myproject --from palette.png --name understory
python theme.py --data ../myproject --from https://example.org
python theme.py --data ../myproject --drop understory
python theme.py --data ../myproject --favicon logo.png
```

Four ship by default: **Sarsen**, **Sarsen dark**, **Chalk (high contrast)**, and
**Dusk**. `--default` only decides which opens before the reader chooses.

`--from` adds one. Hex colours need no vision — they are already the answer, and
the work is assigning them to roles. **An image or a URL is why this involves a
model at all**: it must see the thing, so the CLI is granted `Read` for a file or
`WebFetch` for a page, one tool, only for that call. Fonts come back too.

### Tokens worth knowing

| | |
|---|---|
| `include` / `exclude` | the two halves of a code definition. Green-ish and red-ish deliberately — these are never compared to each other in a chart, so hue may carry the distinction. |
| `pos` / `neg` | favourable and unfavourable. These *are* compared, in stacked bars, so they are blue and orange and are checked against a deuteranopia simulation. |
| `series-a` / `series-b` | extra chart series beyond the valence pair. |
| `font-display` | headings and headline figures, separate from body and mono. |

### Readability is computed, not taken on trust

Every theme in the project is checked before anything is written — contrast for
text and marks, and `pos` against `neg` under deuteranopia (OKLab ΔE ≥ 8). A theme
that fails is reported and not written unless you pass `--force`.

One thing colour cannot fix: deuteranopia collapses hue onto roughly one
blue–yellow axis, so once `pos` and `neg` hold the two poles there is no third hue
left for `mixed`. It carries a diagonal stripe as well as a colour, and the legend
and its fixed place in the stack do the rest. The checker says so rather than
pretending otherwise.

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
