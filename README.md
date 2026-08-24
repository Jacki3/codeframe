# codeframe

**Qualitative coding in plain CSV files, with the provenance filed for you.**

You read your material, copy whatever passages matter into a spreadsheet, and
write the code and any note beside each one. codeframe works out where each quote
came from — which participant, which unit, which question or timestamp — so none
of that has to be recorded by hand. Then it builds a small website: your codebook,
your findings, and your discussion notes.

Standard library only. Every artefact is a CSV or a small JSON file, so the whole
project belongs under version control and every figure regenerates from source.

MIT licensed. Python 3.9+. Full command reference in
**[COMMANDS.md](COMMANDS.md)**.

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

## Checking your work

```bash
python audit.py --data ../myproject
```

Nothing else verifies that `sources.csv` and `frame.csv` say what you believe.
An import that silently drops a third of the interview text produces a complete,
plausible, **wrong** set of findings, and the only symptom is that the corpus
looks a bit thin. The audit lists what is actually there and every inconsistency
it can find: sources with no text, frame rows nothing can ever be coded to,
sources naming a unit outside the frame, excerpts whose offsets no longer match
the text beneath them, orphaned codes, participants with nothing coded, and any
one participant dominating the codings.

### Two coders

```bash
python file_codings.py --data ../myproject --sheet theirs.csv --coder jb --apply
python audit.py --data ../myproject --reliability
```

Filing a sheet replaces **that coder's** codings and leaves everyone else's
alone, so two people can work on one project. You get per-code Cohen's κ, exact
agreement, and — the useful part — the list of passages to reconcile.

> **The honest limitation.** Agreement assumes both coders judged the same units,
> but in an excerpt-first model there are no units until somebody selects one. If
> a second coder never marks a passage, nothing in the data says whether they
> disagreed or never read it. Counting that as agreement would inflate every
> figure, so the comparison is made over the excerpts **both** coders touched and
> everything outside is reported separately.

### When the codebook changes

```bash
python retire.py --data ../myproject --merge ENJ-FUN ENJ-ENJOYMENT --note "same idea"
python retire.py --data ../myproject
```

An emergent codebook is meant to change. Editing `codes.csv` by hand does it
badly: every coding still names the old id, nothing complains, and the code
vanishes from the codebook page while its codings sit unreachable — prevalence
drops and nothing says why.

`codebook/retired_codes.csv` records what was merged, into what, and why. Existing
codings are rewritten, and a sheet coded *before* the merge still files correctly
because the old id is mapped forward. It is also the register a methods section
gets written from.

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

### `propose_codes.py` — use with caution

There is a fifth, deliberately held apart from the others, because **it
undermines the rest.** It draws a sample of your corpus and proposes a starting
codebook from it.

It sends more participant speech than anything else here, and unlike `valence.py`
it is not confined to passages you already chose. It is the most expensive step by
a distance. And it costs you the thing that makes an inductive codebook worth
having: a frame you built by reading is one you can defend line by line, while a
frame you accepted is one you will be asked to justify and will not be able to.
Reading a proposed code also makes it markedly harder to notice the code you would
have written instead — and that effect is strongest at the start, which is exactly
when you would reach for it.

It is included because a blank codebook is a genuinely hard place to begin. It is
built so that using it is a decision you keep making: **nothing is ever written to
`codes.csv`.** Proposals land in `codebook/proposed_codes.csv` marked
`machine-proposed`, and moving one into the codebook is a thing you do by hand,
having read the passages it came from.

#### Using it

**Always dry-run first.** It prints the sample and the exact payload, and sends
nothing:

```bash
python propose_codes.py --data ../myproject --lenses "Enjoyment,Place,Perceptions" --sample 10 --dry-run
```

```
sample: 27 of 334 sources, 3,396 words, 26 participants, seed 1
  survey 26, interview 1
  lenses: Enjoyment, Place, Perceptions
```

`--sample` is a **percentage of sources, not of words** — and the two are not the
same thing. It defaults to `10`. Each source kind is sampled in proportion to its
own size, and within a kind the draw goes round-robin by participant so one
talkative person cannot define the frame.

Watch the word count rather than the source count. On the corpus above:

| | sources | words | |
|---|---|---|---|
| `--sample 5` | 14 | 2,982 | |
| `--sample 10` | 27 | 3,396 | 26 participants, only 1 interview |
| `--sample 25` | 66 | 7,958 | |
| `--sample 10 --kind interview` | 1 | 2,723 | one long transcript ≈ the whole 10% sample |

That last row is the point. Ten percent of the *interviews* is one transcript and
almost as many words as ten percent of everything, because interviews are long and
surveys are short. If your corpus mixes kinds, decide which you actually want to
read.

Then send it:

```bash
python propose_codes.py --data ../myproject --lenses "Enjoyment,Place,Perceptions" --sample 10 --apply
```

Other options: `--n 20` takes a fixed number of sources instead of a percentage,
shared out across kinds by size. `--kind interview` restricts the draw to one
kind. `--seed 1` fixes the sample — the same command twice gives the same
passages, so a methods section can say which ones were read.

#### What you get, and what to do with it

`codebook/proposed_codes.csv`, in the same shape as `codes.csv` plus two columns:
`source` (always `machine-proposed`) and `drawn_from` (the seed and sample size).
Every `note` starts *"PROPOSED, not read by a human."*

**Nothing is written to `codes.csv`, and nothing ever will be.** The intended
workflow is: open the proposals beside the passages they were drawn from, discard
the ones that do not survive that reading — most will not — rewrite the survivors
in your own words, and move those across by hand. A code you have not argued with
is one you cannot defend.

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

## Taking it somewhere else

```bash
python export_qda.py --data ../myproject --dry-run   # check, write nothing
python export_qda.py --data ../myproject             # write myproject.qdpx
```

A project does not have to end here. `export_qda.py` writes
[REFI-QDA](https://www.qdasoftware.org/) `.qdpx`, the open exchange format that
NVivo, ATLAS.ti, MAXQDA, Quirkos and Dedoose all read. Codes, coded passages,
cases with their attributes and your standing notes go across together, so the
work arrives whole rather than as a codebook somebody has to code against again.

In NVivo that is **File → Open Project**, choosing *REFI-QDA Project* in the
file-type list — not File → Import, which is for NVivo's own projects.
`--codebook` also writes a `.qdc`, which is codes and nothing else: the right
thing to hand a second coder in another tool, and no use as a substitute for the
project.

A file is one participant and one unit, with their sources under the questions
that produced them, so somebody opening the project reads a document rather than
gathering fragments. Sources belonging to no single unit stay whole. Cases come
out one per frame row, carrying every category and measure as an attribute.

**On offsets.** A coded passage travels as a start and end position into a text
file, so merging, line endings, a byte order mark or a character outside the
Basic Multilingual Plane can each move a reference off the words it belongs to.
Every offset is checked against the text as it will be written, and one mismatch
stops the export. What no local check can settle is whether a given importer
counts from zero or one — so `--dry-run` prints the shortest passages with their
offsets and exact text. Import once, look at those, and you know. `--base 1` and
`--end-inclusive` switch the convention.

**On valence.** A REFI-QDA coding carries no attributes, so valence is emitted as
its own code tree, co-coded onto the passage — which is what makes a Code ×
Valence matrix query work. A passage carrying two codings of opposite valence is
emitted once per valence at the same range, so the matrix stays exact rather than
counting every code on that passage against both.

---

## Reference

Every command, what each file does, and the shape of a project directory:
**[COMMANDS.md](COMMANDS.md)**.

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

## Licence

MIT — see [LICENSE](LICENSE). Use it, change it, publish what you make with it.

If it is useful in published work, a citation of the repository is welcome but
not required.

## Not yet

- **Notes into an argument.** `--summarise` writes a paragraph per lens from the
  coding notes. Turning those into a claim somebody could disagree with, and
  defend, is still yours.
- **Hunting candidates for an existing code.** `propose_codes.py` proposes a
  codebook from a sample; going back through the corpus for more of what an
  established code already covers is a different job, and needs its own decision
  about what may leave the machine.
- **A matched light/dark pair from one source.** `--from` adds one theme per run.
- **Coming back in.** `export_qda.py` only goes out. Nothing here reads a `.qdpx`,
  so coding done in another tool has to return by hand.
- **Memos linked to the codes they discuss.** The REFI-QDA schema has links and
  the exporter does not emit them, so standing notes arrive in NVivo as project
  memos, attached to nothing.
