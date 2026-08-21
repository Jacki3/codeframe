"""Choose which model the model-backed steps use.

    python model.py                 # what is set, and what else is available
    python model.py sonnet          # set it
    python model.py opus --check    # set it and prove the CLI accepts it
    python model.py --clear         # back to the default

The choice is written to config.json beside these scripts and read by every step
that can call a model: --review, valence.py, --discussion --summarise, and
findings.py --add. Any of them still takes --model to override it for one run.

Requests go through the Claude Code CLI, not the API, so there is no key to set
and the short aliases below work as well as the full ids. The CLI resolves an
alias to the current model of that family, which means "opus" keeps working after
a new Opus is released, while a pinned id keeps a study reproducible. For work you
intend to write up, pin the id.

WHICH TO PICK

Nothing here asks a model to do arithmetic or to write a finding - it proposes a
column mapping, a chart spec, a valence, a summary paragraph - so the cheaper
models are not obviously worse at these jobs. Sonnet is the default because it
has been enough for all four. Reach for Opus when a mapping is genuinely
ambiguous or a corpus is unusual; reach for Haiku when you are re-running a
valence pass over hundreds of excerpts and cost is the constraint.
"""
import argparse, json, os, shutil, subprocess, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")
DEFAULT = "sonnet"

# Cached from the Claude API model list on 2026-06-24; prices are per million
# tokens on the first-party API and are here for relative scale, not billing -
# the CLI bills against whatever plan you are signed in with.
KNOWN = [
    ("fable",  "claude-fable-5",       "1M",   "$10 / $50",
     "most capable; for the hardest reasoning"),
    ("opus",   "claude-opus-5",        "1M",   "$5 / $25",
     "strong general reasoning"),
    ("sonnet", "claude-sonnet-5",      "1M",   "$3 / $15",
     "the default here; enough for every step"),
    ("haiku",  "claude-haiku-4-5",     "200K", "$1 / $5",
     "cheapest; for large repeated passes"),
]


def current():
    """The configured model, for the other scripts to use as their default."""
    if os.path.exists(CONFIG):
        try:
            with open(CONFIG, encoding="utf-8") as f:
                return (json.load(f).get("model") or DEFAULT).strip()
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT


def save(name):
    tmp = CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"model": name}, f, indent=1)
    os.replace(tmp, CONFIG)


def auth(timeout=60):
    """Whether the CLI is signed in. Free, instant, and sends nothing.

    `claude auth status` answers locally and exits non-zero when signed out, so
    this is the check to run before anything that would cost money - and the one
    to run first when a step fails, because "not logged in" is by far the most
    likely reason.
    """
    exe = shutil.which("claude")
    if not exe:
        return None, "the claude CLI is not on PATH"
    try:
        p = subprocess.run([exe, "auth", "status"], capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
    except (subprocess.TimeoutExpired, OSError):
        return None, "could not run `claude auth status`"
    try:
        d = json.loads(p.stdout)
    except (json.JSONDecodeError, TypeError):
        return None, (p.stdout or p.stderr or "").strip()[:120] or "no answer"
    if not d.get("loggedIn"):
        return False, "signed out"
    who = d.get("email") or d.get("authMethod") or "signed in"
    plan = d.get("subscriptionType")
    return True, f"{who}" + (f" ({plan})" if plan else "")


def check(name, timeout=180):
    """Ask the CLI to answer something trivial, and see whether it accepts the model.

    A model name is not validated until something is sent, and the worst moment
    to discover a typo is part-way through a valence pass over three hundred
    excerpts.
    """
    exe = shutil.which("claude")
    if not exe:
        return False, "the claude CLI was not found on PATH"
    # Signed-out is the likeliest reason and costs nothing to rule out, so rule it
    # out before sending a request that would be billed.
    signed_in, who = auth()
    if signed_in is False:
        return False, "not signed in - run  claude auth login"
    try:
        p = subprocess.run([exe, "-p", "--output-format", "json", "--model", name],
                           input="Reply with the single word: ok",
                           capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return False, f"no answer within {timeout}s"
    # The envelope explains itself; the exit code does not. Checking the code
    # first turns "Not logged in - please run /login" into a wall of JSON.
    env = None
    if (p.stdout or "").strip():
        try:
            env = json.loads(p.stdout)
        except json.JSONDecodeError:
            env = None
    if env is not None and env.get("is_error"):
        return False, str(env.get("result") or env.get("terminal_reason"))[:200]
    if p.returncode != 0:
        return False, (p.stderr or p.stdout or "").strip().splitlines()[-1][:160]
    if env is None:
        return False, "the CLI returned something that was not JSON"
    used = ", ".join(sorted(env.get("modelUsage") or {})) or "unknown"
    cost = env.get("total_cost_usd") or 0
    return True, f"answered as {used}" + (f" (${cost:.2f})" if cost else "")


def show(name):
    ok, who = auth()
    state = {True: "signed in", False: "SIGNED OUT", None: "unknown"}[ok]
    print(f"account: {state} - {who}")
    if ok is not True:
        print("  run  claude auth login   (or  python model.py --login)")
        print("  Only four steps need this; everything else runs without it.")
    print()
    print(f"model: {name}" + ("   (default)" if name == DEFAULT else ""))
    print(f"  set in {CONFIG}" if os.path.exists(CONFIG) else "  no config.json yet")
    print()
    print(f"  {'alias':<8} {'id':<22} {'context':<8} {'in / out per Mtok':<18} ")
    for alias, mid, ctx, price, why in KNOWN:
        mark = "*" if name in (alias, mid) else " "
        print(f"{mark} {alias:<8} {mid:<22} {ctx:<8} {price:<18} {why}")
    print()
    print("  Any other name the CLI accepts works too - these are the ones checked")
    print("  against the model list on 2026-06-24.")


def main():
    ap = argparse.ArgumentParser(description="Choose the model for the steps that use one.")
    ap.add_argument("name", nargs="?", help="alias or full model id")
    ap.add_argument("--check", action="store_true",
                    help="send one trivial request to prove the model is accepted")
    ap.add_argument("--login", action="store_true",
                    help="sign the claude CLI in (hands over to `claude auth login`)")
    ap.add_argument("--clear", action="store_true", help="forget the setting")
    a = ap.parse_args()

    if a.login:
        exe = shutil.which("claude")
        if not exe:
            raise SystemExit(
                "the claude CLI is not on PATH - install it from "
                "claude.com/product/claude-code first.")
        # Hand the terminal over: signing in opens a browser and asks questions,
        # so this must not capture the streams.
        raise SystemExit(subprocess.run([exe, "auth", "login"]).returncode)

    if a.clear:
        if os.path.exists(CONFIG):
            os.remove(CONFIG)
        print(f"cleared - back to {DEFAULT}")
        return
    if not a.name:
        name = current()
        show(name)
        if a.check:
            ok, why = check(name)
            print(f"\ncheck: {'OK - ' if ok else 'FAILED - '}{why}")
            raise SystemExit(0 if ok else 1)
        return

    name = a.name.strip()
    known = {k for row in KNOWN for k in row[:2]}
    if name not in known:
        print(f"'{name}' is not one of the names checked on 2026-06-24. "
              f"Setting it anyway - run with --check to confirm the CLI takes it.")
    if a.check:
        ok, why = check(name)
        print(f"check: {'OK - ' if ok else 'FAILED - '}{why}")
        if not ok:
            raise SystemExit(f"not saving '{name}' - it was not accepted")
    save(name)
    print()
    show(current())


if __name__ == "__main__":
    main()
