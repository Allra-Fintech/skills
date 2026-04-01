from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "skills" / "frontend" / "ariadne" / "scripts" / "api_parity_state.py"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def run_git(root: str, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def install_fake_gh(temp_dir: str, fixture_path: Path) -> Path:
    bin_dir = Path(temp_dir) / ".fake-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    gh_path = bin_dir / "gh"
    gh_path.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

mode = os.environ.get("ARIADNE_GH_MODE", "ok")
fixture_path = os.environ.get("ARIADNE_GH_FIXTURES")
fixture = json.loads(Path(fixture_path).read_text()) if fixture_path else {}
args = sys.argv[1:]

if args == ["--version"]:
    print("gh version test")
    raise SystemExit(0)

if args[:2] == ["auth", "status"]:
    if mode == "auth_fail":
        print("authentication failed", file=sys.stderr)
        raise SystemExit(1)
    print("logged in")
    raise SystemExit(0)

if not args or args[0] != "api":
    print("unsupported gh invocation", file=sys.stderr)
    raise SystemExit(1)

if mode == "api_fail":
    print("api failure", file=sys.stderr)
    raise SystemExit(1)

endpoint = args[1]
parsed = urlparse("https://example.test/" + endpoint)
path = parsed.path.lstrip("/")

if path == "repos/example/monorepo":
    print(json.dumps(fixture.get("repo", {})))
    raise SystemExit(0)

if path == "repos/example/monorepo/pulls":
    print(json.dumps(fixture.get("pulls", [])))
    raise SystemExit(0)

if path.startswith("repos/example/monorepo/pulls/") and path.endswith("/files"):
    number = path.split("/")[4]
    files = [{"filename": name} for name in fixture.get("files", {}).get(number, [])]
    print(json.dumps(files))
    raise SystemExit(0)

print("unknown endpoint: " + endpoint, file=sys.stderr)
raise SystemExit(1)
""",
        encoding="utf-8",
    )
    gh_path.chmod(0o755)
    return bin_dir


class AriadneCliTest(unittest.TestCase):
    def run_cli(self, *args: str, cwd: str, env: dict[str, str] | None = None, check: bool = True) -> tuple[int, str]:
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            env=run_env,
            check=False,
        )
        if check and completed.returncode != 0:
            raise subprocess.CalledProcessError(completed.returncode, completed.args, completed.stdout, completed.stderr)
        return completed.returncode, completed.stdout

    def run_cli_json(self, *args: str, cwd: str, env: dict[str, str] | None = None, check: bool = True) -> tuple[int, dict[str, object]]:
        code, stdout = self.run_cli(*args, cwd=cwd, env=env, check=check)
        return code, json.loads(stdout)

    def create_workspace(self, temp_dir: str) -> None:
        root = Path(temp_dir)
        write_text(root / "backend" / "orders.controller.ts", "router.get('/orders', handler)\nrouter.post('/orders', handler)\n")
        write_text(root / "backend" / "users.py", "@app.get('/users/<user_id>')\ndef show_user():\n    return {}\n")
        write_text(root / "src" / "api" / "orders.ts", "export async function getOrders() { return fetch('/orders'); }\n")
        write_text(root / "src" / "api" / "users.ts", "export async function getUser(id) { return fetch(`/users/${id}`); }\n")
        write_text(root / "src" / "api" / "ghost.ts", "export async function getGhost() { return axios.get('/ghosts'); }\n")

    def init_git_repo(self, temp_dir: str) -> None:
        run_git(temp_dir, "init")
        run_git(temp_dir, "config", "user.email", "codex@example.com")
        run_git(temp_dir, "config", "user.name", "Codex")
        run_git(temp_dir, "remote", "add", "origin", "https://github.com/example/monorepo.git")
        run_git(temp_dir, "add", ".")
        run_git(temp_dir, "commit", "-m", "initial")

    def gh_env(self, temp_dir: str, fixture: dict[str, object], *, mode: str = "ok") -> dict[str, str]:
        fixture_index = len(list(Path(temp_dir).glob("gh-fixture-*.json")))
        fixture_path = Path(temp_dir) / f"gh-fixture-{fixture_index}.json"
        write_json(fixture_path, fixture)
        fake_bin = install_fake_gh(temp_dir, fixture_path)
        return {
            "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
            "ARIADNE_GH_FIXTURES": str(fixture_path),
            "ARIADNE_GH_MODE": mode,
        }

    def load_state(self, temp_dir: str) -> dict[str, object]:
        return json.loads((Path(temp_dir) / ".ariadne" / "state.json").read_text(encoding="utf-8"))

    def test_init_autodetects_remote_and_seeds_pr_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.create_workspace(temp_dir)
            self.init_git_repo(temp_dir)
            env = self.gh_env(
                temp_dir,
                {
                    "repo": {"default_branch": "main"},
                    "pulls": [
                        {"number": 101, "merged_at": "2026-04-01T09:00:00Z", "title": "seed"},
                    ],
                    "files": {},
                },
            )

            _, payload = self.run_cli_json("init", "--root", temp_dir, "--backend-root", "backend", "--frontend-root", "src", cwd=temp_dir, env=env)

            state_dir = Path(payload["state_dir"])
            self.assertTrue((state_dir / "config.yaml").exists())
            self.assertTrue((state_dir / "catalog.json").exists())
            self.assertTrue((state_dir / "state.json").exists())
            self.assertTrue((state_dir / "waivers.yaml").exists())
            self.assertEqual(payload["remote"]["repo"], "example/monorepo")
            self.assertEqual(payload["remote"]["base_branch"], "main")
            self.assertEqual(payload["cursor"]["last_processed_pr_number"], 101)
            self.assertEqual(payload["summary"]["status_counts"]["matched"], 1)
            self.assertEqual(payload["summary"]["status_counts"]["needs-review"], 3)
            self.assertEqual(payload["summary"]["status_counts"]["mismatch"], 0)
            self.assertEqual(payload["summary"]["status_counts"]["missing"], 0)

            state_payload = self.load_state(temp_dir)
            self.assertEqual(state_payload["remote"]["repo"], "example/monorepo")
            self.assertEqual(state_payload["cursor"]["last_processed_pr_number"], 101)

    def test_check_uses_remote_pr_cursor_and_candidate_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.create_workspace(temp_dir)
            self.init_git_repo(temp_dir)
            env = self.gh_env(
                temp_dir,
                {
                    "repo": {"default_branch": "main"},
                    "pulls": [
                        {"number": 101, "merged_at": "2026-04-01T09:00:00Z", "title": "seed"},
                    ],
                    "files": {"101": ["src/api/orders.ts"]},
                },
            )
            self.run_cli_json("init", "--root", temp_dir, "--backend-root", "backend", "--frontend-root", "src", cwd=temp_dir, env=env)

            write_text(Path(temp_dir) / "src" / "api" / "orders.ts", "export async function getOrders() { return axios.post('/orders'); }\n")
            env = self.gh_env(
                temp_dir,
                {
                    "repo": {"default_branch": "main"},
                    "pulls": [
                        {"number": 101, "merged_at": "2026-04-01T09:00:00Z", "title": "seed"},
                        {"number": 102, "merged_at": "2026-04-02T09:00:00Z", "title": "orders change"},
                    ],
                    "files": {
                        "101": ["src/api/orders.ts"],
                        "102": ["src/api/orders.ts"],
                    },
                },
            )

            _, payload = self.run_cli_json("check", "--root", temp_dir, cwd=temp_dir, env=env, check=False)
            self.assertEqual(payload["repo"], "example/monorepo")
            self.assertEqual(payload["base_branch"], "main")
            self.assertEqual(payload["processed_pr_numbers"], [102])
            self.assertEqual(payload["candidate_api_keys"], ["GET /orders", "POST /orders"])
            self.assertIn("src/api/orders.ts", payload["changed_files"])
            self.assertFalse(payload["full_rescan"])
            self.assertEqual(payload["summary"]["status_counts"]["mismatch"], 0)
            self.assertGreaterEqual(payload["summary"]["status_counts"]["needs-review"], 3)

            state_payload = self.load_state(temp_dir)
            self.assertEqual(state_payload["cursor"]["last_processed_pr_number"], 102)

    def test_remote_failure_does_not_mutate_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.create_workspace(temp_dir)
            self.init_git_repo(temp_dir)
            env = self.gh_env(
                temp_dir,
                {
                    "repo": {"default_branch": "main"},
                    "pulls": [{"number": 101, "merged_at": "2026-04-01T09:00:00Z", "title": "seed"}],
                    "files": {},
                },
            )
            self.run_cli_json("init", "--root", temp_dir, "--backend-root", "backend", "--frontend-root", "src", cwd=temp_dir, env=env)
            before_state = (Path(temp_dir) / ".ariadne" / "state.json").read_text(encoding="utf-8")

            code, payload = self.run_cli_json("check", "--root", temp_dir, cwd=temp_dir, env={**env, "ARIADNE_GH_MODE": "auth_fail"}, check=False)
            self.assertEqual(code, 2)
            self.assertIn("GitHub CLI", payload["hint"])
            after_state = (Path(temp_dir) / ".ariadne" / "state.json").read_text(encoding="utf-8")
            self.assertEqual(before_state, after_state)

    def test_resolve_accepts_mismatch_and_manual_resolution_conflict_is_sticky(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.create_workspace(temp_dir)
            self.init_git_repo(temp_dir)
            env = self.gh_env(
                temp_dir,
                {
                    "repo": {"default_branch": "main"},
                    "pulls": [{"number": 101, "merged_at": "2026-04-01T09:00:00Z", "title": "seed"}],
                    "files": {},
                },
            )
            self.run_cli_json("init", "--root", temp_dir, "--backend-root", "backend", "--frontend-root", "src", cwd=temp_dir, env=env)

            _, mismatch_payload = self.run_cli_json(
                "resolve",
                "--root",
                temp_dir,
                "--api-key",
                "GET /ghosts",
                "--status",
                "mismatch",
                "--note",
                "Confirmed frontend-only experimental endpoint.",
                cwd=temp_dir,
                env=env,
            )
            self.assertEqual(mismatch_payload["status"], "mismatch")

            _, matched_payload = self.run_cli_json(
                "resolve",
                "--root",
                temp_dir,
                "--api-key",
                "GET /orders",
                "--status",
                "matched",
                "--note",
                "Confirmed GET endpoint.",
                cwd=temp_dir,
                env=env,
            )
            self.assertEqual(matched_payload["status"], "matched")

            write_text(Path(temp_dir) / "src" / "api" / "orders.ts", "export async function getOrders() { return axios.post('/orders'); }\n")
            env = self.gh_env(
                temp_dir,
                {
                    "repo": {"default_branch": "main"},
                    "pulls": [
                        {"number": 101, "merged_at": "2026-04-01T09:00:00Z", "title": "seed"},
                        {"number": 102, "merged_at": "2026-04-02T09:00:00Z", "title": "orders change"},
                    ],
                    "files": {"102": ["src/api/orders.ts"]},
                },
            )
            self.run_cli_json("check", "--root", temp_dir, cwd=temp_dir, env=env, check=False)

            state_payload = self.load_state(temp_dir)
            records = {record["api_key"]: record for record in state_payload["records"]}
            self.assertEqual(records["GET /ghosts"]["manual_resolution"]["status"], "mismatch")
            self.assertEqual(records["GET /orders"]["status"], "needs-review")
            self.assertEqual(records["GET /orders"]["reason_code"], "manual-resolution-conflict")
            self.assertEqual(records["GET /orders"]["manual_resolution"]["status"], "matched")

    def test_report_shows_pr_context_and_resolve_waiver(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.create_workspace(temp_dir)
            self.init_git_repo(temp_dir)
            env = self.gh_env(
                temp_dir,
                {
                    "repo": {"default_branch": "main"},
                    "pulls": [
                        {"number": 101, "merged_at": "2026-04-01T09:00:00Z", "title": "seed"},
                        {"number": 102, "merged_at": "2026-04-02T09:00:00Z", "title": "users review"},
                    ],
                    "files": {"102": ["src/api/users.ts"]},
                },
            )
            self.run_cli_json("init", "--root", temp_dir, "--backend-root", "backend", "--frontend-root", "src", cwd=temp_dir, env=self.gh_env(temp_dir, {"repo": {"default_branch": "main"}, "pulls": [{"number": 101, "merged_at": "2026-04-01T09:00:00Z", "title": "seed"}], "files": {}}))
            self.run_cli_json(
                "resolve",
                "--root",
                temp_dir,
                "--api-key",
                "GET /users/{user_id}",
                "--status",
                "waived",
                "--note",
                "Template literal path is intentionally accepted.",
                cwd=temp_dir,
                env=env,
            )
            self.run_cli_json("check", "--root", temp_dir, cwd=temp_dir, env=env, check=False)

            _, output = self.run_cli("report", "--root", temp_dir, cwd=temp_dir, env=env)
            self.assertIn("원격 저장소: example/monorepo", output)
            self.assertIn("기준 브랜치: main", output)
            self.assertIn("처리 PR 범위: #102", output)
            self.assertIn("처리 PR 수: 1", output)
            self.assertIn("## waiver 항목", output)

    def test_removed_legacy_commands_return_clear_v2_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.create_workspace(temp_dir)
            self.init_git_repo(temp_dir)
            env = self.gh_env(temp_dir, {"repo": {"default_branch": "main"}, "pulls": [], "files": {}})
            code, payload = self.run_cli_json("finalize-check", "--root", temp_dir, cwd=temp_dir, env=env, check=False)
            self.assertEqual(code, 2)
            self.assertIn("removed in Ariadne v2", payload["error"])
            self.assertIn("init, check, report, or resolve", payload["hint"])


if __name__ == "__main__":
    unittest.main()
