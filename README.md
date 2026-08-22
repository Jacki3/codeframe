# codeframe

**Qualitative coding in plain CSV files, with the provenance filed for you.**

You read your material, copy whatever passages matter into a spreadsheet, and
write the code and any note beside each one. codeframe works out where each quote
came from — which participant, which unit, which question or timestamp — so none
of that has to be recorded by hand. Then it builds a small website: your codebook,
your findings, and your discussion notes.

Standard library only. Every artefact is a CSV or a small JSON file, so the whole
project belongs under version control and every figure regenerates from source.

```bash
python setup_project.py --raw ../raw --to ../myproject --apply
```

```bash
python file_codings.py --data ../myproject --sheet coding.csv --apply
```

```bash
python findings.py --data ../myproject --generate
```

---

## Two ideas worth knowing before you start

**Nothing is segmented in advance.** Choosing a passage is what creates an
excerpt, so the coded corpus and the codebook grow together. You do not decide in
advance what the units of analysis are.

**Rates are over a frame, not over what you happened to code.** `frame.csv` holds
one row per (participant, unit) — a game played, a session attended, a site
visited. Those rows exist whether or not anything has been coded, so *"31% of
visits"* means 31% of the study rather than 31% of your coding. That is what lets
prevalence stay meaningful while segmentation stays emergent.

A source belonging to no single unit — an interview covering a whole session, say
— is read, quoted and coded like any other, but counted against the participant
rather than a unit. The reports say so rather than quietly dropping it.

---

## Requirements

- **Python 3.9+**
- **`openpyxl`**, only if your raw data is `.xlsx`
- **[Claude Code CLI](https://claude.com/product/claude-code)**, only for the four
  optional steps that use a model

Nothing else. No API key, no database, no build step.

---

## The three steps

### 1 · Set up the project

```bash
python setup_project.py --raw ../raw --to ../myproject
```

Reads whatever is in the raw folder — spreadsheets, CSVs, transcripts — profiles
every column, and writes `setup.json`: a proposed mapping saying which column
identifies the participant, which says what each response is *about*, which hold
the text to code, which are categories to compare across, and which are numeric
measures. Every proposal carries the evidence behind it. Nothing else is written.

`setup.json` is meant to be edited. The machine is good at finding candidates and
bad at knowing which of two plausible columns you meant.

Optionally, have a model check it:

```bash
python setup_project.py --to ../myproject --review
```

Worth running for the two jobs heuristics genuinely cannot do — telling a rating
scale from a category when both are small integers, and naming a column, since a
survey export writes the whole question into the header and that string becomes a
column name and a label on every finding. Add `--dry-run` to see exactly what
would be sent first.

Then build:

```bash
python setup_project.py --to ../myproject --apply
```

Writes `sources.csv`, `frame.csv` and `frame.json`. Transcripts are imported only
once you set `transcripts_confirmed` to true, because a wrong id mislabels every
quote from that recording.

### 2 · Code

Read and code in whatever you like — Excel, Sheets, a text editor. Save as CSV.
`coding_sheet_template.csv` shows the shape:

| column | |
|---|---|
| `quote` | **required** — the passage, pasted |
| `code` | **required** — one code, or several separated by `;` |
| `valence` | optional — `pos` / `neg` / `mixed` / `neutral`; blank stays blank |
| `note` | optional — kept with the coding |
| `pid`, `unit` | optional — only to disambiguate, when the report asks |

Column names are matched loosely: `Quote`, `CODE`, `Notes` all work.

```bash
python file_codings.py --data ../myproject --sheet coding.csv
```

Reports what it would do and writes nothing. Add `--apply` when the report is
clean. You get `data/excerpts.csv` — every quote with its provenance and character
offsets — and `data/codings.csv`. Anything it could not place goes to
`data/unresolved.csv` with the reason.

**How quotes are matched.** On normalised text: smart quotes and dashes folded,
whitespace collapsed, case ignored. That absorbs almost everything copy-and-paste
does to a passage. An exact match in exactly one document resolves; anything else
is reported with the closest candidate and a similarity score. Nothing ambiguous
is filed silently.

**Codes** live in `codebook/codes.csv`, which you write as you go: an id, a lens,
a name, the include and exclude rules, and optionally a valence the code carries
by its nature.

> **The lens is structural, not decoration.** It is what the discussion page
> groups by and what the codebook filters on, so a code with no lens is one you
> will not see coming. Conventionally a code id is `PREFIX-SOMETHING` and the
> prefix is the lens. A stub created by `--allow-new-codes` inherits the lens its
> prefix-mates use, and `file_codings.py` lists any code still without one.

**Settle any valence you left blank:**

```bash
python valence.py --data ../myproject --apply
```

Two judgements kept apart. The *code* may declare a polarity — a frustration code
is negative wherever it lands — which needs no model and sends nothing anywhere.
The *model* reads the excerpt and judges what was actually said. Where they agree
it is written; where they disagree neither wins and the excerpt is listed for you;
where only one has a view, that one is used. `--offline` uses `codes.csv` alone.

Read the disagreements. When several land on one code, it is usually the code's
declared valence that is wrong, not the passages.

**Or code in the browser:**

```bash
python serve.py --data ../myproject
```

Secondary to the spreadsheet, but good for reading a whole transcript with its
excerpts highlighted, and for coding the odd passage in place.

### 3 · Build the site

```bash
python findings.py --data ../myproject --generate
```

Three pages, cross-linked, sharing a masthead and a theme picker:

| page | what it holds |
|---|---|
| **Findings** | prevalence, valence, splits by category, measures, co-occurrence, source dependence |
| **Codebook** | every code under its lens with definition, rules, prevalence bar and an example passage |
| **Discussion** | your method notes, then your coding notes grouped by lens |

**Any `findings.py` command writes all three pages.** They share a masthead, a
nav and a theme, so a change to any of those changes all three. The flag chooses
what to *recompute*, not what to write.

Every figure is a **spec** — a small JSON object saying what to compare — kept in
`findings/specs.json`. Rendering is deterministic from spec plus data, so the page
rebuilds from the corpus and two people with the same corpus get the same page.
Custom findings survive a regenerate.

```bash
python findings.py --data ../myproject --add "differences between the two conditions for the top ten codes"
```

`--add` turns a request in words into a spec. It never returns a number and never
sees a quote.

---

## The site it builds

### Naming it

```bash
python siteinfo.py --data ../myproject --init
```

Writes `site.json`. With no file at all the title is the project folder's own
name, which is right often enough to be a useful default and wrong in a way that
is obvious on sight.

| field | where it appears |
|---|---|
| `title`, `version` | the h1, version greyed beside it |
| `project` | the eyebrow above it |
| `description` | the standfirst |
| `authors`, `footer` | the footer |

### Reading it

The codebook and discussion pages carry a **search box** — press `/`, Escape
clears — and **lens filter chips** with counts. Lenses combine rather than
replace, so you can read two at once. Matching happens in the page: no reload, no
server, no index to keep in step.

### Themes

A project ships **several themes and a picker**, not one baked-in look. Somebody
who needs high contrast should not have to ask you for a rebuild. The choice
follows the reader between pages, and *Match my system* hands control back to
their own light/dark setting.

```bash
python theme.py --data ../myproject --list
python theme.py --data ../myproject --from palette.png --name housestyle
python theme.py --data ../myproject --favicon logo.png
```

Four ship by default: **Light**, **Dark**, **High contrast** and **Dusk**. Each
carries its own **typography and shape** as well as colours — High contrast has
square corners and a heavier rule; Dusk has soft corners and a serif body — so
switching changes the page rather than repainting it.

`--from` matches a source. A list of hex colours needs no model: the colours are
already the answer, and the work is assigning them to roles. **A URL or an image
is why a model is involved at all.** For a URL, codeframe fetches the site's own
stylesheets and counts what is actually in them — colours by frequency,
typefaces, corner radii — and hands the model measurements rather than asking it
to imagine a palette. For an image, the CLI is granted `Read` so it can see the
picture.

**Readability is computed, not taken on trust.** Before any theme is written:

| check | floor |
|---|---|
| body text on ground, and on a card | 4.5:1 |
| secondary ink, include/exclude rules | 4.5:1 |
| muted ink, accent and valence marks | 3:1 |
| `pos` against `neg` under deuteranopia | ΔE 8 |

A colour that misses a floor is nudged along its own lightness — hue and chroma
kept — by the smallest step that passes, and every adjustment is printed. If that
cannot save it, the theme is refused rather than written.

> One thing colour cannot fix: deuteranopia collapses hue onto roughly one
> blue–yellow axis, so once `pos` and `neg` hold the two poles there is no third
> hue left for `mixed`. It carries a diagonal stripe as well as a colour, and the
> legend and its fixed place in the stack do the rest. The checker says so rather
> than pretending otherwise.

---

## Where a model is involved

Four steps, all optional, none load-bearing. **A model never produces a number.**
It proposes a column mapping, a chart spec, a valence, a summary paragraph — and
every figure is computed locally from the corpus. That is not fastidiousness: a
model asked to do arithmetic over a corpus it cannot see returns *plausible*
figures, and plausible figures in a findings section are worse than none.

| step | sends | never sends |
|---|---|---|
| `setup_project.py --review` | column names, statistics, category values | free text; identifiers are masked to shapes |
| `valence.py` | unjudged excerpts and your notes | pids, source ids, already-judged excerpts |
| `findings.py --discussion --summarise` | your notes | the passages behind them |
| `findings.py --add` | code names and category names | any quote |
| `theme.py --from` | measured colours and font names | nothing from your corpus |

Everything that sends anything takes `--dry-run`, which prints the exact payload
and sends nothing. Run it first on data you are answerable for.

### If you have no account

Most of this does not need one:

```
setup_project.py (except --review)    file_codings.py
valence.py --offline                  serve.py
findings.py --generate / --codebook / --discussion
```

You can take a project from raw spreadsheets to a full site without sending
anything: the mapping in `setup.json` is editable by hand, valence can come from
`codes.csv`, and every figure is computed locally regardless. The four steps that
do ask will tell you what to do rather than failing obscurely.

### Choosing the model

```bash
python model.py
python model.py opus --check
```

The choice is written to `config.json` beside the scripts and read by every
model-backed step; any of them still takes `--model` to override for one run.
`--check` sends one trivial request and reports which model actually answered,
because a model name is not validated until something is sent and the worst
moment to find a typo is part-way through a long pass.

Honest guidance: **this tool does not need a large model.** Nothing here asks one
to do arithmetic or write a finding.

---

## Reference

### Every command

```bash
python setup_project.py --raw ../raw --to ../myproject [--skip folder,folder]
python setup_project.py --to ../myproject --review [--dry-run] [--model NAME]
python setup_project.py --to ../myproject --apply [--allow-rename]

python file_codings.py --data ../myproject --sheet coding.csv [--apply] [--allow-new-codes] [--coder NAME]
python valence.py --data ../myproject [--dry-run | --offline] [--apply] [--batch N]
python serve.py --data ../myproject [--port N] [--read-only] [--no-open] [--coder NAME]

python findings.py --data ../myproject --generate
python findings.py --data ../myproject --codebook
python findings.py --data ../myproject --discussion [--summarise]
python findings.py --data ../myproject --add "a request in words"

python siteinfo.py --data ../myproject --init
python siteinfo.py --data ../myproject --title T --version V --project P --description D --authors "A, B"
python theme.py --data ../myproject [--list] [--default NAME] [--drop NAME] [--reset]
python theme.py --data ../myproject --from SOURCE [--name NAME] [--force]
python theme.py --data ../myproject --favicon logo.png
python model.py [NAME] [--check] [--login] [--clear]
```

### What each file does

| | |
|---|---|
| `setup_project.py` | profile raw data, propose a mapping, build the project |
| `review.py` | the optional model check of that mapping — the only place a request is built |
| `file_codings.py` | file a coding spreadsheet against the corpus |
| `valence.py` | settle valences left blank |
| `project.py` | project state, shared by the tools |
| `serve.py` | the browser coding tool |
| `findings.py` | build the three pages |
| `siteinfo.py` | what the site calls itself |
| `theme.py` | the themes it ships with |
| `model.py` | which model the model-backed steps use |

### What a project directory holds

```
myproject/
├── sources.csv             the material to read and quote from
├── frame.csv               one row per (pid, unit) — the denominator
├── frame.json              which columns are categories, which are measures
├── setup.json              the mapping — only if setup_project.py built it
├── site.json               title, authors, description — optional
├── theme.json              the themes the pages ship with — optional
├── codebook/
│   ├── codes.csv           your codes
│   └── notes.csv           method notes — optional
├── data/
│   ├── excerpts.csv        every quote, with provenance
│   ├── codings.csv         which code sits on which excerpt
│   └── unresolved.csv      what could not be placed, and why
└── findings/
    ├── findings.html  codebook.html  discussion.html
    └── specs.json          what each figure compares
```

### What the project calls things

`frame.json` records `unit_label` (a game, a visit, a session) and `kinds` (the
sorts of source in the corpus). Every tool reads its nouns from there, so a study
of museum visits says *"36 visits"* and offers a Kind filter of `diary` and
`focus_group`. `facets` is the shortlist of categories the coding rail and the
default findings splits use.

### Rebuilding a project that already exists

`--apply` can be re-run at any time. Two things are protected because they are
decisions rather than derived values:

**A trimmed `facets` list survives a rebuild.** If you removed a category from
the coding rail, it stays removed.

**Renaming an existing frame column is refused.** Labels are proposed, not
derived, so two runs of `--review` can land on `device` and `phone_os` for the
same column. Either is fine; changing it under a project already built is not,
because a saved finding refers to columns by name and a renamed column does not
error — it silently stops matching. Pass `--allow-rename` when you mean it.

### Bringing your own data

`setup_project.py` is one route in. Anything that writes a `sources.csv` with
these columns will do:

```
source_id, pid, unit, kind, label, text
```

plus a `frame.csv` keyed on `pid, unit`. Only `source_id`, `pid`, `unit` and
`text` are required.

---

## Safety

Every write goes through a temp file and an atomic replace. The tools write only
inside the project directory. `serve.py` binds to `127.0.0.1` and takes
`--read-only`.

Keep the project under version control. The history of `codes.csv` is a record of
how the frame evolved, which is worth having when the methods section asks.

**If your corpus contains identifiable or sensitive material**, note that
`sources.csv` holds the full text of everything you imported, and the generated
pages quote from it. Treat the project directory with the same care as the raw
data, and read `--dry-run` output before using any step that sends.

## Not yet

- **Reliability.** Two coders over the same passages, and an agreement figure.
- **Notes into prose.** Notes are grouped by lens on the discussion page; turning
  a lens into an argument is still yours.
- **Codebook assistance.** Proposing a starting codebook from a sample, or
  hunting candidates for an existing code. Both need the source text itself, so
  both need their own decision about what may leave the machine.
- **A matched light/dark pair from one source.** `--from` adds one theme per run.
