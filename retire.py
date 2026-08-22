"""Merge one code into another, or retire it, without orphaning what you coded.

    python retire.py --data ../myproject
    python retire.py --data ../myproject --merge ENJ-FUN ENJ-ENJOYMENT --note "same idea"
    python retire.py --data ../myproject --retire PLC-VAGUE --note "never earned its keep"

An emergent codebook is meant to change. Two codes turn out to be one; a code
written early turns out to describe nothing. Editing codes.csv by hand does that
badly: every coding still names the old id, nothing complains, and the code
quietly vanishes from the codebook page while its codings sit in the data
unreachable. Prevalence drops and nothing says why.

So a merge is recorded rather than performed silently. codebook/retired_codes.csv
keeps old_id, new_id, a note and the date, and it is the register a methods
section can be written from - "these two were merged, here is when and why" is a
question reviewers ask about any evolving frame.

The register is applied in both directions: existing codings are rewritten now,
and file_codings.py maps the old id forward when it turns up in a sheet somebody
coded before the merge.
"""
import argparse, collections, csv, datetime, io, os, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

csv.field_size_limit(10 ** 8)
FIELDS = ["old_id", "new_id", "note", "date"]


def read(path):
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write(path, fields, rows):
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in fields} for r in rows])
    os.replace(tmp, path)


def register_path(root):
    return os.path.join(root, "codebook", "retired_codes.csv")


def load_register(root):
    """old id -> new id. Follows a chain, so A->B->C resolves A to C."""
    rows = read(register_path(root))
    direct = {r["old_id"]: (r.get("new_id") or "").strip() for r in rows}
    out = {}
    for old in direct:
        seen, cur = {old}, direct[old]
        while cur and cur in direct and cur not in seen:
            seen.add(cur)
            cur = direct[cur]
        out[old] = cur
    return out, rows


def show(root):
    codes = read(os.path.join(root, "codebook", "codes.csv"))
    codings = read(os.path.join(root, "data", "codings.csv"))
    reg, rows = load_register(root)
    known = {c["code_id"] for c in codes}
    used = collections.Counter(c["code_id"] for c in codings)

    if rows:
        print(f"register: {len(rows)} entr{'y' if len(rows) == 1 else 'ies'}")
        for r in rows:
            arrow = f"-> {r['new_id']}" if (r.get("new_id") or "").strip() else "retired"
            print(f"  {r['old_id']:<24} {arrow:<26} {r.get('date', '')}")
            if r.get("note"):
                print(f"      {r['note'][:76]}")
    else:
        print("register: empty - no code has been merged or retired")

    orphan = sorted(c for c in used if c not in known and c not in reg)
    if orphan:
        print(f"\n{len(orphan)} code(s) are used by codings but are not in "
              f"codes.csv and not on the register:")
        for c in orphan:
            print(f"  {c:<24} {used[c]} coding(s) - unreachable from the codebook")
        print("\n  If you renamed by hand, record it:")
        print(f"    python retire.py --data <p> --merge {orphan[0]} NEW-ID "
              f"--note \"why\"")
    else:
        print("\nno orphaned codings - every code in use is in codes.csv "
              "or on the register")
    return len(orphan)


def apply_change(root, old, new, note, force):
    codes_p = os.path.join(root, "codebook", "codes.csv")
    codings_p = os.path.join(root, "data", "codings.csv")
    codes = read(codes_p)
    codings = read(codings_p)
    known = {c["code_id"] for c in codes}
    used = collections.Counter(c["code_id"] for c in codings)

    if old not in known and not used.get(old):
        raise SystemExit(f"no code called {old!r} - nothing in codes.csv or "
                         f"codings.csv uses it")
    if new:
        if new == old:
            raise SystemExit("a code cannot be merged into itself")
        if new not in known:
            raise SystemExit(
                f"{new!r} is not in codes.csv. Merge into a code that exists, or "
                f"add it first - a merge should point somewhere real.")
    elif used.get(old) and not force:
        raise SystemExit(
            f"{old} still has {used[old]} coding(s). Retiring it with no "
            f"replacement leaves them unreachable.\n"
            f"  Merge it into another code, or pass --force if you mean to "
            f"strand them.")

    moved = 0
    for c in codings:
        if c["code_id"] == old:
            if new:
                c["code_id"] = new
                moved += 1

    # a merge can leave one excerpt carrying the target code twice
    seen, deduped = set(), []
    for c in codings:
        key = (c["excerpt_id"], c["code_id"], (c.get("coder") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    collapsed = len(codings) - len(deduped)

    kept = [c for c in codes if c["code_id"] != old]
    fields = list(codes[0].keys()) if codes else ["code_id", "lens", "name"]
    write(codes_p, fields, kept)
    if codings:
        write(codings_p, list(codings[0].keys()), deduped)

    reg_rows = read(register_path(root))
    reg_rows = [r for r in reg_rows if r["old_id"] != old]
    reg_rows.append({"old_id": old, "new_id": new or "", "note": note or "",
                     "date": datetime.date.today().isoformat()})
    write(register_path(root), FIELDS, reg_rows)

    print(f"{'merged' if new else 'retired'} {old}" + (f" into {new}" if new else ""))
    print(f"  {moved} coding(s) rewritten"
          + (f", {collapsed} collapsed as duplicates" if collapsed else ""))
    print(f"  codes.csv: {len(codes)} -> {len(kept)} codes")
    print(f"  recorded in codebook/retired_codes.csv")
    if not new and used.get(old):
        print(f"  WARNING: {used[old]} coding(s) still name {old} and are now "
              f"unreachable from the codebook")
    print("\n  rebuild to see it:  python findings.py --data <p> --generate")


def main():
    ap = argparse.ArgumentParser(
        description="Merge or retire a code, keeping a register of what changed.")
    ap.add_argument("--data", required=True)
    ap.add_argument("--merge", nargs=2, metavar=("OLD", "NEW"),
                    help="move every coding from OLD to NEW and drop OLD")
    ap.add_argument("--retire", metavar="CODE",
                    help="drop a code with no replacement")
    ap.add_argument("--note", default="", help="why - this ends up in the register")
    ap.add_argument("--force", action="store_true",
                    help="retire a code even though codings still use it")
    a = ap.parse_args()
    root = os.path.abspath(a.data)
    if not os.path.isdir(root):
        raise SystemExit(f"no such project: {root}")
    if a.merge and a.retire:
        raise SystemExit("--merge or --retire, not both")
    if a.merge:
        apply_change(root, a.merge[0], a.merge[1], a.note, a.force)
    elif a.retire:
        apply_change(root, a.retire, "", a.note, a.force)
    else:
        raise SystemExit(show(root) and 0 or 0)


if __name__ == "__main__":
    main()
