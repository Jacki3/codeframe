# codeframe — command reference

Every command, what each file does, and what a project directory holds.

For what the tool is and why it works this way, see [README.md](README.md).

---

## Every command

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

python audit.py --data ../myproject [--reliability] [--against CODER]
python retire.py --data ../myproject [--merge OLD NEW | --retire CODE] [--note "why"] [--force]
python propose_codes.py --data ../myproject --lenses "A,B" [--sample N] [--n N] [--seed N] [--kind K] [--dry-run] [--apply]

python export_qda.py --data ../myproject [--dry-run] [--codebook] [--no-merge] [--no-valence]
python export_qda.py --data ../myproject [--newline lf|crlf] [--bom] [--base 0|1] [--end-inclusive]
```

## What each file does

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
| `audit.py` | check the corpus, and measure agreement between coders |
| `retire.py` | merge or retire a code without orphaning what you coded |
| `propose_codes.py` | propose a starting codebook from a sample — **read its warnings** |
| `export_qda.py` | export the whole project as REFI-QDA `.qdpx`, for NVivo and the rest |

## What a project directory holds

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

## What the project calls things

`frame.json` records `unit_label` (a game, a visit, a session) and `kinds` (the
sorts of source in the corpus). Every tool reads its nouns from there, so a study
of museum visits says *"36 visits"* and offers a Kind filter of `diary` and
`focus_group`. `facets` is the shortlist of categories the coding rail and the
default findings splits use.

## Rebuilding a project that already exists

`--apply` can be re-run at any time. Two things are protected because they are
decisions rather than derived values:

**A trimmed `facets` list survives a rebuild.** If you removed a category from
the coding rail, it stays removed.

**Renaming an existing frame column is refused.** Labels are proposed, not
derived, so two runs of `--review` can land on `device` and `phone_os` for the
same column. Either is fine; changing it under a project already built is not,
because a saved finding refers to columns by name and a renamed column does not
error — it silently stops matching. Pass `--allow-rename` when you mean it.

## Bringing your own data

`setup_project.py` is one route in. Anything that writes a `sources.csv` with
these columns will do:

```
source_id, pid, unit, kind, label, text
```

plus a `frame.csv` keyed on `pid, unit`. Only `source_id`, `pid`, `unit` and
`text` are required.

---
