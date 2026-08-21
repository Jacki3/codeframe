"""Choose how the pages look, and check that the result is readable.

    python theme.py --data ../myproject                       # what is set
    python theme.py --data ../myproject --list                # the built-in themes
    python theme.py --data ../myproject --set paper
    python theme.py --data ../myproject --from palette.png    # match an image
    python theme.py --data ../myproject --from https://…      # match a site
    python theme.py --data ../myproject --from "#1b3a2f,#e8e4d9,#c2703d"
    python theme.py --data ../myproject --favicon logo.png

Themes live in <project>/theme.json and are read by every page and by the coding
tool, so all four surfaces move together.

MATCHING SOMETHING

A palette given as hex needs no model - the colours are already the answer, and
the work is only assigning them to roles. An image or a site does need one, and it
needs to SEE the thing: --from a file lets the CLI read the image, --from a URL
lets it fetch the page. That is the whole reason this goes through a model at all.

READABILITY IS NOT TAKEN ON TRUST

Whatever comes back is checked here, in Python, before it is written:

  - body text against its background, to WCAG AA (4.5:1); secondary and muted ink
    to their own floors
  - the valence colours against the surface they sit on (3:1, they are marks)
  - pos against neg under deuteranopia, because those two carry opposite meanings
    and a reader who cannot tell them apart is reading the opposite finding

A theme that fails is reported and not written unless you insist. This is the same
rule as everywhere else here: the model proposes, the arithmetic is done locally.
"""
import argparse, base64, colorsys, json, math, os, re, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

# Every custom property the pages and the coding tool use, in one place.
TOKENS = ["ground", "surface", "surface-2", "ink", "ink-2", "ink-3",
          "rule", "rule-soft", "accent", "accent-ink", "accent-wash",
          "mark", "mark-ink", "warn", "pos", "neg", "mixed", "neutral", "none"]
FONTS = ["body", "mono"]

DEFAULT_FONTS = {
    "body": '"Segoe UI",-apple-system,BlinkMacSystemFont,Arial,sans-serif',
    "mono": 'Consolas,"Cascadia Mono","SF Mono",Menlo,monospace',
}

BUILTIN = {
    "default": {
        "name": "default", "fonts": DEFAULT_FONTS,
        "light": {"ground": "#F2F2EF", "surface": "#FFFFFF", "surface-2": "#F8F8F5",
                  "ink": "#22212A", "ink-2": "#56545F", "ink-3": "#86848F",
                  "rule": "#E0DFDA", "rule-soft": "#EBEAE6",
                  "accent": "#6B7233", "accent-ink": "#4E541F", "accent-wash": "#EDEFE0",
                  "mark": "#EDE8B8", "mark-ink": "#3F3A12", "warn": "#8A4B42",
                  "pos": "#1F6FA8", "neg": "#C0651F", "mixed": "#8A6A12",
                  "neutral": "#6B6976", "none": "#C9C7C0"},
        "dark": {"ground": "#17171B", "surface": "#1F1F25", "surface-2": "#25252C",
                 "ink": "#EDECEE", "ink-2": "#A9A7B2", "ink-3": "#8E8C98",
                 "rule": "#31313A", "rule-soft": "#292930",
                 "accent": "#A8B45C", "accent-ink": "#C3CE84", "accent-wash": "#2A2D1E",
                 "mark": "#4A431C", "mark-ink": "#F0E9BE", "warn": "#CC9186",
                 "pos": "#5EA8D8", "neg": "#E0954E", "mixed": "#D9BC63",
                 "neutral": "#A5A3AF", "none": "#45444D"},
    },
    "paper": {
        "name": "paper", "fonts": {
            "body": 'Charter,"Iowan Old Style",Georgia,"Times New Roman",serif',
            "mono": '"SF Mono",Consolas,Menlo,monospace'},
        "light": {"ground": "#F6F3EC", "surface": "#FFFDF8", "surface-2": "#F1EDE3",
                  "ink": "#211E1A", "ink-2": "#544F46", "ink-3": "#807A6E",
                  "rule": "#DED8CA", "rule-soft": "#E9E4D8",
                  "accent": "#7A4A22", "accent-ink": "#5E3818", "accent-wash": "#F0E4D6",
                  "mark": "#F0E0B4", "mark-ink": "#4A3A12", "warn": "#8E3F32",
                  "pos": "#26688F", "neg": "#B45F22", "mixed": "#836411",
                  "neutral": "#6C665C", "none": "#CFC8B8"},
        "dark": {"ground": "#191713", "surface": "#221F1A", "surface-2": "#2A261F",
                 "ink": "#F1EBDF", "ink-2": "#B2AA9A", "ink-3": "#918977",
                 "rule": "#39342B", "rule-soft": "#302B23",
                 "accent": "#C99763", "accent-ink": "#DDB488", "accent-wash": "#2E251A",
                 "mark": "#4A3C1B", "mark-ink": "#F3E7C4", "warn": "#D08C7C",
                 "pos": "#63A6CE", "neg": "#DC9350", "mixed": "#D3B75F",
                 "neutral": "#A9A294", "none": "#413B31"},
    },
    "slate": {
        "name": "slate", "fonts": DEFAULT_FONTS,
        "light": {"ground": "#EFF1F4", "surface": "#FFFFFF", "surface-2": "#F5F7F9",
                  "ink": "#1B2027", "ink-2": "#4B535E", "ink-3": "#79818C",
                  "rule": "#DDE1E7", "rule-soft": "#E9ECF0",
                  "accent": "#2B5C8A", "accent-ink": "#1F4568", "accent-wash": "#E2ECF5",
                  "mark": "#D8E6F2", "mark-ink": "#173047", "warn": "#9A3B33",
                  "pos": "#2B5F8C", "neg": "#B5651D", "mixed": "#8A6A12",
                  "neutral": "#6A727D", "none": "#C6CBD2"},
        "dark": {"ground": "#12161B", "surface": "#1A1F26", "surface-2": "#20262E",
                 "ink": "#E9EDF2", "ink-2": "#A3ABB6", "ink-3": "#868E99",
                 "rule": "#2C333C", "rule-soft": "#242A32",
                 "accent": "#6FA8DC", "accent-ink": "#95C2E8", "accent-wash": "#1B2A38",
                 "mark": "#26384A", "mark-ink": "#D6E6F5", "warn": "#D18B80",
                 "pos": "#5FA3CC", "neg": "#D98F4A", "mixed": "#D5B860",
                 "neutral": "#9FA7B2", "none": "#3B424B"},
    },
}


# ------------------------------------------------------------------ colour

def parse_hex(s):
    s = str(s).strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", s or ""):
        return None
    return tuple(int(s[i:i + 2], 16) / 255 for i in (0, 2, 4))


def to_hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02X}" for c in rgb)


def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    r, g, b = (_lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """WCAG contrast ratio between two colours, 1.0 to 21.0."""
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def deuter(rgb):
    """Deuteranopia simulation (Machado et al., severity 1.0), in linear light."""
    r, g, b = (_lin(c) for c in rgb)
    m = ((0.367322, 0.860646, -0.227968),
         (0.280085, 0.672501, 0.047413),
         (-0.011820, 0.042940, 0.968881))
    out = [sum(mi[j] * v for j, v in enumerate((r, g, b))) for mi in m]
    def unlin(c):
        c = max(0.0, min(1.0, c))
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return tuple(unlin(c) for c in out)


def oklab(rgb):
    r, g, b = (_lin(c) for c in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def delta_e(a, b):
    """OKLab distance, x100 - the same scale the palette guidance uses."""
    return 100 * math.dist(oklab(a), oklab(b))


CHECKS = [
    # (label, foreground token, background token, minimum, why)
    ("body text", "ink", "ground", 4.5, "the text everything is read in"),
    ("body on card", "ink", "surface", 4.5, "most text sits on a card, not the ground"),
    ("secondary ink", "ink-2", "surface", 4.5, "definitions and note bodies"),
    ("muted ink", "ink-3", "surface", 3.0, "captions and provenance lines"),
    ("accent ink", "accent-ink", "accent-wash", 4.5, "tags and code ids"),
    ("accent mark", "accent", "surface-2", 3.0, "the bars on the findings page"),
    ("pos mark", "pos", "surface", 3.0, "valence marks are marks, not text"),
    ("neg mark", "neg", "surface", 3.0, ""),
    ("mixed mark", "mixed", "surface", 3.0, ""),
]


def validate(theme):
    """Every readability check, computed. Returns (problems, notes)."""
    bad, notes = [], []
    for mode in ("light", "dark"):
        cols = theme.get(mode) or {}
        missing = [t for t in TOKENS if not parse_hex(cols.get(t))]
        if missing:
            bad.append(f"{mode}: not a colour - {', '.join(missing[:6])}")
            continue
        for label, fg, bg, need, _ in CHECKS:
            got = contrast(parse_hex(cols[fg]), parse_hex(cols[bg]))
            if got < need:
                bad.append(f"{mode}: {label} {got:.1f}:1, needs {need}:1 "
                           f"({cols[fg]} on {cols[bg]})")
            elif got < need + 0.6:
                notes.append(f"{mode}: {label} only just passes at {got:.1f}:1")
        # pos and neg carry OPPOSITE meanings; a reader who cannot separate them
        # is reading the opposite finding, so this one is not a style preference.
        d = delta_e(deuter(parse_hex(cols["pos"])), deuter(parse_hex(cols["neg"])))
        if d < 8:
            bad.append(f"{mode}: pos and neg are {d:.1f} apart under deuteranopia "
                       f"(need 8) - they would read as the same colour")
        elif d < 12:
            notes.append(f"{mode}: pos/neg separation is thin at {d:.1f} under deuteranopia")
        # mixed is a softer requirement, and deliberately so. Deuteranopia collapses
        # hue onto roughly one blue-yellow axis, so once pos and neg hold the two
        # poles there is no third hue left for mixed - every candidate lands on top
        # of one of them. It is separated by the legend, by its fixed position in
        # the stack, and by the stripe the stylesheet gives it, which is what the
        # colour cannot do alone.
        for other in ("pos", "neg"):
            dm = delta_e(deuter(parse_hex(cols["mixed"])), deuter(parse_hex(cols[other])))
            if dm < 8:
                notes.append(
                    f"{mode}: mixed sits {dm:.1f} from {other} under deuteranopia - "
                    f"told apart by the stripe and the legend, not by colour")
    return bad, notes


# ------------------------------------------------------------------ storage

def path_of(root):
    return os.path.join(os.path.abspath(root), "theme.json")


def load(root):
    p = path_of(root)
    if os.path.exists(p):
        try:
            t = json.load(open(p, encoding="utf-8"))
            if t.get("light") and t.get("dark"):
                return t
        except (json.JSONDecodeError, OSError):
            pass
    return BUILTIN["default"]


def save(root, theme):
    p = path_of(root)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(theme, f, indent=1)
    os.replace(tmp, p)
    return p


MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
        ".ico": "image/x-icon"}


def set_favicon(theme, path):
    ext = os.path.splitext(path)[1].lower()
    if ext not in MIME:
        raise SystemExit(f"favicon must be one of {', '.join(sorted(MIME))}")
    raw = open(path, "rb").read()
    if len(raw) > 200_000:
        raise SystemExit(f"{path} is {len(raw)//1024}KB - it is inlined into every "
                         "page, so use something under 200KB")
    theme["favicon"] = (f"data:{MIME[ext]};base64,"
                        + base64.b64encode(raw).decode("ascii"))
    theme["favicon_from"] = os.path.basename(path)
    return len(raw)


# ------------------------------------------------------------------ output

def css_vars(theme):
    """The custom-property block the pages open their stylesheet with."""
    fonts = {**DEFAULT_FONTS, **(theme.get("fonts") or {})}
    def block(mode):
        cols = theme.get(mode) or {}
        return "".join(f"  --{t}:{cols.get(t, '#888888')};\n" for t in TOKENS)
    return (":root{\n  color-scheme:light;\n" + block("light")
            + f"  --body:{fonts['body']};\n  --mono:{fonts['mono']};\n}}\n"
            + "@media (prefers-color-scheme:dark){:root{\n  color-scheme:dark;\n"
            + block("dark") + "}}\n")


def head_extra(theme):
    """Anything that belongs in <head> beyond the stylesheet."""
    out = ""
    if theme.get("favicon"):
        out += f'<link rel="icon" href="{theme["favicon"]}">'
    fam = theme.get("google_fonts")
    if fam:
        out += ('<link rel="preconnect" href="https://fonts.googleapis.com">'
                '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
                f'<link rel="stylesheet" href="{fam}">')
    return out


# ------------------------------------------------------------------ the ask

TASK = """You are choosing a colour theme for a set of research pages, to match a
source the researcher has given you.

Look at the source. If it is an image, read it and take the palette from what is
actually there. If it is a web page, fetch it and take the palette from its own
colours. If it is a list of hex values, those ARE the palette - your job is only to
assign them to roles and fill in the rest around them.

Fill both a light and a dark scheme. Dark is not an inversion of light: pick it
from the same source, restated for a dark surface.

Roles, and what each one is actually for:

  ground        the page behind everything
  surface       a card sitting on the ground
  surface-2     a recess inside a card: an empty bar track, a quote block
  ink           body text. This has to reach 4.5:1 against ground AND surface
  ink-2         secondary text: definitions, note bodies. 4.5:1 on surface
  ink-3         captions and provenance. 3:1 on surface
  rule          hairline borders
  rule-soft     a fainter rule
  accent        the filled part of a bar, and the active border. 3:1 on surface-2
  accent-ink    text on accent-wash. 4.5:1 on accent-wash
  accent-wash   a tinted background behind a tag
  mark          highlight behind a selected passage
  mark-ink      text on top of mark
  warn          destructive actions
  pos neg       favourable and unfavourable. These carry OPPOSITE meanings and
                must stay far apart for a red-green colourblind reader - do not
                make them a plain red and green
  mixed         both at once
  neutral       no attitude expressed
  none          not judged yet - the most recessive colour in the set

Also choose fonts: a body family and a monospace family, as CSS font stacks with
sensible fallbacks. Only name a font you are confident is either a common system
font or available from Google Fonts. If from Google Fonts, give the stylesheet URL.

Reply with JSON only:

{"name": "<a short name for this theme>",
 "fonts": {"body": "<css stack>", "mono": "<css stack>"},
 "google_fonts": "<stylesheet url, or omit>",
 "light": {"ground": "#RRGGBB", ...all nineteen roles...},
 "dark":  {...all nineteen roles...},
 "why": "<one sentence on what you took from the source>"}

Every value must be a six-digit hex colour. Contrast is checked after you answer
and a theme that fails is rejected, so aim clear of the floors rather than at
them."""


def from_source(source, model, root):
    from review import ask
    kind = ("image" if os.path.splitext(source)[1].lower() in MIME
            else "url" if re.match(r"https?://", source) else "palette")
    payload = {"source_kind": kind, "roles": TOKENS}
    tools = None
    if kind == "image":
        p = os.path.abspath(source)
        if not os.path.exists(p):
            raise SystemExit(f"no such image: {p}")
        payload["image_path"] = p
        payload["instruction"] = (
            f"Read the image at {p} with the Read tool and take the palette from it.")
        tools = ["Read"]
    elif kind == "url":
        payload["url"] = source
        payload["instruction"] = (
            f"Fetch {source} with WebFetch and take the palette from that page's "
            "own colours and typography.")
        tools = ["WebFetch"]
    else:
        cols = [c.strip() for c in re.split(r"[,\s]+", source) if c.strip()]
        bad = [c for c in cols if not parse_hex(c)]
        if bad:
            raise SystemExit(f"not colours: {', '.join(bad)}")
        payload["palette"] = [to_hex(parse_hex(c)) for c in cols]
        payload["instruction"] = "Assign these colours to the roles and fill in around them."

    print(f"matching a theme from this {kind}"
          + (f" using the {tools[0]} tool" if tools else " (no model vision needed)"))
    reply, env = ask(payload, model=model, task=TASK, tools=tools, timeout=900)
    theme = {"name": str(reply.get("name") or "custom")[:40],
             "fonts": {**DEFAULT_FONTS, **(reply.get("fonts") or {})},
             "light": reply.get("light") or {}, "dark": reply.get("dark") or {},
             "source": source, "why": str(reply.get("why", ""))[:200]}
    if reply.get("google_fonts"):
        theme["google_fonts"] = reply["google_fonts"]
    return theme, env.get("total_cost_usd") or 0


# ------------------------------------------------------------------ cli

def report(theme, verbose=True):
    bad, notes = validate(theme)
    if verbose:
        print(f"theme: {theme.get('name', 'custom')}"
              + (f"  (from {theme['source']})" if theme.get("source") else ""))
        if theme.get("why"):
            print(f"  {theme['why']}")
        f = {**DEFAULT_FONTS, **(theme.get("fonts") or {})}
        print(f"  body {f['body'][:52]}")
        print(f"  mono {f['mono'][:52]}")
        if theme.get("favicon"):
            print(f"  favicon from {theme.get('favicon_from', 'a file')}")
        for mode in ("light", "dark"):
            cols = theme.get(mode) or {}
            print(f"  {mode:<6} " + " ".join(
                f"{t}={cols.get(t, '?')}" for t in ("ground", "surface", "ink", "accent")))
    for n in notes:
        print(f"  note: {n}")
    for b in bad:
        print(f"  FAIL: {b}")
    if not bad:
        print("  contrast and colourblind checks: all pass")
    return bad


def main():
    ap = argparse.ArgumentParser(description="Choose how the pages look.")
    ap.add_argument("--data", required=True, help="project directory")
    ap.add_argument("--list", action="store_true", help="show the built-in themes")
    ap.add_argument("--set", metavar="NAME", help="use a built-in theme")
    ap.add_argument("--from", dest="src", metavar="SOURCE",
                    help="match an image file, a URL, or a list of hex colours")
    ap.add_argument("--favicon", metavar="FILE", help="use this file as the favicon")
    ap.add_argument("--model", default=None)
    ap.add_argument("--force", action="store_true",
                    help="write a theme even if it fails the readability checks")
    a = ap.parse_args()
    root = os.path.abspath(a.data)
    if not os.path.isdir(root):
        raise SystemExit(f"no such project: {root}")

    if a.list:
        for name, t in BUILTIN.items():
            bad, _ = validate(t)
            print(f"  {name:<10} {t['light']['accent']} / {t['dark']['accent']}"
                  f"   {'ok' if not bad else 'FAILS: ' + bad[0][:60]}")
        print("\n  python theme.py --data <p> --set <name>")
        return

    theme, cost = None, 0
    if a.set:
        if a.set not in BUILTIN:
            raise SystemExit(f"unknown theme {a.set!r} - try --list")
        theme = json.loads(json.dumps(BUILTIN[a.set]))
    elif a.src:
        from model import current
        theme, cost = from_source(a.src, a.model or current(), root)

    if theme is None:                       # no change asked for: show and check
        theme = load(root)
        report(theme)
        if a.favicon:
            n = set_favicon(theme, a.favicon)
            save(root, theme)
            print(f"\nfavicon set from {a.favicon} ({n//1024 or 1}KB, inlined)")
        return

    # carry the existing favicon forward unless a new one is given
    old = load(root)
    if old.get("favicon") and not a.favicon:
        theme["favicon"] = old["favicon"]
        theme["favicon_from"] = old.get("favicon_from", "")
    if a.favicon:
        set_favicon(theme, a.favicon)

    print()
    bad = report(theme)
    if cost:
        print(f"  cost: ${cost:.2f}")
    if bad and not a.force:
        raise SystemExit(
            f"\nnot written - {len(bad)} readability check(s) failed.\n"
            "  A theme that fails these is one somebody cannot read. Try another\n"
            "  source, or pass --force if you know better than the arithmetic.")
    p = save(root, theme)
    print(f"\nwrote {p}")
    print("  rebuild the pages to see it:  python findings.py --data <p> --generate")


if __name__ == "__main__":
    main()
