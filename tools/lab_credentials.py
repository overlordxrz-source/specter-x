#!/usr/bin/env python3
"""Keep the lab network's WPA2 credential out of Git.

The passphrase must not live in a tracked file, so it is written to
``firmware/esp32-csi/softap_csi/lab.env`` - gitignored, mode 600 - and the
build reads it from the environment. The generated header lands in the build
directory, which is gitignored too, so the secret never enters the source
tree at all.

Two rules this tool enforces, because both have bitten before:

* the secret is never printed. ``init`` prints the PATH of the file and the
  SSID, so the person at the keyboard can read the passphrase off the
  machine; ``env`` prints an ``export`` line, which is still a secret on
  screen, so it says so first;
* the file is verified to be git-ignored before it is written. A secret in a
  file that git does not ignore is a secret one ``git add -A`` away from
  being published.

Usage::

    tools/lab_credentials.py init            # create a random credential
    tools/lab_credentials.py init --ssid X   # with a specific SSID
    tools/lab_credentials.py env             # print the export line
    tools/lab_credentials.py show            # print the SSID, not the secret
    tools/lab_credentials.py check           # is a credential present and sane?

The build itself does not need this tool: it reads ``SPECTER_LAB_PSK`` from
the environment. The tool exists to make the secret easy to create and
impossible to commit by accident.
"""
from __future__ import annotations

import argparse
import os
import secrets
import stat
import string
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The file the credential lives in. It is inside the repository tree so the
#: build can find it, and it is gitignored so it can never be committed.
LAB_ENV = os.path.join(REPO, "firmware", "esp32-csi", "softap_csi", "lab.env")

#: The characters the build accepts: WPA2 allows 8..63 characters, and this
#: alphabet needs no escaping into a C string literal.
ALPHABET = string.ascii_letters + string.digits + "!@#%^&*()_+=,.:?~-"

DEFAULT_SSID = "SPECTER-LAB"


def _git_ignored(path: str) -> bool:
    """Is this path ignored by git? A secret in a tracked path is a
    published secret."""
    try:
        out = subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", path],
            cwd=REPO, capture_output=True, text=True)
    except OSError:
        return False
    return out.returncode == 0


def _read_env(path: str) -> dict:
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, _, val = raw.partition("=")
            values[key.strip()] = val.strip()
    return values


def _write_env(path: str, values: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = "# The SPECTER-X lab network credential.\n" \
           "# Gitignored, and never to be committed, printed or pasted anywhere.\n"
    for key, val in values.items():
        body += f"{key}={val}\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _passphrase(length: int = 20) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def cmd_init(args) -> int:
    if not _git_ignored(LAB_ENV):
        print(f"REFUSING: {LAB_ENV} is not git-ignored.", file=sys.stderr)
        print("Add it to .gitignore before creating a credential there.",
              file=sys.stderr)
        return 2
    existing = _read_env(LAB_ENV)
    if existing.get("SPECTER_LAB_PSK") and not args.force:
        print(f"a credential already exists at {LAB_ENV} (use --force to replace)")
        return 1
    values = {
        "SPECTER_LAB_SSID": args.ssid,
        "SPECTER_LAB_PSK": _passphrase(),
    }
    _write_env(LAB_ENV, values)
    print(f"credential written to {LAB_ENV} (mode 600, gitignored)")
    print(f"SSID: {args.ssid}")
    print("The passphrase is NOT printed. Read it from the file when you "
          "need it on the phone:")
    print(f"    grep SPECTER_LAB_PSK {LAB_ENV}")
    return 0


def cmd_env(args) -> int:
    values = _read_env(LAB_ENV)
    psk = values.get("SPECTER_LAB_PSK", "")
    if not psk:
        print(f"no credential in {LAB_ENV}; run '{sys.argv[0]} init' first",
              file=sys.stderr)
        return 1
    print("# The line below contains the lab passphrase. It is a secret: do "
          "not paste it into a chat, a ticket or a commit message.")
    print(f"export SPECTER_LAB_PSK='{psk}'")
    return 0


def cmd_show(args) -> int:
    values = _read_env(LAB_ENV)
    psk = values.get("SPECTER_LAB_PSK", "")
    if psk:
        psk_state = "(set, %d characters, not shown)" % len(psk)
    else:
        psk_state = "(unset)"
    print(f"file:   {LAB_ENV}")
    print(f"SSID:   {values.get('SPECTER_LAB_SSID', '(unset)')}")
    print(f"PSK:    {psk_state}")
    return 0


def cmd_check(args) -> int:
    values = _read_env(LAB_ENV)
    psk = values.get("SPECTER_LAB_PSK", "")
    problems = []
    if not psk:
        problems.append("no passphrase in the credential file")
    elif not 8 <= len(psk) <= 63:
        problems.append(f"passphrase is {len(psk)} characters; WPA2 wants 8..63")
    elif any(ch not in ALPHABET for ch in psk):
        problems.append("passphrase uses characters the build rejects")
    if not _git_ignored(LAB_ENV):
        problems.append("the credential file is not git-ignored")
    if problems:
        for p in problems:
            print(f"FAIL: {p}", file=sys.stderr)
        return 1
    print("credential present, sane and git-ignored")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create a random credential")
    p.add_argument("--ssid", default=DEFAULT_SSID)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("env", help="print the export line for the build")
    p.set_defaults(func=cmd_env)

    p = sub.add_parser("show", help="show the SSID, never the secret")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("check", help="is a credential present and sane?")
    p.set_defaults(func=cmd_check)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
