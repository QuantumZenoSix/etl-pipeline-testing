#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block edits to secrets and other protected files.

Hooked tools: Write, Edit, NotebookEdit (and MultiEdit if present). Reading is
not hooked, so protected files stay readable. The hook decides from the target
PATH only. It never opens, prints, copies, or logs the target file's contents.

A path is protected when it (or its symlink-resolved real path) matches a rule
pattern and does not match an exception. Pattern forms:
  name-only   ".env.*", "id_ed25519"     matches the file name (case-insensitive)
  anchored    "~/.aws/", "/etc/ssl/*"    matches that absolute location;
                                         a trailing "/" means "anything inside"
  relative    "config/master.key"        matches that sub-path at any depth
'*' and '**' both match any characters, including '/'.

Rules come from DEFAULT_RULES below plus the user config file
(protected-paths.json next to this script, or $CLAUDE_PROTECT_CONFIG).

Output follows the PreToolUse protocol: permissionDecision "deny" or "ask"
with a short reason naming the path and rule; no output otherwise.
"""

import fnmatch
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.environ.get("CLAUDE_PROTECT_CONFIG", os.path.join(HERE, "protected-paths.json"))
PATH_FIELDS = ("file_path", "notebook_path", "path")

# Built-in rules. Each pattern is documented in README.md.
DEFAULT_RULES = [
    ("env-file", "deny", [".env", ".env.*", "*.env"]),
    ("direnv-file", "ask", [".envrc"]),  # often just `use flake`, but can export secrets
    ("ssh-private-key", "deny", ["id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
                                 "id_ecdsa_sk", "id_ed25519_sk", "*.ppk"]),
    ("private-key-or-cert", "deny", ["*.pem", "*.key", "*.p12", "*.pfx", "*.p8",
                                     "*.jks", "*.keystore", "*.kdbx"]),
    ("credential-file", "deny", [".netrc", "_netrc", ".pgpass", ".my.cnf", ".git-credentials",
                                 ".htpasswd", ".vault-token", "credentials.json",
                                 "client_secret*.json", "service-account*.json",
                                 "secrets.yml", "secrets.yaml", "*.tfstate", "*.tfstate.backup"]),
    ("credential-store", "deny", ["~/.ssh/", "~/.gnupg/", "~/.aws/", "~/.azure/",
                                  "~/.config/gcloud/", "~/.kube/config", "~/.docker/config.json",
                                  "~/.config/gh/hosts.yml", "~/.npmrc", "~/.pypirc",
                                  "~/.terraform.d/credentials.tfrc.json", "~/.password-store/",
                                  "~/.local/share/keyrings/", "~/.claude/.credentials.json"]),
    ("claude-guard-config", "ask", ["~/.claude/settings.json", "~/.claude/hooks/"]),
]
DEFAULT_EXCEPTIONS = [".env.example", ".env.sample", ".env.template", ".env.dist"]


def _expand(pattern):
    p = os.path.expanduser(pattern.strip())
    return p + "*" if p.endswith("/") else p.replace("**", "*")


def matches(pattern, path):
    """True if absolute normalized `path` matches `pattern` (see module docstring)."""
    p = _expand(pattern)
    if "/" not in p:
        return fnmatch.fnmatchcase(os.path.basename(path).lower(), p.lower())
    if p.startswith("/"):
        return fnmatch.fnmatchcase(path, p)
    return fnmatch.fnmatchcase(path, "*/" + p.lstrip("./"))


def load_rules():
    """Return (rules, exceptions, config_error). Rules: list of (name, action, pattern)."""
    rules = [(name, action, pat) for name, action, pats in DEFAULT_RULES for pat in pats]
    exceptions = list(DEFAULT_EXCEPTIONS)
    if not os.path.exists(CONFIG_PATH):
        return rules, exceptions, None
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise ValueError("top level must be an object")
        if cfg.get("use_default_rules", True) is False:
            rules, exceptions = [], []
        for entry in cfg.get("protected", []):
            if isinstance(entry, str):
                entry = {"pattern": entry}
            action = entry.get("action", "deny")
            if not isinstance(entry.get("pattern"), str) or action not in ("deny", "ask"):
                raise ValueError(f"invalid protected entry: {entry!r}")
            rules.append((entry.get("name", "user-rule"), action, entry["pattern"]))
        for exc in cfg.get("exceptions", []):
            if not isinstance(exc, str):
                raise ValueError(f"invalid exception: {exc!r}")
            exceptions.append(exc)
    except (OSError, ValueError, AttributeError, TypeError) as err:
        defaults = [(n, a, p) for n, a, pats in DEFAULT_RULES for p in pats if a == "deny"]
        return defaults, list(DEFAULT_EXCEPTIONS), f"{type(err).__name__}: {err}"
    return rules, exceptions, None


def candidate_paths(raw, cwd):
    """Lexically normalized absolute path, plus its symlink-resolved real path."""
    path = os.path.normpath(os.path.join(cwd, os.path.expanduser(raw)))
    real = os.path.realpath(path)
    return [path] if real == path else [path, real]


def evaluate(raw_path, cwd=None):
    """Return (action, reason) with action in {"deny", "ask", None}. Never reads the file."""
    rules, exceptions, config_error = load_rules()
    cwd = cwd or os.getcwd()
    hits = []
    for path in candidate_paths(raw_path, cwd):
        if any(matches(e, path) for e in exceptions):
            continue
        hits += [(action, name, pat, path) for name, action, pat in rules if matches(pat, path)]
    if hits:
        action = "deny" if any(h[0] == "deny" for h in hits) else "ask"
        _, name, pat, path = next(h for h in hits if h[0] == action)
        via = "" if path == candidate_paths(raw_path, cwd)[0] else f" (symlink target {path})"
        return action, (f"'{raw_path}'{via} is protected by rule '{name}' (pattern '{pat}'). "
                        f"Edit it yourself if intended, or add an exception in {CONFIG_PATH}.")
    if config_error:
        return "ask", (f"protected-paths config is invalid ({config_error}); only built-in rules "
                       f"were checked. Fix {CONFIG_PATH}.")
    return None, None


def run_hook(stdin_text):
    """Return the JSON string to print, or "" for no decision."""
    try:
        data = json.loads(stdin_text)
    except ValueError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("tool_input"), dict):
        action, reason = "ask", "could not read the hook input to check for protected files"
    else:
        tool_input = data["tool_input"]
        raw = next((tool_input[f] for f in PATH_FIELDS if f in tool_input), None)
        if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
            action, reason = "ask", f"{data.get('tool_name', 'tool')} call has no usable target path"
        else:
            try:
                cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
                action, reason = evaluate(raw, cwd)
            except Exception as err:  # fail safe
                action, reason = "ask", f"could not evaluate target path ({type(err).__name__})"
    if not action:
        return ""
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": action,
        "permissionDecisionReason": "protect-sensitive-files: " + reason,
    }})


def main(argv):
    if len(argv) >= 2 and argv[0] == "--check":  # manual check: exit 0=editable, 1=ask, 2=deny
        action, reason = evaluate(argv[1])
        print(f"{(action or 'editable').upper()}" + (f": {reason}" if reason else ""))
        return {"deny": 2, "ask": 1}.get(action, 0)
    output = run_hook(sys.stdin.read())
    if output:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
