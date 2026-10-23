#!/usr/bin/env python3
"""Tests for protect.py. Run: python3 -m unittest -v test_protect (from this directory)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import protect  # noqa: E402

SCRIPT = os.path.join(HERE, "protect.py")


class Sandbox(unittest.TestCase):
    """Each test gets a fake HOME, a project dir, and its own config file."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.home = os.path.join(self.tmp, "home")
        self.proj = os.path.join(self.home, "proj")
        os.makedirs(os.path.join(self.proj, "src"))
        self.config = os.path.join(self.tmp, "protected-paths.json")
        self._old = (os.environ.get("HOME"), protect.CONFIG_PATH)
        os.environ["HOME"] = self.home
        protect.CONFIG_PATH = self.config

    def tearDown(self):
        os.environ["HOME"], protect.CONFIG_PATH = self._old
        shutil.rmtree(self.tmp)

    def write_config(self, cfg):
        with open(self.config, "w") as f:
            f.write(cfg if isinstance(cfg, str) else json.dumps(cfg))

    def action(self, path, cwd=None):
        return protect.evaluate(path, cwd or self.proj)[0]

    def assertProtected(self, paths, expected="deny", cwd=None):
        for p in paths:
            with self.subTest(path=p):
                self.assertEqual(self.action(p, cwd), expected, protect.evaluate(p, cwd or self.proj)[1])


class BuiltInRules(Sandbox):
    def test_exact_names_and_globs_are_denied(self):
        self.assertProtected([
            ".env", ".env.local", ".env.production", "config/prod.env",
            "id_rsa", "deploy/id_ed25519", "server.pem", "tls/server.key", "cert.p12",
            "keystore.jks", "vault.kdbx", ".netrc", ".pgpass", ".git-credentials",
            "credentials.json", "client_secret_123.json", "service-account-prod.json",
            "config/secrets.yml", "terraform.tfstate", "terraform.tfstate.backup",
            "~/.ssh/config", "~/.ssh/authorized_keys", "~/.ssh/id_rsa.pub", "~/.aws/credentials",
            "~/.gnupg/pubring.kbx", "~/.kube/config", "~/.docker/config.json", "~/.npmrc",
            "~/.config/gcloud/application_default_credentials.json", "~/.claude/.credentials.json",
            ".ENV", "ID_RSA",  # name rules are case-insensitive
        ])

    def test_direnv_file_requires_approval(self):
        self.assertProtected([".envrc", "sub/dir/.envrc", ".ENVRC"], "ask")

    def test_guard_configuration_requires_approval(self):
        self.assertProtected(["~/.claude/settings.json", "~/.claude/hooks/guard/guard.py"], "ask")

    def test_similar_names_stay_editable(self):
        self.assertProtected([
            "src/env.ts", "src/environment.ts", ".env-example", ".envrc.example",
            ".env.example", ".env.sample", ".env.template", ".env.dist",
            "config.json", "tsconfig.json", "src/config/settings.py", "src/keys.ts",
            "api_key_test.go", "src/token.py", "secret_santa.md", "docs/credentials.md",
            "credentials.py", "secrets.py", "id_rsa.pub", "id_rsa_test.py", "keymap.json",
            "cert.pem.md", "README.md", "package.json", ".npmrc", "terraform.tfvars",
            "~/notes/ssh.md", "~/.sshrc", "~/.aws-notes.txt", "~/.claude/CLAUDE.md",
            "~/.claude/agents/code-reviewer.md", "~/.claude/skills/x/SKILL.md",
        ], expected=None)


class PathNormalization(Sandbox):
    def test_absolute_and_relative_forms(self):
        self.assertProtected([
            os.path.join(self.proj, ".env"), ".env", "./.env", "src/../.env",
            os.path.join(self.home, ".ssh", "id_rsa"), "../.ssh/id_rsa",
            "src/../../.aws/credentials", "~/proj/../.ssh/known_hosts",
            os.path.join(self.proj, "src", "..", "..", ".kube", "config"),
        ])

    def test_relative_paths_use_cwd(self):
        self.assertEqual(self.action("credentials", cwd=os.path.join(self.home, ".aws")), "deny")
        self.assertIsNone(self.action("credentials", cwd=self.proj))

    def test_traversal_out_of_protected_dir_is_editable(self):
        self.assertIsNone(self.action("~/.ssh/../notes.txt"))

    def test_symlink_to_protected_file_is_denied(self):
        os.makedirs(os.path.join(self.home, ".ssh"))
        key = os.path.join(self.home, ".ssh", "id_ed25519")
        open(key, "w").close()
        os.symlink(key, os.path.join(self.proj, "harmless.txt"))
        action, reason = protect.evaluate("harmless.txt", self.proj)
        self.assertEqual(action, "deny")
        self.assertIn("symlink target", reason)

    def test_symlinked_directory_into_credential_store_is_denied(self):
        os.makedirs(os.path.join(self.home, ".aws"))
        os.symlink(os.path.join(self.home, ".aws"), os.path.join(self.proj, "awslink"))
        self.assertEqual(self.action("awslink/credentials"), "deny")  # file need not exist

    def test_protected_name_symlinked_elsewhere_is_still_denied(self):
        target = os.path.join(self.proj, "src", "plain.txt")
        open(target, "w").close()
        os.symlink(target, os.path.join(self.proj, ".env"))
        self.assertEqual(self.action(".env"), "deny")

    def test_exception_name_cannot_launder_a_symlink(self):
        open(os.path.join(self.proj, ".env"), "w").close()
        os.symlink(os.path.join(self.proj, ".env"), os.path.join(self.proj, ".env.example"))
        self.assertEqual(self.action(".env.example"), "deny")


class UserConfiguration(Sandbox):
    def test_user_rules_exceptions_and_actions(self):
        self.write_config({
            "protected": [
                "config/master.key",
                {"pattern": "~/work/prod-secrets/", "name": "prod-secrets"},
                {"pattern": "deploy/*.yaml", "name": "deploy-manifests", "action": "ask"},
                "/opt/app/settings.ini",
            ],
            "exceptions": ["tests/fixtures/*.pem", "~/.ssh/config"],
        })
        self.assertProtected(["config/master.key", "~/work/prod-secrets/db/pass.txt",
                              "/opt/app/settings.ini", ".env"])
        self.assertProtected(["deploy/prod.yaml", "src/deploy/staging.yaml"], "ask")
        self.assertProtected(["tests/fixtures/cert.pem", "~/.ssh/config", "deploy/README.md",
                              "~/work/prod-secrets-notes.md", "config/master.key.md"], None)
        self.assertEqual(self.action("server.pem"), "deny")          # exception is scoped
        self.assertEqual(self.action("~/.ssh/id_rsa"), "deny")

    def test_deny_wins_over_ask_when_rules_overlap(self):
        self.write_config({"protected": [{"pattern": "*.env", "action": "ask"}]})
        self.assertEqual(self.action("prod.env"), "deny")

    def test_defaults_can_be_disabled(self):
        self.write_config({"use_default_rules": False, "protected": ["only-this.txt"]})
        self.assertIsNone(self.action(".env"))
        self.assertEqual(self.action("only-this.txt"), "deny")

    def test_invalid_config_keeps_builtin_denies_and_asks_otherwise(self):
        for bad in ("{not json", "[]", json.dumps({"protected": [{"pattern": 5}]}),
                    json.dumps({"protected": [{"pattern": "x", "action": "maybe"}]}),
                    json.dumps({"exceptions": [None]})):
            with self.subTest(config=bad):
                self.write_config(bad)
                self.assertEqual(self.action(".env"), "deny")
                action, reason = protect.evaluate("src/app.py", self.proj)
                self.assertEqual(action, "ask")
                self.assertIn("config is invalid", reason)

    def test_missing_config_uses_defaults(self):
        self.assertFalse(os.path.exists(self.config))
        self.assertEqual(self.action(".env"), "deny")
        self.assertIsNone(self.action("src/app.py"))


class HookProtocol(Sandbox):
    def run_hook(self, payload):
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        proc = subprocess.run([sys.executable, "-I", SCRIPT], input=stdin, capture_output=True,
                              text=True, timeout=10,
                              env={**os.environ, "HOME": self.home, "CLAUDE_PROTECT_CONFIG": self.config})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.strip()

    def call(self, tool, **tool_input):
        return {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": self.proj, "tool_input": tool_input}

    def decision(self, out):
        hso = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "PreToolUse")
        self.assertTrue(hso["permissionDecisionReason"].startswith("protect-sensitive-files:"))
        return hso["permissionDecision"], hso["permissionDecisionReason"]

    def test_each_modification_tool_is_checked(self):
        for payload in (self.call("Write", file_path=".env", content="X=1"),
                        self.call("Edit", file_path=".env", old_string="a", new_string="b"),
                        self.call("MultiEdit", file_path=".env", edits=[]),
                        self.call("NotebookEdit", notebook_path="~/.aws/credentials", new_source="")):
            with self.subTest(tool=payload["tool_name"]):
                self.assertEqual(self.decision(self.run_hook(payload))[0], "deny")

    def test_editable_file_produces_no_output(self):
        self.assertEqual(self.run_hook(self.call("Edit", file_path="src/app.py",
                                                 old_string="a", new_string="b")), "")

    def test_reason_names_path_and_rule_but_never_file_contents(self):
        secret = "sk-live-DO-NOT-LEAK-123"
        with open(os.path.join(self.proj, ".env"), "w") as f:
            f.write(f"API_KEY={secret}\n")
        out = self.run_hook(self.call("Write", file_path=".env", content=f"API_KEY={secret}x"))
        action, reason = self.decision(out)
        self.assertEqual(action, "deny")
        self.assertIn("'.env'", reason)
        self.assertIn("env-file", reason)
        self.assertNotIn(secret, out)

    def test_never_answers_allow(self):
        self.assertNotIn('"allow"', self.run_hook(self.call("Write", file_path="a.txt", content="")))

    def test_malformed_or_unexpected_payloads_fail_safe(self):
        for payload in ("not json", "", "[]", "null", {"tool_name": "Write"},
                        {"tool_name": "Write", "tool_input": "x"},
                        self.call("Write", content="no path"), self.call("Write", file_path=""),
                        self.call("Write", file_path=42), self.call("Write", file_path="a\x00b"),
                        self.call("FutureEditTool", target="x")):
            with self.subTest(payload=payload):
                self.assertEqual(self.decision(self.run_hook(payload))[0], "ask")

    def test_check_cli(self):
        env = {**os.environ, "HOME": self.home, "CLAUDE_PROTECT_CONFIG": self.config}
        for path, code in (("src/app.py", 0), ("~/.claude/settings.json", 1), (".env", 2)):
            proc = subprocess.run([sys.executable, "-I", SCRIPT, "--check", path], cwd=self.proj,
                                  capture_output=True, text=True, timeout=10, env=env)
            self.assertEqual(proc.returncode, code, proc.stdout)


class InstalledSettings(unittest.TestCase):
    """Checks the real ~/.claude/settings.json after installation."""

    def test_settings_keep_existing_entries_and_register_hook(self):
        path = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
        if not os.path.exists(path):
            self.skipTest("no user settings file")
        with open(path) as f:
            settings = json.load(f)
        pre = settings.get("hooks", {}).get("PreToolUse", [])
        commands = {m.get("matcher"): [h.get("command", "") for h in m.get("hooks", [])] for m in pre}
        if not any("protect.py" in c for cs in commands.values() for c in cs):
            self.skipTest("hook not installed yet")
        self.assertEqual(settings.get("tui"), "fullscreen")
        self.assertTrue(any("guard.py" in c for c in commands.get("Bash", [])))
        file_matcher = next(m for m, cs in commands.items() if any("protect.py" in c for c in cs))
        for tool in ("Write", "Edit", "NotebookEdit"):
            self.assertIn(tool, file_matcher.split("|"))


if __name__ == "__main__":
    unittest.main()
