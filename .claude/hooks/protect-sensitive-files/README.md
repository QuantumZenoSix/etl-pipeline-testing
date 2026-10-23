# protect-sensitive-files

A user-level Claude Code `PreToolUse` hook that stops Claude's file tools (`Write`, `Edit`,
`NotebookEdit`, and `MultiEdit` where it exists) from creating, editing, or overwriting secrets and
other protected files.

- It decides from the **target path only**. It never opens, prints, copies, or logs the file's contents.
- **Reading is unaffected:** `Read` isn't hooked, so Claude can still read a protected file.
- **Deny** blocks the edit. **Ask** prompts you to approve it. Otherwise there's no output, and your
  normal permission rules apply. The hook never answers "allow".
- The reason names the path, the rule, and the pattern, for example:
  `'.env' is protected by rule 'env-file' (pattern '.env')`.

## Built-in rules

| Rule | Action | Patterns |
|---|---|---|
| `env-file` | deny | `.env`, `.env.*`, `*.env` |
| `direnv-file` | **ask** | `.envrc`. Usually just `use flake`, but it can export secrets. |
| `ssh-private-key` | deny | `id_rsa`, `id_dsa`, `id_ecdsa`, `id_ed25519`, `id_*_sk`, `*.ppk` |
| `private-key-or-cert` | deny | `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.p8`, `*.jks`, `*.keystore`, `*.kdbx` |
| `credential-file` | deny | `.netrc`, `_netrc`, `.pgpass`, `.my.cnf`, `.git-credentials`, `.htpasswd`, `.vault-token`, `credentials.json`, `client_secret*.json`, `service-account*.json`, `secrets.yml`/`.yaml`, `*.tfstate`, `*.tfstate.backup` |
| `credential-store` | deny | `~/.ssh/`, `~/.gnupg/`, `~/.aws/`, `~/.azure/`, `~/.config/gcloud/`, `~/.kube/config`, `~/.docker/config.json`, `~/.config/gh/hosts.yml`, `~/.npmrc`, `~/.pypirc`, `~/.terraform.d/credentials.tfrc.json`, `~/.password-store/`, `~/.local/share/keyrings/`, `~/.claude/.credentials.json` |
| `claude-guard-config` | **ask** | `~/.claude/settings.json`, `~/.claude/hooks/`. Claude can't silently disable its own guards. |

**Built-in exceptions:** `.env.example`, `.env.sample`, `.env.template`, `.env.dist`.

Matching uses these explicit patterns only. It never matches on words like "key", "token", or
"secret", so `src/keys.ts`, `token.py`, `config.json`, `docs/credentials.md`, `.env-example`,
`id_rsa.pub` (outside `~/.ssh`), and a project-level `.npmrc` all remain editable.

## Customize: `protected-paths.json`

```json
{
  "use_default_rules": true,
  "protected": [
    "config/master.key",
    { "pattern": "~/work/prod-secrets/", "name": "prod-secrets" },
    { "pattern": "deploy/*.yaml", "name": "deploy-manifests", "action": "ask" }
  ],
  "exceptions": ["tests/fixtures/*.pem"]
}
```

**Pattern forms** (`*` and `**` both match any characters, including `/`):
- **Name only**, with no `/`: matches the file name in any directory, case-insensitively. Examples: `.env.*`, `id_ed25519`.
- **Anchored**, starting with `/` or `~/`: matches that absolute location. A trailing `/` protects everything inside it.
- **Relative**, containing `/`: matches that sub-path at any depth. Example: `config/master.key`.

**How rules combine:**
- **Exceptions win** over every rule, including built-ins.
- If both deny and ask rules match, **deny wins**.
- `"use_default_rules": false` replaces the built-in rules and built-in exceptions entirely.

**If the config file is invalid:** built-in deny rules still apply, and every other edit gets
**ask** with a message telling you to fix the file.

Editing this config file through Claude triggers an approval prompt. That's the `claude-guard-config`
rule at work. You can also edit it yourself.

**Path handling:**
- Relative paths resolve against Claude's working directory.
- `~` is expanded and `..` is collapsed, so `src/../../.ssh/id_rsa` is caught.
- Both the literal path and its **symlink-resolved** real path are checked. A link that points into
  `~/.ssh`, or a symlinked directory into `~/.aws`, is denied.
- An exception name can't be used to launder a symlink to a protected file.

## Test

```bash
cd ~/.claude/hooks/protect-sensitive-files
python3 -m unittest -v test_protect              # full suite (uses a temporary HOME)
python3 protect.py --check path/to/file          # EDITABLE / ASK / DENY; exit 0 / 1 / 2
```

## Enable or disable

Installed in `~/.claude/settings.json` under `hooks.PreToolUse` with matcher
`Write|Edit|NotebookEdit|MultiEdit`. Backups of earlier settings are kept as
`~/.claude/settings.json.bak-<timestamp>`.

- **Review or temporarily disable:** use `/hooks`. Setting `"disableAllHooks": true` disables *all* hooks.
- **Remove:** delete that `PreToolUse` entry from settings.
- **Fail-closed setting:** `"onFailure": "block"` means that if the script can't start or times out,
  file edits are blocked rather than allowed. Use the steps above to recover.

## Limitations of path-based protection

- **Only Claude's file tools are covered.** Shell commands can still change files indirectly:
  `echo X > .env`, `sed -i`, `cp`, `mv`, `tee`, scripts, package managers, and code that Claude runs.
  The separate `guard-dangerous-commands` Bash hook doesn't cover these writes either.
  - Use Claude Code `permissions.deny` rules such as `Edit(~/.ssh/**)` and `Read(./.env)` if you also
    want to stop reads.
  - Use `/sandbox` with `sandbox.filesystem.denyWrite` for OS-level enforcement that also applies to
    Bash.
- **Reading is allowed.** Claude can read a protected file into the conversation. Add `Read(...)`
  permission deny rules for files that must never be read.
- **Hard links and bind mounts aren't detected.** Only symlinks are resolved. A file with an unexpected
  name or location isn't protected unless you add it to the config.
- **The decision is made before the write.** A symlink swapped between the check and the write
  (time-of-check to time-of-use) isn't caught.
- **The protection is lexical.** Secrets inside ordinary files, such as a hard-coded key in `app.py`,
  aren't detected. Use a secret scanner (gitleaks, trufflehog) and pre-commit hooks for that.
- **This is a guard rail against mistakes, not a security boundary.** Keep real credentials out of
  project directories, use a secret manager, and rotate anything that has been exposed.
