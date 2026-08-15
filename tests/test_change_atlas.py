from pathlib import Path
import json
import subprocess

from change_atlas.analysis import explain_file
from change_atlas.cli import main
from change_atlas.git_history import hotspots
from change_atlas.graph import build_temporal_graph


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def commit(repo: Path, message: str, body: str = "") -> str:
    command = ["commit", "-m", message]
    if body:
        command.extend(["-m", body])
    git(repo, "add", ".")
    git(repo, *command)
    return git(repo, "rev-parse", "HEAD")


def history_repo(tmp_path: Path) -> tuple[Path, list[str]]:
    repo = tmp_path / "history"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Test Archaeologist")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "remote", "add", "origin", "git@github.com:example/history.git")

    (repo / "README.md").write_text("# Fixture\n", encoding="utf-8")
    commits = [commit(repo, "docs: start repository")]

    (repo / "service.py").write_text(
        "def retry(operation):\n    return operation()\n",
        encoding="utf-8",
    )
    commits.append(commit(repo, "feat: add retry policy", "Protect requests from transient failures."))

    (repo / "service.py").write_text(
        "def retry(operation, attempts=3):\n    for _ in range(attempts):\n        try:\n            return operation()\n        except OSError:\n            pass\n    raise RuntimeError('retry budget exhausted')\n",
        encoding="utf-8",
    )
    (repo / "test_service.py").write_text("def test_retry_budget():\n    assert True\n", encoding="utf-8")
    commits.append(commit(repo, "fix: cap retry budget", "Avoid infinite retries during outages."))
    return repo, commits


def test_file_story_is_grounded_in_commit_citations(tmp_path: Path):
    repo, commits = history_repo(tmp_path)

    story = explain_file(repo, "service.py")

    assert len(story.evidence) == 2
    assert story.evidence[0].sha == commits[-1]
    assert story.evidence[-1].sha == commits[-2]
    assert story.evidence[0].url == f"https://github.com/example/history/commit/{commits[-1]}"
    assert "feat: add retry policy" in story.summary
    assert "fix: cap retry budget" in story.summary


def test_hotspots_rank_repeatedly_changed_files_first(tmp_path: Path):
    repo, _ = history_repo(tmp_path)

    ranked = hotspots(repo)

    assert ranked[0].path == "service.py"
    assert ranked[0].commits == 2
    assert ranked[0].churn > 0


def test_cli_can_emit_machine_readable_evidence(tmp_path: Path, capsys):
    repo, commits = history_repo(tmp_path)

    exit_code = main(["--repo", str(repo), "file", "service.py", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["path"] == "service.py"
    assert payload["evidence"][0]["sha"] == commits[-1]


def test_temporal_graph_links_commits_to_changed_files(tmp_path: Path):
    repo, commits = history_repo(tmp_path)

    graph = build_temporal_graph(repo)
    commit_nodes = [node for node in graph.nodes if node.kind == "commit"]
    file_nodes = [node for node in graph.nodes if node.kind == "file"]

    assert len(commit_nodes) == 3
    assert {node.label for node in file_nodes} == {"README.md", "service.py", "test_service.py"}
    assert len(graph.edges) == 4
    assert any(
        edge.source == f"commit:{commits[-1]}"
        and edge.target == "file:service.py"
        and edge.kind == "touches"
        for edge in graph.edges
    )
