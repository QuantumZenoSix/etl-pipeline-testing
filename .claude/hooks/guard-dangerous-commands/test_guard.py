#!/usr/bin/env python3
"""Tests for guard.py. Run: python3 -m unittest -v test_guard (from this directory)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guard.py")
HOME = guard.HOME
PROJECT = os.path.join(HOME, "proj")          # a project directly under $HOME
NESTED = os.path.join(HOME, "work", "proj")   # a project two levels down


def level(cmd, cwd=PROJECT):
    return guard.evaluate(cmd, cwd)[0]


class Deny(unittest.TestCase):
    CASES = [
        "rm -rf /", "rm -rf /*", "rm -fr ~", "rm -rf ~/", "rm -rf ~/*", "rm -rf $HOME",
        'rm -rf "${HOME}"', "rm -Rf /etc", "rm -r -f /usr", "rm --recursive --force /var",
        "/bin/rm -rf /", "\\rm -rf /", "'rm' '-rf' '/'", "rm -rf -- /", "rm -rf /tmp",
        "rm -rf /mnt/c", "rm -rf /home/someone", "sudo rm -rf --no-preserve-root /",
        "sudo -u root rm -rf /", "env FOO=1 rm -rf /", "FOO=1 rm -rf /", "timeout 5 rm -rf /",
        "nice -n 10 rm -rf /", "nohup rm -rf / &",
        "mkfs.ext4 /dev/sda1", "mkfs -t ext4 /dev/sdb", "wipefs -a /dev/nvme0n1",
        "dd if=/dev/zero of=/dev/sda bs=1M", "cat image.iso > /dev/sdb", "echo x >/dev/nvme0n1",
        "shred -n 3 /dev/sda", ":(){ :|:& };:",
        "git push --force origin main", "git push -f origin master", "git push origin +main",
        "git push origin HEAD:main --force", "git -C repo push --force origin main",
        "git push origin --delete main", "chmod -R 777 /", "chown -R me /etc",
        "find / -delete", "find ~ -name '*.log' -delete", "find / -exec rm -rf {} +",
        "find / \\( -name a -o -name b \\) -delete", "mv /etc /tmp/etc-old",
    ]

    def test_dangerous_commands_are_denied(self):
        for cmd in self.CASES:
            with self.subTest(cmd=cmd):
                self.assertEqual(level(cmd), guard.DENY)

    def test_relative_paths_resolve_against_cwd(self):
        self.assertEqual(level("rm -rf ..", cwd=PROJECT), guard.DENY)   # .. == $HOME
        self.assertEqual(level("rm -rf *", cwd=HOME), guard.DENY)
        self.assertEqual(level("rm -rf .", cwd=HOME), guard.DENY)


class Ask(unittest.TestCase):
    CASES = [
        "git reset --hard", "git reset --hard HEAD~3", "git clean -fd", "git clean -fdx",
        "git clean -f", "git checkout -- .", "git checkout .", "git checkout -- src/app.py",
        "git checkout -f main", "git restore .", "git restore src/x.py",
        "git restore --staged --worktree x.py", "git switch --discard-changes main",
        "git stash drop", "git stash clear", "git branch -D feature",
        "git branch --delete --force feature", "git push --force origin feature",
        "git push --force-with-lease origin feature", "git push origin --delete feature",
        "git push origin :feature", "git push --mirror backup", "git filter-branch --all",
        "git filter-repo --path secrets", "git reflog expire --expire=now --all",
        "git gc --prune=now", "git update-ref -d refs/heads/x",
        "rm -rf .", "rm -rf ./*", "rm -rf *", "rm -rf .git", 'rm -rf "$BUILD_DIR"',
        "rm -rf ${DIR}/", "rm -rf ~/Documents", "rm /etc/hosts", "rm -rf /var/lib/docker",
        "find . -type f | xargs rm -rf", "shred secrets.txt", "mkfs.ext4 disk.img",
        "fdisk /dev/sda", "mv important.db /dev/null",
        "terraform destroy", "terraform apply -auto-approve", "pulumi destroy --yes",
        "kubectl delete ns prod", "kubectl -n app delete pod web-1", "helm uninstall api",
        "aws s3 rm s3://bucket/data --recursive", "aws s3 rb s3://bucket --force",
        "gcloud compute instances delete vm-1", "docker system prune -af",
        "docker volume prune -f", "dropdb app_prod", "crontab -r",
        'echo "unterminated',  # unparseable -> fail safe
    ]

    def test_risky_commands_require_approval(self):
        for cmd in self.CASES:
            with self.subTest(cmd=cmd):
                self.assertEqual(level(cmd), guard.ASK)

    def test_force_push_without_refspec_uses_checked_out_branch(self):
        with tempfile.TemporaryDirectory() as repo:
            os.makedirs(os.path.join(repo, ".git"))
            head = os.path.join(repo, ".git", "HEAD")
            with open(head, "w") as f:
                f.write("ref: refs/heads/main\n")
            self.assertEqual(level("git push --force", cwd=repo), guard.DENY)
            with open(head, "w") as f:
                f.write("ref: refs/heads/feature/x\n")
            self.assertEqual(level("git push --force", cwd=repo), guard.ASK)


class Allow(unittest.TestCase):
    CASES = [
        "", "ls -la", "cat README.md", "pwd", "git status", "git diff --stat",
        "git log --oneline -20", "git add -A", "git commit -m 'fix: handle rm -rf in docs'",
        'git commit -m "remove rm -rf / example"', "git checkout -b feature/x",
        "git checkout main", "git switch main", "git switch -c new-branch", "git push",
        "git push origin feature", "git push -u origin feature", "git push --follow-tags",
        "git pull --rebase", "git fetch --all --prune", "git rebase main", "git merge --no-ff x",
        "git reset HEAD file.txt", "git reset --soft HEAD~1", "git restore --staged file.txt",
        "git clean -n", "git clean -nd", "git clean -fdn", "git branch -d merged-branch",
        "git stash", "git stash pop", "git -C sub status",
        "npm install", "npm ci", "npm test", "npm run build", "pip install requests",
        "pip install -r requirements.txt", "pytest -q", "python -m unittest", "make test",
        "cargo build", "go test ./...", "sudo apt-get install -y jq",
        "rm file.txt", "rm -f build.log", "rm -rf node_modules", "rm -rf build/ dist/",
        "rm -rf ./node_modules", "rm -rf /tmp/build-123", 'rm -r "my dir"',
        "rm -rf ~/work/proj/node_modules", "mkdir -p a/b", "touch x", "cp -r src dst",
        'echo "rm -rf /"', "echo 'mkfs is a command'", 'grep -rn "rm -rf" .',
        'grep -rn "git push --force" docs', "dd if=in.img of=out.img",
        "dd if=/dev/zero of=/dev/null count=1", "cat x > /dev/null", "echo hi 2>/dev/null",
        "cmd > out.log 2>&1", "find . -name '*.pyc' -delete",
        "find build -type f -exec rm {} \\;", "chmod +x script.sh", "chmod -R u+w build",
        "docker ps", "docker build -t app .", "kubectl get pods", "terraform plan",
        "terraform apply", "helm list", "aws s3 ls", "crontab -l", "fdisk -l",
        "kill -9 1234", "echo $((1 + 2))", "curl -s https://example.com/#rm",
    ]

    def test_ordinary_commands_pass_through(self):
        for cmd in self.CASES:
            with self.subTest(cmd=cmd):
                self.assertEqual(level(cmd), guard.ALLOW, guard.evaluate(cmd, PROJECT)[1])

    def test_heredoc_bodies_are_data(self):
        commit = "git commit -F - <<'EOF'\nfix: guard against rm -rf / and git push --force origin main\nEOF"
        self.assertEqual(level(commit), guard.ALLOW)
        self.assertEqual(level("cat <<EOF > notes.md\nrm -rf /\nEOF"), guard.ALLOW)

    def test_comments_are_ignored(self):
        self.assertEqual(level("ls # rm -rf /"), guard.ALLOW)


class CompoundCommands(unittest.TestCase):
    def test_destructive_command_hidden_in_compound_expression(self):
        cases = [
            "echo ok && rm -rf /", "true; rm -rf /", "false || rm -rf ~", "ls | rm -rf /",
            "(cd /tmp && rm -rf /)", "{ rm -rf /; }", "if true; then rm -rf /; fi",
            "for f in a; do rm -rf /; done", "cd x\nrm -rf /", "# note\nrm -rf /",
            "ls \\\n && rm -rf /", 'bash -c "rm -rf /"', "sh -c 'rm -rf ~'", "zsh -lc 'rm -rf /'",
            'eval "rm -rf /"', "echo $(rm -rf /)", 'echo "$(rm -rf /)"', "echo `rm -rf ~`",
            "diff <(rm -rf /) x", "watch -n 1 'rm -rf /'", "bash <<EOF\nrm -rf /\nEOF",
            'bash -c "bash -c \\"rm -rf /\\""', "npm test && git push --force origin main",
        ]
        for cmd in cases:
            with self.subTest(cmd=cmd):
                self.assertEqual(level(cmd), guard.DENY)

    def test_highest_risk_wins_and_reasons_are_reported(self):
        lvl, reasons = guard.evaluate("git reset --hard && rm -rf /", PROJECT)
        self.assertEqual(lvl, guard.DENY)
        self.assertTrue(any("critical path /" in r for r in reasons))

    def test_deep_nesting_fails_safe(self):
        cmd = "rm -rf build"
        for _ in range(8):
            cmd = "bash -c " + guard.shlex.quote(cmd)
        self.assertEqual(level(cmd), guard.ASK)


class HookProtocol(unittest.TestCase):
    def run_hook(self, payload, *args, env=None):
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        proc = subprocess.run([sys.executable, "-I", SCRIPT, *args], input=stdin,
                              capture_output=True, text=True, timeout=10,
                              env={**os.environ, **(env or {})})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.strip()

    def bash(self, command, cwd=PROJECT):
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": cwd,
                "tool_input": {"command": command, "description": "test"}}

    def decision(self, out):
        hso = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "PreToolUse")
        self.assertTrue(hso["permissionDecisionReason"].startswith("guard-dangerous-commands:"))
        return hso["permissionDecision"]

    def test_deny_response(self):
        self.assertEqual(self.decision(self.run_hook(self.bash("rm -rf /"))), "deny")

    def test_ask_response(self):
        self.assertEqual(self.decision(self.run_hook(self.bash("git reset --hard"))), "ask")

    def test_safe_command_produces_no_output(self):
        self.assertEqual(self.run_hook(self.bash("npm test")), "")

    def test_never_answers_allow(self):
        for cmd in ("ls", "git status", "rm -rf node_modules"):
            self.assertNotIn('"allow"', self.run_hook(self.bash(cmd)))

    def test_other_tools_are_ignored(self):
        payload = {"tool_name": "Write", "tool_input": {"file_path": "/etc/passwd", "content": ""}}
        self.assertEqual(self.run_hook(payload), "")

    def test_malformed_input_fails_safe(self):
        for payload in ("not json", "", "[1, 2]", "null",
                        {"tool_name": "Bash"}, {"tool_name": "Bash", "tool_input": "rm -rf /"},
                        {"tool_name": "Bash", "tool_input": {"command": 42}}):
            with self.subTest(payload=payload):
                self.assertEqual(self.decision(self.run_hook(payload)), "ask")

    def test_empty_command_passes(self):
        self.assertEqual(self.run_hook(self.bash("   ")), "")

    def test_dry_run_logs_but_never_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "dry.log")
            for args, env in ((("--dry-run",), {}), ((), {"CLAUDE_GUARD_MODE": "dry-run"})):
                out = self.run_hook(self.bash("rm -rf /"), *args, env={"CLAUDE_GUARD_LOG": log, **env})
                self.assertEqual(out, "")
            with open(log) as f:
                entries = [json.loads(line) for line in f]
            self.assertEqual([e["decision"] for e in entries], ["deny", "deny"])

    def test_check_cli_exit_codes(self):
        for cmd, code in (("ls", 0), ("git reset --hard", 1), ("rm -rf /", 2)):
            proc = subprocess.run([sys.executable, "-I", SCRIPT, "--check", cmd],
                                  capture_output=True, text=True, timeout=10)
            self.assertEqual(proc.returncode, code, proc.stdout)

    def test_inspected_command_is_never_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = os.path.join(tmp, "executed")
            cmd = f"touch {marker} && echo $(touch {marker}2) && rm -rf /"
            self.assertEqual(self.decision(self.run_hook(self.bash(cmd, cwd=tmp))), "deny")
            self.assertFalse(os.path.exists(marker))
            self.assertFalse(os.path.exists(marker + "2"))


if __name__ == "__main__":
    unittest.main()
