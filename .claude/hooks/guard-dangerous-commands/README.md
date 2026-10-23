# guard-dangerous-commands

A user-level Claude Code `PreToolUse` hook that inspects every `Bash` command Claude is about to run
and stops clearly destructive shell and git operations. It parses the command text only and never
executes it. It uses only the Python standard library.

| Decision | When | Effect |
|---|---|---|
| **deny** | Catastrophic or almost never intended | Claude Code blocks the call and shows the reason |
| **ask** | Destructive but sometimes legitimate | You are prompted to approve or reject |
| *(no output)* | Everything else | Your normal permission rules apply |

The guard never returns `allow`, so it can only make Claude Code stricter, never more permissive.

## What it catches

**Denied**
- Recursive `rm` of `/`, system directories (`/etc`, `/usr`, …), `/tmp`, `/home/<user>`, `~`, `$HOME`,
  WSL drive roots (`/mnt/c`), or anything that resolves to them (`rm -rf ..` from `~/proj`, `rm -rf *` in `~`).
  Also any `rm --no-preserve-root`.
- `mkfs*` / `wipefs` / `shred` on a disk device, `dd of=/dev/sdX`, redirects into a disk device.
- Force-push or remote delete targeting `main`, `master`, `production`, `prod`, or `release`. With no
  refspec, the branch is read from `.git/HEAD`.
- Recursive `chmod`/`chown`, `find -delete`/`-exec rm`, or `mv` on critical paths. Fork bombs.

**Asks first**
- `git reset --hard`, `git clean -f…` (but not `-n`), `git checkout -- …`/`.`/`-f`, `git restore` (worktree),
  `git switch --discard-changes`, `git stash drop|clear`, `git branch -D`, force-push to other branches
  (including `--force-with-lease`), remote branch deletion, `push --mirror`, `filter-branch`/`filter-repo`,
  `reflog expire`, `gc --prune=now`, `update-ref -d`.
- `rm -rf .`, `rm -rf *`, `rm -rf .git`, a recursive `rm` of a path built from a variable (`"$DIR"`),
  of a top-level home folder (`~/Documents`), or inside a system directory. `xargs rm -rf`.
- `terraform destroy` / `apply -auto-approve`, `pulumi destroy` / `up --yes`, `kubectl delete|drain`,
  `helm uninstall`, `aws s3 rb` / `rm --recursive`, `gcloud … delete`, `docker system|volume prune`,
  `docker volume rm`, `dropdb`, `crontab -r`, partition editors, `mv x /dev/null`.
- Anything the guard cannot parse (for example unbalanced quotes), malformed hook input, or an internal error.

**How it reads commands:** it splits on `;`, `&&`, `||`, `|`, `&`, newlines, and subshells. It handles
quoting and escapes (`'rm'`, `\rm`, `/bin/rm`), strips wrappers (`sudo`, `env`, `VAR=x`, `timeout`,
`nice`, `nohup`, `xargs`, `watch`, …), and recurses into `bash -c`, `sh -c`, `eval`, `$(…)`, backticks,
and `<(…)`. Heredoc bodies are treated as data (so commit messages that mention `rm -rf /` are fine),
unless the heredoc is fed to a shell.

Customize the rule tables (`CRITICAL_PATHS`, `PROTECTED_BRANCHES`, `INFRA_RULES`) at the top of `guard.py`.

## Installation (already done)

`~/.claude/settings.json` contains:

```json
"hooks": {
  "PreToolUse": [
    { "matcher": "Bash",
      "hooks": [{ "type": "command",
                  "command": "python3 -I /home/zeno/.claude/hooks/guard-dangerous-commands/guard.py",
                  "timeout": 10, "onFailure": "block" }] }
  ]
}
```

The previous settings file was backed up as `~/.claude/settings.json.bak-<timestamp>`.

`"onFailure": "block"` makes the hook **fail closed**. If the guard can't start (for example, `python3`
is missing) or times out, Bash calls are blocked rather than silently allowed. If that ever happens, use
the recovery steps under **Disable** below.

## Enable, disable, dry-run

- **Review:** run `/hooks` in Claude Code.
- **Dry-run (log only, never block):** add `"env": { "CLAUDE_GUARD_MODE": "dry-run" }` to
  `~/.claude/settings.json`, or append `--dry-run` to the hook command. Decisions are appended to
  `dry-run.log` in this directory. Note that this log contains the first 300 characters of each
  flagged command.
- **Disable temporarily:** use `/hooks`, or set `"disableAllHooks": true` in settings. That setting
  turns off *all* hooks.
- **Remove:** delete the `PreToolUse` entry from `~/.claude/settings.json`, or restore the backup.

## Testing

```bash
cd ~/.claude/hooks/guard-dangerous-commands
python3 -m unittest -v test_guard               # full suite
python3 guard.py --check 'git reset --hard'     # one command: prints NONE/ASK/DENY; exit 0/1/2
echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' | python3 guard.py   # raw hook output
```

The suite covers denied, asked, and allowed commands; variations in quoting, flags, and wrappers;
compound and nested commands; heredocs and comments; malformed input; the exact hook JSON
responses; dry-run; and a check that inspected commands are never executed.

## Limitations: this is a guard rail, not a security boundary

- **It sees command text, not behavior.** These get past it: scripts (`./cleanup.sh`, `make clean`,
  `npm run reset`), aliases and functions, `curl … | bash`, `python -c 'shutil.rmtree(...)'`, encoded
  or variable-built commands (`$CMD`), `ssh host '…'`, and destructive SQL sent through a client.
- **Path checks are lexical.** They don't follow symlinks, and globs other than a trailing `*` aren't expanded.
- **Only the Bash tool is inspected.** Claude's Write/Edit tools, MCP tools, and commands you run
  yourself with `!` are not covered.
- **There are known false positives.** A literal `'$(rm -rf /)'` in single quotes is treated as executable,
  and `find . -delete` run from `~` is denied.
- **It doesn't protect production.** It knows nothing about which kube context, AWS profile, or database
  is production.

**Use stronger protections for what matters:**
- Claude Code `permissions.deny` / `ask` rules, and `/sandbox` (filesystem and network isolation for Bash).
- Server-side branch protection for `main` (disallow force-push and deletion). This catches what the
  client can't.
- Least-privilege, separate credentials for production (no prod kubeconfig or cloud profile in your dev
  shell by default), and approval gates in CI/CD for deploys and `terraform apply`.
- Regular backups or snapshots, and pushing work often. `git reflog` can recover many local git mistakes.
