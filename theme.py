"""Themes: what the pages ship with, and which one a reader gets.

    python theme.py --data ../myproject                       # what is set
    python theme.py --data ../myproject --list                # themes in the project
    python theme.py --data ../myproject --default chalk       # which one opens first
    python theme.py --data ../myproject --from palette.png    # add one from an image
    python theme.py --data ../myproject --from https://…      # add one from a site
    python theme.py --data ../myproject --from "#173C2E,#E8E4D9,#C2703D" --name understory
    python theme.py --data ../myproject --drop understory
    python theme.py --data ../myproject --favicon logo.png

A project ships SEVERAL themes, not one. Every page carries all of them and a
picker in the corner, so the reader chooses - "Match my system" hands control back
to their own light/dark setting. The choice is remembered in localStorage per
reader, and --default only decides which one opens before they choose.

That is the important difference from a build-time theme: a reader who needs high
contrast should not have to ask the author for a rebuild.

TOKENS

Beyond the obvious surfaces and inks, three pairs carry meaning and are worth
knowing about:

    include / exclude   the two halves of a code definition. Green-ish and
                        red-ish deliberately: these are inclusion and exclusion
                        rules, and unlike pos/neg they are never compared to each
                        other in a chart, so hue may carry the distinction.
    pos / neg           favourable and unfavourable. These ARE compared, in
                        stacked bars, so they are blue and orange and are checked
                        against a deuteranopia simulation before shipping.
    series-a / series-b extra chart series beyond the valence pair.

READABILITY IS COMPUTED, NOT TAKEN ON TRUST

Every theme in the project is checked before anything is written: contrast for
text and marks, and pos-against-neg under deuteranopia. A theme that fails is
reported and not written unless you pass --force.
"""
import argparse, base64, collections, json, math, os, re, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

COLOURS = ["ground", "surface", "surface-2", "ink", "ink-2", "ink-3",
           "rule", "rule-soft", "accent", "accent-ink", "accent-wash",
           "include", "include-wash", "exclude", "exclude-wash",
           "pos", "neg", "mixed", "neutral", "none", "series-a", "series-b",
           "mark", "mark-ink", "warn"]
FONTS = ["font-display", "font-body", "font-mono"]
# Not colours: the shape of a box. A site with 3px corners and one with 14px do
# not look alike however well the palette matches, so these travel with a theme.
SHAPE = {"radius": "4px", "radius-sm": "2px", "border": "1px"}

DEFAULT_FONTS = {
    "font-display": '"Palatino Linotype","Book Antiqua",Palatino,'
                    '"Iowan Old Style",Georgia,serif',
    "font-body": '"Segoe UI",-apple-system,BlinkMacSystemFont,'
                 '"Helvetica Neue",Arial,sans-serif',
    "font-mono": 'Consolas,"Cascadia Mono","SF Mono",Menlo,monospace',
}

SHADOW = {
    "light": "0 1px 2px rgba(34,33,42,.05), 0 8px 24px -16px rgba(34,33,42,.22)",
    "dark": "0 1px 2px rgba(0,0,0,.4), 0 8px 24px -16px rgba(0,0,0,.7)",
    "none": "none",
}

# The four the pages ship with. "scheme" tells the browser which system setting
# this theme belongs to, and which one "Match my system" falls back to.
BUILTIN = {
 "light": {"label": "Sarsen", "scheme": "light", "shadow": SHADOW["light"], "tokens": {
    "ground": "#F2F2EF", "surface": "#FFFFFF", "surface-2": "#F8F8F5",
    "ink": "#22212A", "ink-2": "#56545F", "ink-3": "#86848F",
    "rule": "#E0DFDA", "rule-soft": "#EBEAE6",
    "accent": "#6B7233", "accent-ink": "#4E541F", "accent-wash": "#EDEFE0",
    "include": "#4A6B4F", "include-wash": "#E9F0EA",
    "exclude": "#8A4B42", "exclude-wash": "#F4E9E7",
    "pos": "#1F6FB8", "neg": "#C0731F", "mixed": "#8A6A12",
    "neutral": "#6B6976", "none": "#C9C7C0",
    "series-a": "#86848F", "series-b": "#7A4A7E",
    "mark": "#EDE8B8", "mark-ink": "#3F3A12", "warn": "#8A4B42"}},

 "dark": {"label": "Sarsen dark", "scheme": "dark", "shadow": SHADOW["dark"], "tokens": {
    "ground": "#17171B", "surface": "#1F1F25", "surface-2": "#25252C",
    "ink": "#EDECEE", "ink-2": "#A9A7B2", "ink-3": "#8E8C98",
    "rule": "#31313A", "rule-soft": "#292930",
    "accent": "#A8B45C", "accent-ink": "#C3CE84", "accent-wash": "#2A2D1E",
    "include": "#8FB396", "include-wash": "#1E271F",
    "exclude": "#CC9186", "exclude-wash": "#2B1F1D",
    "pos": "#5EA8D8", "neg": "#E0954E", "mixed": "#D9BC63",
    "neutral": "#A5A3AF", "none": "#45444D",
    "series-a": "#9A98A3", "series-b": "#B98BBE",
    "mark": "#4A431C", "mark-ink": "#F0E9BE", "warn": "#CC9186"}},

 "chalk": {"label": "Chalk - high contrast", "scheme": "light",
           "shadow": SHADOW["none"],
           # square corners, a heavier rule and one plain face throughout: the
           # point of this theme is that nothing is soft or decorative
           "shape": {"radius": "0px", "radius-sm": "0px", "border": "2px"},
           "fonts": {"font-display": '"Segoe UI",-apple-system,'
                                     'BlinkMacSystemFont,Arial,sans-serif'},
           "tokens": {
    "ground": "#FFFFFF", "surface": "#FFFFFF", "surface-2": "#F4F4F2",
    "ink": "#0E0E12", "ink-2": "#3A3A44", "ink-3": "#5A5964",
    "rule": "#B9B7B1", "rule-soft": "#D6D4CE",
    "accent": "#4A5416", "accent-ink": "#3A4210", "accent-wash": "#E4E8CE",
    "include": "#2F5237", "include-wash": "#DCE8DF",
    "exclude": "#772F25", "exclude-wash": "#F0DCD8",
    "pos": "#12558F", "neg": "#8F5312", "mixed": "#6B4E0A",
    "neutral": "#4E4D57", "none": "#C2C0BA",
    "series-a": "#5A5964", "series-b": "#5E3462",
    "mark": "#FBF0A8", "mark-ink": "#2E2A08", "warn": "#772F25"}},

 "dusk": {"label": "Dusk", "scheme": "dark", "shadow": SHADOW["dark"],
          # softer corners and a serif body: this one is for reading at length
          "shape": {"radius": "9px", "radius-sm": "5px", "border": "1px"},
          "fonts": {"font-body": 'Charter,"Iowan Old Style",Georgia,'
                                 '"Times New Roman",serif'},
          "tokens": {
    "ground": "#12161B", "surface": "#1A2026", "surface-2": "#212831",
    "ink": "#E4E9EF", "ink-2": "#9FAAB8", "ink-3": "#84909E",
    "rule": "#2B333D", "rule-soft": "#232A33",
    "accent": "#D2A857", "accent-ink": "#E4C282", "accent-wash": "#2E2717",
    "include": "#7FA9A2", "include-wash": "#17262A",
    "exclude": "#C98878", "exclude-wash": "#2A1D1B",
    "pos": "#5EA8D8", "neg": "#E0954E", "mixed": "#D2A857",
    "neutral": "#9AA5B2", "none": "#2B333D",
    "series-a": "#84909E", "series-b": "#B98BBE",
    "mark": "#3A3320", "mark-ink": "#F2E7C0", "warn": "#C98878"}},
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
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def deuter(rgb):
    """Deuteranopia simulation (Machado et al., severity 1.0), in linear light."""
    r, g, b = (_lin(c) for c in rgb)
    m = ((0.367322, 0.860646, -0.227968),
         (0.280085, 0.672501, 0.047413),
         (-0.011820, 0.042940, 0.968881))
    def unlin(c):
        c = max(0.0, min(1.0, c))
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return tuple(unlin(sum(mi[j] * v for j, v in enumerate((r, g, b)))) for mi in m)


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
    return 100 * math.dist(oklab(a), oklab(b))


def from_oklab(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    lin = (+4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
           -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
           -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
    def gamma(c):
        c = max(0.0, min(1.0, c))
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return tuple(gamma(c) for c in lin)


def snap(fg_hex, bg_hex, need, steps=80):
    """Move a colour along its own lightness until it clears `need` against bg.

    A matched palette should not be thrown away because one token missed a floor
    by a tenth - the site's own orange came back at 2.9:1 against white where 3.0
    was wanted. Hue and chroma are kept, so the result is still recognisably the
    colour that was measured; only its lightness moves, and by the smallest step
    that passes.
    """
    fg, bg = parse_hex(fg_hex), parse_hex(bg_hex)
    if fg is None or bg is None or contrast(fg, bg) >= need:
        return fg_hex, None
    L, a, b = oklab(fg)
    darker = luminance(bg) > 0.4      # light background: darken the mark
    for i in range(1, steps + 1):
        t = i / steps
        cand = from_oklab(L * (1 - t) if darker else L + (1 - L) * t, a, b)
        if contrast(cand, bg) >= need:
            return to_hex(cand), round(contrast(cand, bg), 2)
    return ("#000000" if darker else "#FFFFFF"), None


def repair(name, spec):
    """Nudge any token that misses a floor, and say which ones moved."""
    t = spec.get("tokens") or {}
    moved = []
    for label, fg, bg, need in CHECKS:
        if not (parse_hex(t.get(fg)) and parse_hex(t.get(bg))):
            continue
        if contrast(parse_hex(t[fg]), parse_hex(t[bg])) >= need:
            continue
        new, got = snap(t[fg], t[bg], need)
        if new.upper() != str(t[fg]).upper():
            moved.append(f"{fg} {t[fg]} -> {new} for {label}"
                         + (f" ({got}:1)" if got else ""))
            t[fg] = new
    return moved


CHECKS = [
    ("body text on ground", "ink", "ground", 4.5),
    ("body text on a card", "ink", "surface", 4.5),
    ("secondary ink", "ink-2", "surface", 4.5),
    ("muted ink", "ink-3", "surface", 3.0),
    ("accent ink on its wash", "accent-ink", "accent-wash", 4.5),
    ("accent mark", "accent", "surface-2", 3.0),
    ("include text on its wash", "include", "include-wash", 4.5),
    ("exclude text on its wash", "exclude", "exclude-wash", 4.5),
    ("pos mark", "pos", "surface", 3.0),
    ("neg mark", "neg", "surface", 3.0),
    ("mixed mark", "mixed", "surface", 3.0),
]


def validate_one(name, spec):
    bad, notes = [], []
    t = spec.get("tokens") or {}
    missing = [k for k in COLOURS if not parse_hex(t.get(k))]
    if missing:
        return [f"{name}: not colours - {', '.join(missing[:6])}"], []
    for label, fg, bg, need in CHECKS:
        got = contrast(parse_hex(t[fg]), parse_hex(t[bg]))
        if got < need:
            bad.append(f"{name}: {label} {got:.1f}:1, needs {need}:1 "
                       f"({t[fg]} on {t[bg]})")
        elif got < need + 0.5:
            notes.append(f"{name}: {label} only just passes at {got:.1f}:1")
    # pos and neg sit side by side in a stacked bar and mean opposite things
    d = delta_e(deuter(parse_hex(t["pos"])), deuter(parse_hex(t["neg"])))
    if d < 8:
        bad.append(f"{name}: pos and neg are {d:.1f} apart under deuteranopia "
                   f"(need 8) - a reader would get the opposite finding")
    elif d < 12:
        notes.append(f"{name}: pos/neg separation is thin at {d:.1f}")
    # Deuteranopia collapses hue onto roughly one blue-yellow axis, so once pos and
    # neg hold the poles there is no third hue left for mixed. It is separated by
    # its stripe, the legend, and its fixed place in the stack - not by colour.
    for other in ("pos", "neg"):
        dm = delta_e(deuter(parse_hex(t["mixed"])), deuter(parse_hex(t[other])))
        if dm < 8:
            notes.append(f"{name}: mixed sits {dm:.1f} from {other} under "
                         f"deuteranopia - told apart by its stripe and the legend")
    return bad, notes


def validate(project):
    bad, notes = [], []
    for name, spec in (project.get("themes") or {}).items():
        b, n = validate_one(name, spec)
        bad += b
        notes += n
    return bad, notes


# ---------------------------------------------------------------- measuring

def _get(url, timeout=20, cap=900_000):
    import urllib.request
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; codeframe theme matcher)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(cap).decode("utf-8", errors="replace")


LINK_TAG = re.compile(r"<link[^>]+>", re.I)
IS_SHEET = re.compile(r"rel\s*=\s*[\"']?stylesheet", re.I)
HREF = re.compile(r"href\s*=\s*[\"']([^\"']+)", re.I)
STYLE_TAG = re.compile(r"<style[^>]*>(.*?)</style>", re.S | re.I)
HEXLIT = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
RGBLIT = re.compile(r"rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)")
FONTDECL = re.compile(r"font-family\s*:\s*([^;}]+)", re.I)
RADIUSDECL = re.compile(r"border-radius\s*:\s*([^;}]+)", re.I)


def measure_site(url, max_sheets=8):
    """Read a site's own stylesheets and count what it actually uses.

    A model asked to match a site it cannot see returns a plausible palette
    rather than the real one. Asked to match this project's own case-study page
    it produced a blue accent for a site that uses olive, an almost-black ink for
    a site whose text is forest green, and named two typefaces the site does not
    load - and said in its own reasoning that the stylesheet was not reachable.

    The colours are sitting in the CSS. Fetching and counting them is cheap and
    exact, so the model is handed measurements and left to do the part it is good
    at, which is deciding which measured colour should play which role.
    """
    from urllib.parse import urljoin
    html = _get(url)
    sheets = []
    for tag in LINK_TAG.findall(html):
        if IS_SHEET.search(tag):
            m = HREF.search(tag)
            if m:
                sheets.append(urljoin(url, m.group(1)))
    css = "\n".join(STYLE_TAG.findall(html))
    read = 0
    for href in sheets[:max_sheets]:
        try:
            css += "\n" + _get(href)
            read += 1
        except Exception:
            continue

    colours = collections.Counter()
    for m in HEXLIT.finditer(css):
        rgb = parse_hex(m.group(1))
        if rgb:
            colours[to_hex(rgb)] += 1
    for m in RGBLIT.finditer(css):
        vals = [int(v) for v in m.groups()]
        if all(v <= 255 for v in vals):
            colours[to_hex(tuple(v / 255 for v in vals))] += 1

    # Which selector a family is declared on decides whether it is the body face
    # or the heading face, and a bare count cannot tell them apart - on this
    # project's own site Barlow is declared fewer times than it is used, and a
    # count alone got body and display the wrong way round.
    fonts, where = collections.Counter(), {}
    for m in FONTDECL.finditer(css):
        first = m.group(1).split(",")[0].strip().strip("\"'")
        if not first or first.startswith(("var(", "inherit", "initial", "unset")):
            continue
        fonts[first] += 1
        head = css[max(0, m.start() - 160):m.start()]
        sel = head.rsplit("}", 1)[-1].rsplit("{", 1)[0].strip()
        sel = re.sub(r"\s+", " ", sel)[-70:]
        if sel:
            where.setdefault(first, [])
            if sel not in where[first] and len(where[first]) < 4:
                where[first].append(sel)

    # Modern sites name their faces in custom properties - --global-body-font-family,
    # --heading-font, --font-sans - and that says outright which is body and which
    # is display, where a declaration count only guesses.
    named = {}
    for m in re.finditer(r"--([a-z0-9-]*(?:font|type)[a-z0-9-]*)\s*:\s*([^;}]+)",
                         css, re.I):
        key, val = m.group(1).lower(), m.group(2).strip().strip("\"'")
        # a family, not a size or a weight: starts with a name and carries no
        # lengths or calc, which is what --*-font-size is full of
        if (not val or val.startswith("var(") or val[0].isdigit()
                or re.search(r"clamp\(|calc\(|[0-9](px|rem|em)\b|^\d", val)
                or not re.match(r"[A-Za-z\"']", val)):
            continue
        named.setdefault(key, val[:90])

    radii = collections.Counter(m.group(1).strip()[:16]
                                for m in RADIUSDECL.finditer(css))
    return {"url": url, "stylesheets_read": read, "css_bytes": len(css),
            "colours_by_frequency": [{"hex": h, "uses": n}
                                     for h, n in colours.most_common(24)],
            "fonts_by_frequency": [{"family": f, "uses": n,
                                    "declared_on": where.get(f, [])}
                                   for f, n in fonts.most_common(8)],
            "font_variables_declared_by_the_site": named,
            "radius_by_frequency": [{"value": v, "uses": n}
                                    for v, n in radii.most_common(5)]}


# ------------------------------------------------------------------ storage

def path_of(root):
    return os.path.join(os.path.abspath(root), "theme.json")


def blank():
    return {"default": "light", "fonts": dict(DEFAULT_FONTS), "shape": dict(SHAPE),
            "themes": json.loads(json.dumps(BUILTIN))}


def load(root):
    p = path_of(root)
    if os.path.exists(p):
        try:
            t = json.load(open(p, encoding="utf-8"))
            if t.get("themes"):
                t.setdefault("fonts", dict(DEFAULT_FONTS))
                t.setdefault("shape", dict(SHAPE))
                t.setdefault("default", next(iter(t["themes"])))
                return t
        except (json.JSONDecodeError, OSError):
            pass
    return blank()


def save(root, project):
    p = path_of(root)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(project, f, indent=1)
    os.replace(tmp, p)
    return p


MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
        ".ico": "image/x-icon"}


def set_favicon(project, path):
    ext = os.path.splitext(path)[1].lower()
    if ext not in MIME:
        raise SystemExit(f"favicon must be one of {', '.join(sorted(MIME))}")
    raw = open(path, "rb").read()
    if len(raw) > 200_000:
        raise SystemExit(f"{path} is {len(raw)//1024}KB - it is inlined into every "
                         "page, so use something under 200KB")
    project["favicon"] = f"data:{MIME[ext]};base64," + base64.b64encode(raw).decode()
    project["favicon_from"] = os.path.basename(path)
    return len(raw)


# ------------------------------------------------------------------ output

def css_vars(project):
    """Tokens for every theme: the default on :root, the rest behind data-theme.

    The dark block is guarded with :root:not([data-theme]) so a reader's explicit
    choice is not overridden by their system setting - the picker has to win in
    both directions or "Sarsen" is unusable on a machine set to dark.
    """
    themes = project.get("themes") or BUILTIN
    dflt = project.get("default") if project.get("default") in themes else next(iter(themes))

    def body(spec):
        """Everything a theme controls - colours, type and shape alike.

        Typography and corner radius live in the theme, not on :root. Emitting
        them once meant switching theme repainted the page and changed nothing
        else, so a serif theme and a square high-contrast theme were the same
        page in different colours. A theme that does not name its own falls back
        to the project's, and then to the defaults.
        """
        t = spec.get("tokens") or {}
        fonts = {**DEFAULT_FONTS, **(project.get("fonts") or {}),
                 **(spec.get("fonts") or {})}
        shape = {**SHAPE, **(project.get("shape") or {}), **(spec.get("shape") or {})}
        return ("".join(f"  --{k}:{t.get(k, '#888888')};\n" for k in COLOURS)
                + f"  --shadow:{spec.get('shadow', SHADOW['light'])};\n"
                + "".join(f"  --{k}:{v};\n" for k, v in fonts.items())
                + "".join(f"  --{k}:{v};\n" for k, v in shape.items()))

    css = (":root{\n  color-scheme:" + themes[dflt].get("scheme", "light") + ";\n"
           + body(themes[dflt]) + "}\n")
    for name, spec in themes.items():
        css += (f'[data-theme="{name}"]{{\n  color-scheme:'
                + spec.get("scheme", "light") + ";\n" + body(spec) + "}\n")
    # a reader who has chosen nothing follows their system
    sysdark = next((n for n, s in themes.items()
                    if s.get("scheme") == "dark"), None)
    if sysdark and themes[dflt].get("scheme") != "dark":
        css += ("@media (prefers-color-scheme:dark){:root:not([data-theme]){\n"
                "  color-scheme:dark;\n" + body(themes[sysdark]) + "}}\n")
    return css


HEAD_JS = """
(function(){try{
  var k=%s, u=null;
  try{u=new URLSearchParams(location.search).get('theme');}catch(e){}
  var v=u;
  if(!v){try{v=localStorage.getItem(k);}catch(e){}}
  if(u){try{localStorage.setItem(k,u);}catch(e){}}
  if(v&&v!=='system')document.documentElement.setAttribute('data-theme',v);
}catch(e){}})();
"""


def head_script(key="codeframe-theme"):
    """Apply the reader's theme before the page paints, and without storage.

    Two problems, one script. In <head> it runs before anything is drawn, so the
    page does not flash the default theme and then correct itself.

    And it reads ?theme= before localStorage, because localStorage is per-origin:
    open these pages from a file:// path or inside a preview pane and each one can
    get its own empty store, so a choice made on the codebook is simply not there
    when you reach the findings. The picker stamps the current theme onto the nav
    links, so following one carries the choice whether storage works or not.
    """
    return f"<script>{HEAD_JS % json.dumps(key)}</script>"


def head_extra(project, key="codeframe-theme"):
    out = head_script(key)
    if project.get("favicon"):
        out += f'<link rel="icon" href="{project["favicon"]}">'
    # every theme is in the page, so every theme's webfont must be available -
    # linking only the default's leaves the others falling back silently
    urls = []
    for u in [project.get("google_fonts")] + [
            (t or {}).get("google_fonts") for t in (project.get("themes") or {}).values()]:
        if u and u not in urls:
            urls.append(u)
    if urls:
        out += ('<link rel="preconnect" href="https://fonts.googleapis.com">'
                '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
        out += "".join(f'<link rel="stylesheet" href="{u}">' for u in urls)
    return out


PICKER_CSS = """
.themepick{display:flex;align-items:center;gap:7px}
.themepick label{font-family:var(--font-mono);font-size:10px;letter-spacing:.09em;
 text-transform:uppercase;color:var(--ink-3)}
.themepick select{font:13px var(--font-body);color:var(--ink);background:var(--surface);
 border:1px solid var(--rule);border-radius:3px;padding:4px 7px}
"""

PICKER_JS = """
(function(){
  var root=document.documentElement, KEY=%s,
      sel=document.getElementById('theme');
  if(!sel) return;
  // the head script has already applied the theme; start from what it decided
  var current=root.getAttribute('data-theme')||'system';
  function stamp(v){
    // carry the choice on every in-site link, so it survives a missing or
    // per-file localStorage - which is what happens over file://
    [].slice.call(document.querySelectorAll('nav a[href]')).forEach(function(a){
      var h=a.getAttribute('href').split('?')[0];
      a.setAttribute('href', (v&&v!=='system')
        ? h+'?theme='+encodeURIComponent(v) : h);
    });
  }
  function set(v){
    if(v&&v!=='system'){root.setAttribute('data-theme',v);}
    else{root.removeAttribute('data-theme');}
    try{localStorage.setItem(KEY,v);}catch(e){}
    stamp(v);
  }
  sel.value=current;
  // the picker sits above the nav, so at parse time the links do not exist yet;
  // stamp them once the document is complete or the first click loses the theme
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',function(){stamp(current);});
  } else { stamp(current); }
  sel.addEventListener('change',function(){set(sel.value);});
})();
"""


def picker(project, key="codeframe-theme"):
    """The control the reader uses, and the script that remembers their choice."""
    themes = project.get("themes") or BUILTIN
    opts = '<option value="system">Match my system</option>' + "".join(
        f'<option value="{n}">{(s.get("label") or n)}</option>'
        for n, s in themes.items())
    return (f'<div class="themepick"><label for="theme">Theme</label>'
            f'<select id="theme">{opts}</select></div>'
            f'<script>{PICKER_JS % json.dumps(key)}</script>')


# ------------------------------------------------------------------ the ask

TASK = """You are designing one colour theme for a set of research pages, matched
to a source the researcher has given you.

Look at the source. If it is an image, read it and take the palette from what is
actually there. If it is a web page, fetch it and take the palette from its own
colours and typography. If it is a list of hex values, those ARE the palette - your
job is only to assign them to roles and fill in sensibly around them.

Say whether the result is a light theme or a dark one, then give every token.

  ground        the page behind everything
  surface       a card on the ground
  surface-2     a recess inside a card: an empty bar track, a quote block
  ink           body text. Must reach 4.5:1 on BOTH ground and surface
  ink-2         secondary text. 4.5:1 on surface
  ink-3         captions and provenance. 3:1 on surface
  rule          hairline borders
  rule-soft     a fainter rule
  accent        the filled part of a bar. 3:1 on surface-2
  accent-ink    text on accent-wash. 4.5:1 on accent-wash
  accent-wash   a tinted background behind a tag
  include       text of an inclusion rule. 4.5:1 on include-wash
  include-wash  its background
  exclude       text of an exclusion rule. 4.5:1 on exclude-wash
  exclude-wash  its background
  pos neg       favourable and unfavourable. These sit side by side in a stacked
                bar and mean OPPOSITE things, so they must stay far apart for a
                red-green colourblind reader. Do not make them red and green -
                a blue and an orange is the reliable choice
  mixed         both at once
  neutral       no attitude expressed
  none          not judged yet - the most recessive colour in the set
  series-a      an extra chart series
  series-b      another
  mark          highlight behind a selected passage
  mark-ink      text on top of mark
  warn          destructive actions

Also give the SHAPE of a box, matched to the source: "radius" for cards and
figures, "radius-sm" for small chips and bars, "border" for hairline width. Use
CSS lengths, e.g. "4px". A site with square corners and one with pill-shaped
buttons are not the same house style even with the same palette.

Reply with JSON only:

{"name": "<one lowercase word, no spaces>",
 "label": "<a short human name for the picker>",
 "scheme": "<light or dark>",
 "tokens": {"ground": "#RRGGBB", ...every token above...},
 "fonts": {"font-display": "<css stack>", "font-body": "<css stack>",
           "font-mono": "<css stack>"},
 "shape": {"radius": "4px", "radius-sm": "2px", "border": "1px"},
 "google_fonts": "<stylesheet url, or omit>",
 "why": "<one sentence on what you took from the source>"}

Every colour must be six-digit hex. Contrast and colourblind separation are
checked after you answer and a theme that fails is rejected, so aim clear of the
floors rather than at them."""


def from_source(source, model):
    from review import ask
    kind = ("image" if os.path.splitext(source)[1].lower() in MIME
            else "url" if re.match(r"https?://", source) else "palette")
    payload = {"source_kind": kind, "tokens_required": COLOURS}
    tools = None
    if kind == "image":
        p = os.path.abspath(source)
        if not os.path.exists(p):
            raise SystemExit(f"no such image: {p}")
        payload["image_path"] = p
        payload["instruction"] = f"Read the image at {p} and take the palette from it."
        tools = ["Read"]
    elif kind == "url":
        payload["url"] = source
        try:
            m = measure_site(source)
        except Exception as e:
            raise SystemExit(
                f"could not read {source}: {e}\n"
                "  If the site is behind a login, save a screenshot and use\n"
                "  --from that-image.png instead.")
        payload["measured"] = m
        payload["instruction"] = (
            "These are the colours, typefaces and corner radii counted in that "
            "site's own stylesheets, most-used first. Use THESE - do not invent a "
            "palette and do not fetch the page. Decide which measured colour plays "
            "which role, and derive only the tokens the site has no colour for. "
            "Name the font stacks after the families measured, with fallbacks.")
        print(f"  read {m['stylesheets_read']} stylesheet(s), "
              f"{m['css_bytes']:,} bytes of CSS")
        if m["colours_by_frequency"]:
            print("  most-used colours: " + " ".join(
                c["hex"] for c in m["colours_by_frequency"][:6]))
        if m["fonts_by_frequency"]:
            print("  typefaces: " + ", ".join(
                f["family"] for f in m["fonts_by_frequency"][:4]))
    else:
        cols = [c.strip() for c in re.split(r"[,\s]+", source) if c.strip()]
        bad = [c for c in cols if not parse_hex(c)]
        if bad:
            raise SystemExit(f"not colours: {', '.join(bad)}")
        payload["palette"] = [to_hex(parse_hex(c)) for c in cols]
        payload["instruction"] = "Assign these to the roles and fill in around them."

    print(f"matching a theme from this {kind}"
          + (f", using the {tools[0]} tool to see it" if tools else ""))
    reply, env = ask(payload, model=model, task=TASK, tools=tools, timeout=900)
    name = re.sub(r"[^a-z0-9]", "", str(reply.get("name") or "custom").lower())[:20]
    spec = {"label": str(reply.get("label") or name)[:40],
            "scheme": "dark" if str(reply.get("scheme")) == "dark" else "light",
            "shadow": SHADOW["dark" if reply.get("scheme") == "dark" else "light"],
            "tokens": reply.get("tokens") or {},
            "source": source, "why": str(reply.get("why", ""))[:200]}
    return name or "custom", spec, reply, env.get("total_cost_usd") or 0


# ------------------------------------------------------------------ cli

def show(project):
    themes = project.get("themes") or {}
    print(f"default: {project.get('default')}   ({len(themes)} themes ship in every page)")
    if project.get("favicon"):
        print(f"favicon: {project.get('favicon_from', 'set')}")
    f = {**DEFAULT_FONTS, **(project.get("fonts") or {})}
    for k in FONTS:
        print(f"  {k:<13} {f[k][:56]}")
    sh = {**SHAPE, **(project.get("shape") or {})}
    print(f"  {'shape':<13} " + "  ".join(f"{k} {v}" for k, v in sh.items()))
    print()
    for name, spec in themes.items():
        bad, _ = validate_one(name, spec)
        t = spec.get("tokens") or {}
        mark = "*" if name == project.get("default") else " "
        own = []
        if spec.get("fonts"):
            own.append((spec["fonts"].get("font-body") or "?").split(",")[0].strip("'\""))
        if spec.get("shape"):
            own.append("r" + str(spec["shape"].get("radius", "?")))
        print(f"{mark} {name:<11} {spec.get('label', name)[:22]:<24} "
              f"{spec.get('scheme', 'light'):<6} {t.get('ground', '?')} "
              f"{t.get('accent', '?')}  {'ok' if not bad else 'FAILS':<6}"
              + ("  " + " ".join(own) if own else ""))


def main():
    ap = argparse.ArgumentParser(description="Themes the pages ship with.")
    ap.add_argument("--data", required=True)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--default", metavar="NAME", help="which theme opens first")
    ap.add_argument("--from", dest="src", metavar="SOURCE",
                    help="add a theme from an image, a URL, or hex colours")
    ap.add_argument("--name", help="with --from: what to call it")
    ap.add_argument("--drop", metavar="NAME", help="remove a theme")
    ap.add_argument("--reset", action="store_true", help="back to the four built-ins")
    ap.add_argument("--favicon", metavar="FILE")
    ap.add_argument("--model", default=None)
    ap.add_argument("--force", action="store_true",
                    help="write even if a readability check fails")
    a = ap.parse_args()
    root = os.path.abspath(a.data)
    if not os.path.isdir(root):
        raise SystemExit(f"no such project: {root}")

    project = blank() if a.reset else load(root)
    changed, cost = a.reset, 0

    if a.src:
        from model import current
        name, spec, reply, cost = from_source(a.src, a.model or current())
        name = re.sub(r"[^a-z0-9]", "", (a.name or name).lower()) or "custom"
        for m in repair(name, spec):
            print(f"  adjusted: {m}")
        bad, notes = validate_one(name, spec)
        for n in notes:
            print(f"  note: {n}")
        for b in bad:
            print(f"  FAIL: {b}")
        if bad and not a.force:
            raise SystemExit(
                f"\nnot added - {len(bad)} readability check(s) failed.\n"
                "  Try another source, or --force if you know better than the maths.")
        # type and shape belong to the theme, so adding a second one does not
        # quietly restyle the first
        if reply.get("fonts"):
            spec["fonts"] = {k: v for k, v in reply["fonts"].items() if k in FONTS}
        if reply.get("google_fonts"):
            spec["google_fonts"] = reply["google_fonts"]
        if isinstance(reply.get("shape"), dict):
            keep = {k: str(v)[:12] for k, v in reply["shape"].items()
                    if k in SHAPE and re.fullmatch(r"[0-9.]+(px|rem|em)", str(v))}
            if keep:
                spec["shape"] = keep
        project["themes"][name] = spec
        project["default"] = name
        changed = True
        print(f"\nadded theme {name!r} ({spec['label']}) and made it the default")
        if spec.get("why"):
            print(f"  {spec['why']}")

    if a.drop:
        if a.drop not in project.get("themes", {}):
            raise SystemExit(f"no theme called {a.drop!r}")
        if len(project["themes"]) == 1:
            raise SystemExit("that is the only theme left")
        del project["themes"][a.drop]
        if project.get("default") == a.drop:
            project["default"] = next(iter(project["themes"]))
        changed = True
        print(f"dropped {a.drop!r}")

    if a.default:
        if a.default not in project.get("themes", {}):
            raise SystemExit(f"no theme called {a.default!r} - try --list")
        project["default"] = a.default
        changed = True

    if a.favicon:
        n = set_favicon(project, a.favicon)
        changed = True
        print(f"favicon set from {a.favicon} ({n // 1024 or 1}KB, inlined)")

    if a.list or not changed:
        show(project)
        bad, notes = validate(project)
        for n in notes:
            print(f"  note: {n}")
        for b in bad:
            print(f"  FAIL: {b}")
        if not bad:
            print("\n  every theme passes contrast and colourblind checks")
        if not changed:
            return

    bad, _ = validate(project)
    if bad and not a.force:
        raise SystemExit(f"\nnot written - {len(bad)} check(s) failed. "
                         "Fix them, or pass --force.")
    p = save(root, project)
    if cost:
        print(f"  cost: ${cost:.2f}")
    print(f"\nwrote {p}")
    print("  rebuild to see it:  python findings.py --data <p> --generate")


if __name__ == "__main__":
    main()
