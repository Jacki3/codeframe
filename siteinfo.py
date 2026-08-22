"""What the site calls itself: title, standfirst, project, authors.

    python siteinfo.py --data ../myproject                 # what is set
    python siteinfo.py --data ../myproject --init          # write an editable site.json
    python siteinfo.py --data ../myproject --title "Qualitative codebook" --version v0.4

Read from <project>/site.json. Nothing is required: with no file at all the title
is the project folder's own name, which is right often enough to be a sensible
default and wrong in a way that is obvious the moment you look at the page.

    title        the h1
    version      shown beside it, greyed
    project      the eyebrow above it - the study or programme this belongs to
    description  the standfirst under it, a paragraph
    authors      a list of names, shown in the footer
    footer       anything else you want at the bottom: a licence, a DOI, a date
"""
import argparse, json, os, re, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

FIELDS = ["title", "version", "project", "description", "authors", "footer"]


def default_title(root):
    """A folder called 'reading-study-2024' becomes 'Reading study 2024'."""
    name = os.path.basename(os.path.abspath(root).rstrip("\\/"))
    name = re.sub(r"[-_]+", " ", name).strip()
    return name[:1].upper() + name[1:] if name else "Untitled project"


def load(root):
    root = os.path.abspath(root)
    out = {k: "" for k in FIELDS}
    out["authors"] = []
    p = os.path.join(root, "site.json")
    if os.path.exists(p):
        try:
            got = json.load(open(p, encoding="utf-8"))
            for k in FIELDS:
                if k in got and got[k] not in (None, ""):
                    out[k] = got[k]
        except (json.JSONDecodeError, OSError):
            pass
    if not out["title"]:
        out["title"] = default_title(root)
    if isinstance(out["authors"], str):
        out["authors"] = [a.strip() for a in out["authors"].split(",") if a.strip()]
    return out


def save(root, meta):
    p = os.path.join(os.path.abspath(root), "site.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({k: meta.get(k, "") for k in FIELDS}, f, indent=1)
    os.replace(tmp, p)
    return p


def main():
    ap = argparse.ArgumentParser(description="What the site calls itself.")
    ap.add_argument("--data", required=True)
    ap.add_argument("--init", action="store_true",
                    help="write site.json with the current values, ready to edit")
    for k in FIELDS:
        ap.add_argument(f"--{k}", help=f"set {k}")
    a = ap.parse_args()
    root = os.path.abspath(a.data)
    if not os.path.isdir(root):
        raise SystemExit(f"no such project: {root}")

    meta = load(root)
    changed = False
    for k in FIELDS:
        v = getattr(a, k, None)
        if v is not None:
            meta[k] = ([x.strip() for x in v.split(",") if x.strip()]
                       if k == "authors" else v)
            changed = True

    p = os.path.join(root, "site.json")
    if changed or (a.init and not os.path.exists(p)):
        save(root, meta)
        print(f"wrote {p}")
    elif a.init:
        print(f"{p} already exists - edit it by hand, or pass --title etc.")

    for k in FIELDS:
        v = meta.get(k)
        v = ", ".join(v) if isinstance(v, list) else v
        shown = (str(v)[:70] + "...") if v and len(str(v)) > 70 else (v or "-")
        print(f"  {k:<12} {shown}")
    if not os.path.exists(p):
        print(f"\n  no site.json - title is the folder name. "
              f"Run --init to write one you can edit.")
    else:
        print("\n  rebuild to see it:  python findings.py --data <p> --generate")


if __name__ == "__main__":
    main()
