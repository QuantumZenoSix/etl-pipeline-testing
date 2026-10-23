#!/usr/bin/env python3
"""Claude Code PreToolUse hook: stop clearly destructive shell and git commands.

Reads the hook payload (JSON) on stdin and inspects ``tool_input.command``
WITHOUT executing it. The command text is only parsed: heredoc bodies and
comments are stripped, the text is split into simple commands, wrappers such
as ``sudo``/``env``/``xargs`` are removed, and ``bash -c``/``eval``/``$(...)``
bodies are inspected recursively.

Decisions:
  deny  -> catastrophic or almost never intended (``rm -rf /``, mkfs on a disk,
           force-push to main). Claude Code blocks the call.
  ask   -> destructive but sometimes legitimate (``git reset --hard``,
           ``git clean -fd``, ``terraform destroy``). You are asked to approve.
  none  -> no output; Claude Code's normal permission rules apply. This hook
           never answers "allow", so it can only make things stricter.

Anything the guard cannot parse, and any internal error, results in "ask".

Usage:
  guard.py                 hook mode (payload on stdin)
  guard.py --dry-run       hook mode, but only log decisions (never blocks)
  guard.py --check "cmd"   classify one command; exit 0=none, 1=ask, 2=deny
Setting CLAUDE_GUARD_MODE=dry-run has the same effect as --dry-run.

This is a guard rail against mistakes, not a security boundary: a determined
or obfuscated command (scripts, aliases, encoded payloads) can get past it.
"""

import datetime
import json
import os
import re
import shlex
import sys

ALLOW, ASK, DENY = 0, 1, 2
NAMES = {ALLOW: "none", ASK: "ask", DENY: "deny"}
MAX_DEPTH = 5

HOME = os.path.normpath(os.path.expanduser("~"))
LOG_PATH = os.environ.get(
    "CLAUDE_GUARD_LOG", os.path.join(os.path.dirname(os.path.abspath(__file__)), "dry-run.log")
)

# --- Tunable rule data -------------------------------------------------------

CRITICAL_PATHS = {
    "/", "/bin", "/boot", "/dev", "/etc", "/home", "/lib", "/lib32", "/lib64", "/media",
    "/mnt", "/opt", "/proc", "/root", "/run", "/sbin", "/snap", "/srv", "/sys", "/tmp",
    "/usr", "/var", "/Users", "/System", "/Applications", HOME,
}
SYSTEM_PREFIXES = ("/bin/", "/boot/", "/dev/", "/etc/", "/lib/", "/lib32/", "/lib64/",
                   "/proc/", "/root/", "/sbin/", "/sys/", "/usr/", "/var/lib/", "/System/")
PROTECTED_BRANCHES = {"main", "master", "production", "prod", "release"}

# Raw block devices (writing to these destroys a filesystem). /dev/null etc. are not matched.
BLOCK_DEVICE = re.compile(
    r"^/dev/(sd[a-z]|nvme\d|hd[a-z]|vd[a-z]|xvd[a-z]|mmcblk\d|disk\d|rdisk\d|loop\d|md\d|dm-\d|mapper/)"
)

# (command words in order, required options or None, reason) -> "ask".
INFRA_RULES = [
    (("terraform", "destroy"), None, "terraform destroy deletes managed infrastructure"),
    (("terraform", "apply"), {"-auto-approve", "--auto-approve"}, "terraform apply without review"),
    (("pulumi", "destroy"), None, "pulumi destroy deletes managed infrastructure"),
    (("pulumi", "up"), {"--yes", "-y"}, "pulumi up without review"),
    (("kubectl", "delete"), None, "kubectl delete removes cluster resources"),
    (("kubectl", "drain"), None, "kubectl drain evicts workloads from a node"),
    (("helm", "uninstall"), None, "helm uninstall removes a release"),
    (("helm", "delete"), None, "helm delete removes a release"),
    (("aws", "s3", "rb"), None, "aws s3 rb deletes a bucket"),
    (("aws", "s3", "rm"), {"--recursive"}, "recursive S3 delete"),
    (("gcloud", "delete"), None, "gcloud delete removes cloud resources"),
    (("docker", "system", "prune"), None, "docker system prune deletes images/containers/volumes"),
    (("docker", "volume", "prune"), None, "docker volume prune deletes volumes"),
    (("docker", "volume", "rm"), None, "docker volume rm deletes volume data"),
    (("dropdb",), None, "dropdb deletes a database"),
    (("crontab",), {"-r"}, "crontab -r removes all cron jobs"),
]

# Wrappers that run another command, and their options that take a value.
WRAPPERS = {
    "sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-R"},
    "doas": {"-u", "-C"},
    "env": {"-u", "-C", "--unset", "--chdir"},
    "nice": {"-n"}, "ionice": {"-c", "-n", "-p"}, "nohup": set(), "time": set(),
    "command": set(), "builtin": set(), "exec": set(), "chronic": set(), "unbuffer": set(),
    "stdbuf": {"-i", "-o", "-e"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "watch": {"-n", "--interval"},
    "xargs": {"-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a", "--max-args", "--max-procs",
              "--delimiter", "--arg-file", "--replace"},
}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish"}
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "}"}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
FORK_BOMB = re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:")
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
SHELL_BEFORE_HEREDOC = re.compile(r"\b(ba|z|da|k)?sh\b[^<]*<<")
SEP_CHARS, REDIR_CHARS = set(";&|"), set("<>&|")
LPAREN, RPAREN = "\x00LP\x00", "\x00RP\x00"  # escaped \( \) placeholders (find expressions)


# --- Text preprocessing ------------------------------------------------------

def _strip_heredocs(text):
    """Drop heredoc bodies (data, not commands) unless they are fed to a shell."""
    out, body, pending = [], [], []
    for line in text.split("\n"):
        if pending:
            body.append(line)
            if line.strip() == pending[0]:
                pending.pop(0)
                body = []
            continue
        out.append(line)
        if not SHELL_BEFORE_HEREDOC.search(line):
            pending.extend(m.group(2) for m in HEREDOC.finditer(line))
    return "\n".join(out + body)  # an unterminated heredoc is kept and inspected


def _preprocess(text):
    """Turn unquoted newlines into ';', drop comments, protect escaped parens."""
    out, quote, i = [], None, 0
    while i < len(text):
        c = text[i]
        if quote:
            out.append(c)
            if c == "\\" and quote == '"' and i + 1 < len(text):
                out.append(text[i + 1])
                i += 1
            elif c == quote:
                quote = None
        elif c == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt != "\n":  # backslash-newline is a line continuation
                out.append({"(": LPAREN, ")": RPAREN}.get(nxt, c + nxt))
            i += 1
        elif c in "'\"":
            quote = c
            out.append(c)
        elif c == "\n":
            out.append(" ; ")
        elif c == "#" and (not out or out[-1][-1:] in " \t;&|()"):
            end = text.find("\n", i)
            if end == -1:
                break
            i = end
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _substitutions(text):
    """Bodies of $(...), <(...), >(...) and `...` (these are executed by the shell)."""
    found = []
    for m in re.finditer(r"[$<>]\(", text):
        depth, j = 1, m.end()
        while j < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[j], 0)
            j += 1
        found.append(text[m.end():j - 1])
    found += re.findall(r"`([^`]*)`", text)
    return found


def _simple_commands(text):
    """Split shell text into (argv, redirect_targets) pairs."""
    lex = shlex.shlex(text, posix=True, punctuation_chars=True)
    lex.whitespace_split, lex.commenters = True, ""
    commands, argv, redirects, want_target = [], [], [], False
    for tok in lex:
        if want_target:
            redirects.append(tok)
            want_target = False
        elif "(" in tok or ")" in tok or (tok and set(tok) <= SEP_CHARS):
            if argv or redirects:
                commands.append((argv, redirects))
            argv, redirects = [], []
        elif tok and set(tok) <= REDIR_CHARS:
            want_target = True
        else:
            argv.append(tok.replace(LPAREN, "(").replace(RPAREN, ")"))
    if argv or redirects:
        commands.append((argv, redirects))
    return commands


# --- Path helpers ------------------------------------------------------------

def _resolve(target, cwd):
    """Return (absolute path or None if unresolvable, whether a '*' glob was stripped)."""
    t = target
    if t == "~" or t.startswith("~/"):
        t = HOME + t[1:]
    t = re.sub(r"^\$(\{HOME\}|HOME)(?=/|$)", lambda _: HOME, t)
    if "$" in t or "`" in t:
        return None, False
    parts, broad = t.split("/"), False
    while len(parts) > 1 and parts[-1] in ("*", ".*", ""):
        broad = broad or parts[-1] != ""
        parts.pop()
    if parts in (["*"], [".*"]):
        parts, broad = ["."], True
    t = "/".join(parts) or "/"
    return os.path.normpath(os.path.join(cwd, t)), broad


def _is_critical(path):
    return (path in CRITICAL_PATHS
            or re.fullmatch(r"/mnt/[a-z]", path) is not None      # WSL Windows drives
            or re.fullmatch(r"/(home|Users)/[^/]+", path) is not None)


def _contains(parent, path):
    return path == parent or path.startswith(parent.rstrip("/") + "/")


def _short_flag(args, letter):
    return any(re.fullmatch(r"-[A-Za-z]+", a) and letter in a for a in args)


def _current_branch(cwd):
    """Read the checked-out branch from .git/HEAD (file read only, no git process)."""
    d = cwd
    while True:
        head = os.path.join(d, ".git", "HEAD")
        if os.path.isfile(head):
            try:
                with open(head, encoding="utf-8") as f:
                    ref = f.read().strip()
            except OSError:
                return None
            return ref.rsplit("/", 1)[-1] if ref.startswith("ref:") else None
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


# --- Command rules -----------------------------------------------------------

def _rm(args, cwd, from_stdin):
    recursive, targets, opts_done = False, [], False
    for a in args:
        if not opts_done and a == "--":
            opts_done = True
        elif not opts_done and a == "--no-preserve-root":
            return [(DENY, "rm --no-preserve-root")]
        elif not opts_done and a.startswith("--"):
            recursive = recursive or a == "--recursive"
        elif not opts_done and a.startswith("-") and len(a) > 1:
            recursive = recursive or bool(set(a[1:]) & set("rR"))
        else:
            targets.append(a)
    results = []
    if from_stdin and recursive:
        results.append((ASK, "recursive rm on paths supplied by xargs (targets unknown)"))
    for target in targets:
        path, _ = _resolve(target, cwd)
        if path is None:
            if recursive:
                results.append((ASK, f"recursive rm on a path built from a variable/substitution: {target}"))
        elif _is_critical(path):
            results.append((DENY if recursive else ASK, f"rm targets critical path {path}"))
        elif path.startswith(SYSTEM_PREFIXES):
            results.append((ASK, f"rm inside a system directory: {path}"))
        elif recursive and _contains(path, cwd):
            results.append((ASK, f"recursive rm of the working directory or a parent of it: {path}"))
        elif recursive and os.path.dirname(path) == HOME:
            results.append((ASK, f"recursive rm of a top-level home directory: {path}"))
        elif recursive and os.path.basename(path) == ".git":
            results.append((ASK, f"recursive rm of git history: {path}"))
    return results


def _git(args, cwd):
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in ("-C", "-c", "--git-dir", "--work-tree", "--namespace") else 1
    if i >= len(args):
        return []
    sub, r = args[i], args[i + 1:]
    if i >= 2 and "-C" in args[:i]:
        cwd = os.path.join(cwd, args[args.index("-C") + 1])
    force = any(a in ("-f", "--force") for a in r) or _short_flag(r, "f")

    if sub == "push":
        positional = [a for a in r if not a.startswith("-")]
        refspecs = positional[1:]
        dests = [s.lstrip("+").split(":")[-1].replace("refs/heads/", "") for s in refspecs]
        if not refspecs:
            dests = [_current_branch(cwd) or "?"]
        protected = sorted(set(dests) & PROTECTED_BRANCHES)
        on = f" to {', '.join(protected)}" if protected else ""
        if force or any(s.startswith("+") for s in refspecs):
            return [(DENY if protected else ASK, f"git force-push{on} rewrites remote history")]
        if any(a.startswith(("--force-with-lease", "--force-if-includes")) for a in r):
            return [(ASK, "git force-push (with lease) rewrites remote history")]
        if "--delete" in r or "-d" in r or any(s.startswith(":") for s in refspecs):
            return [(DENY if protected else ASK, f"git push deletes a remote branch{on}")]
        if "--mirror" in r:
            return [(ASK, "git push --mirror can overwrite or delete remote refs")]
        return []
    if sub == "reset" and "--hard" in r:
        return [(ASK, "git reset --hard discards uncommitted changes")]
    if sub == "clean" and (force or "--force" in r) and not (
            "--dry-run" in r or "-n" in r or _short_flag(r, "n")):
        return [(ASK, "git clean -f deletes untracked files")]
    if sub == "checkout" and (force or "." in r or "--" in r):
        return [(ASK, "git checkout can discard uncommitted changes")]
    if sub == "restore" and not (({"--staged", "-S"} & set(r)) and not ({"--worktree", "-W"} & set(r))):
        return [(ASK, "git restore discards uncommitted changes in the working tree")]
    if sub == "switch" and (force or "--discard-changes" in r):
        return [(ASK, "git switch --discard-changes discards uncommitted changes")]
    if sub == "stash" and r[:1] in (["drop"], ["clear"]):
        return [(ASK, f"git stash {r[0]} deletes stashed work")]
    if sub == "branch" and ("-D" in r or (({"-d", "--delete"} & set(r)) and force)):
        return [(ASK, "git branch -D deletes a branch even if unmerged")]
    if sub in ("filter-branch", "filter-repo"):
        return [(ASK, f"git {sub} rewrites repository history")]
    if sub == "reflog" and r[:1] == ["expire"]:
        return [(ASK, "git reflog expire removes recovery points")]
    if sub == "gc" and any(a.startswith("--prune=now") for a in r):
        return [(ASK, "git gc --prune=now permanently deletes unreachable commits")]
    if sub == "update-ref" and "-d" in r:
        return [(ASK, "git update-ref -d deletes a ref")]
    if sub == "worktree" and r[:1] == ["remove"] and force:
        return [(ASK, "git worktree remove --force discards worktree changes")]
    return []


def _disk(name, args):
    devices = [a for a in args if BLOCK_DEVICE.match(a.split("=", 1)[-1])]
    if name in ("mkfs", "mke2fs", "mkswap", "wipefs") or name.startswith("mkfs."):
        return [(DENY if devices else ASK, f"{name} formats or wipes a filesystem")]
    if name == "dd" and any(a.startswith("of=") and BLOCK_DEVICE.match(a[3:]) for a in args):
        return [(DENY, "dd writes directly to a disk device")]
    if name in ("fdisk", "sfdisk", "gdisk", "sgdisk", "cfdisk", "parted") and not (
            {"-l", "--list"} & set(args) or "print" in args):
        return [(ASK, f"{name} edits a partition table")]
    if name == "shred":
        return [(DENY if devices else ASK, "shred irrecoverably destroys data")]
    return []


def _ownership(name, args, cwd):
    if not ("-R" in args or "--recursive" in args or _short_flag(args, "R")):
        return []
    positional = [a for a in args if not a.startswith("-")][1:]  # skip mode/owner
    for target in positional:
        path, _ = _resolve(target, cwd)
        if path and _is_critical(path):
            return [(DENY, f"recursive {name} of critical path {path}")]
    return []


def _find(args, cwd):
    starts = []
    for a in args:
        if a.startswith("-") or a in ("(", "!", ")"):
            break
        starts.append(a)
    deletes = "-delete" in args or any(
        a in ("-exec", "-execdir", "-ok") and i + 1 < len(args) and os.path.basename(args[i + 1]) == "rm"
        for i, a in enumerate(args))
    if deletes:
        for s in starts or ["."]:
            path, _ = _resolve(s, cwd)
            if path and _is_critical(path):
                return [(DENY, f"find deletes files under critical path {path}")]
    return []


def _mv(args, cwd):
    positional = [a for a in args if not a.startswith("-")]
    if len(positional) >= 2 and positional[-1] == "/dev/null":
        return [(ASK, "mv to /dev/null destroys the source")]
    for src in positional[:-1]:
        path, _ = _resolve(src, cwd)
        if path and _is_critical(path):
            return [(DENY, f"mv of critical path {path}")]
    return []


def _infra(name, args):
    words = [a for a in args if not a.startswith("-")]
    opts = {a.split("=", 1)[0] for a in args if a.startswith("-")}
    for prefix, needed, reason in INFRA_RULES:
        if name != prefix[0] or (needed and not needed & opts):
            continue
        it = iter(words)
        if all(w in it for w in prefix[1:]):  # ordered subsequence
            return [(ASK, reason)]
    return []


# --- Evaluation --------------------------------------------------------------

def _strip_wrappers(argv):
    argv, from_stdin = list(argv), False
    while argv:
        name = os.path.basename(argv[0])
        if argv[0] in KEYWORDS or ASSIGNMENT.match(argv[0]):
            argv.pop(0)
        elif name in WRAPPERS:
            argv.pop(0)
            from_stdin = from_stdin or name == "xargs"
            while argv and argv[0].startswith("-") and argv[0] != "-":
                if argv.pop(0) in WRAPPERS[name] and argv:
                    argv.pop(0)
            if name == "timeout" and argv:
                argv.pop(0)  # duration
        else:
            break
    return argv, from_stdin


def _classify(argv, redirects, cwd, depth):
    results = [(DENY, f"output redirected to raw disk device {t}")
               for t in redirects if BLOCK_DEVICE.match(t)]
    argv, from_stdin = _strip_wrappers(argv)
    if not argv:
        return results
    name, args = os.path.basename(argv[0]), argv[1:]
    if len(argv) == 1 and re.search(r"\s", argv[0]):  # e.g. watch 'cmd ...'
        return results + _evaluate(argv[0], cwd, depth + 1)
    if name in SHELLS or name == "su":
        for i, a in enumerate(args):
            if (a == "-c" or re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", a)) and i + 1 < len(args):
                results += _evaluate(args[i + 1], cwd, depth + 1)
                break
    elif name == "eval":
        results += _evaluate(" ".join(args), cwd, depth + 1)
    elif name == "rm":
        results += _rm(args, cwd, from_stdin)
    elif name == "git":
        results += _git(args, cwd)
    elif name in ("chmod", "chown", "chgrp"):
        results += _ownership(name, args, cwd)
    elif name == "find":
        results += _find(args, cwd)
    elif name == "mv":
        results += _mv(args, cwd)
    else:
        results += _disk(name, args) + _infra(name, args)
    return results


def _evaluate(text, cwd, depth=0):
    if depth > MAX_DEPTH:
        return [(ASK, "command is nested too deeply to inspect")]
    results = []
    if FORK_BOMB.search(text):
        results.append((DENY, "fork bomb"))
    text = _preprocess(_strip_heredocs(text))
    for inner in _substitutions(text):
        results += _evaluate(inner, cwd, depth + 1)
    try:
        commands = _simple_commands(text)
    except ValueError as exc:  # e.g. unbalanced quotes
        return results + [(ASK, f"could not parse command safely ({exc})")]
    for argv, redirects in commands:
        results += _classify(argv, redirects, cwd, depth)
    return results


def evaluate(command, cwd=None):
    """Return (level, reasons) for a shell command string. Never executes it."""
    try:
        results = _evaluate(command, os.path.normpath(cwd or os.getcwd()))
    except Exception as exc:  # fail safe: unknown -> ask
        return ASK, [f"guard internal error ({type(exc).__name__}); please review manually"]
    level = max((lvl for lvl, _ in results), default=ALLOW)
    reasons = list(dict.fromkeys(why for lvl, why in results if lvl == level and lvl > ALLOW))
    return level, reasons


# --- Hook protocol -----------------------------------------------------------

def _decision(level, reasons):
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": NAMES[level],
        "permissionDecisionReason": "guard-dangerous-commands: " + "; ".join(reasons),
    }}


def _log(level, reasons, command):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": datetime.datetime.now().isoformat(timespec="seconds"),
                                "decision": NAMES[level], "reasons": reasons,
                                "command": command[:300]}) + "\n")
    except OSError:
        pass


def run_hook(stdin_text, dry_run=False):
    """Return the JSON string to print (or "" for no decision)."""
    try:
        data = json.loads(stdin_text)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        level, reasons, command = ASK, ["could not read hook input; please review manually"], ""
    elif data.get("tool_name") != "Bash":
        return ""
    else:
        tool_input = data.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not isinstance(command, str):
            level, reasons, command = ASK, ["hook input has no command string; please review manually"], ""
        elif not command.strip():
            return ""
        else:
            cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
            level, reasons = evaluate(command, cwd)
    if dry_run:
        if level > ALLOW:
            _log(level, reasons, command)
        return ""
    return json.dumps(_decision(level, reasons)) if level > ALLOW else ""


def main(argv):
    if len(argv) >= 2 and argv[0] == "--check":
        level, reasons = evaluate(argv[1])
        print(f"{NAMES[level].upper()}" + (f": {'; '.join(reasons)}" if reasons else ""))
        return level
    dry_run = "--dry-run" in argv or os.environ.get("CLAUDE_GUARD_MODE") == "dry-run"
    output = run_hook(sys.stdin.read(), dry_run)
    if output:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
