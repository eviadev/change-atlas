"""Read Git evidence without a shell or network dependency."""

from pathlib import Path
import re
import subprocess

from .models import CommitEvidence, FileChange, Hotspot


class GitHistoryError(RuntimeError):
    """Raised when a repository cannot provide the requested evidence."""


def _run_git(repo: str | Path, *args: str) -> str:
    repository = Path(repo).resolve()
    command = ["git", "-C", str(repository), *args]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "Git command failed."
        raise GitHistoryError(detail)
    return completed.stdout


def repository_url(repo: str | Path) -> str | None:
    try:
        remote = _run_git(repo, "config", "--get", "remote.origin.url").strip()
    except GitHistoryError:
        return None
    if not remote:
        return None
    ssh_match = re.fullmatch(r"git@([^:]+):(.+?)(?:\.git)?", remote)
    if ssh_match:
        return f"https://{ssh_match.group(1)}/{ssh_match.group(2).removesuffix('.git')}"
    return remote.removesuffix(".git")


def _parse_numstat(line: str) -> FileChange | None:
    parts = line.split("\t", 2)
    if len(parts) != 3:
        return None
    additions_raw, deletions_raw, path = parts
    additions = int(additions_raw) if additions_raw.isdigit() else None
    deletions = int(deletions_raw) if deletions_raw.isdigit() else None
    return FileChange(path=path, additions=additions, deletions=deletions)


def _parse_commit_records(output: str, remote: str | None) -> tuple[CommitEvidence, ...]:
    evidence: list[CommitEvidence] = []
    for raw_record in output.split("\x1e"):
        record = raw_record.strip("\n")
        if not record:
            continue
        header, *change_lines = record.splitlines()
        fields = header.split("\x1f", 4)
        if len(fields) != 5:
            continue
        sha, author, authored_at, subject, body = fields
        changes = tuple(
            change
            for line in change_lines
            if (change := _parse_numstat(line)) is not None
        )
        evidence.append(
            CommitEvidence(
                sha=sha,
                author=author,
                authored_at=authored_at,
                subject=subject,
                body=body.strip(),
                changes=changes,
                url=f"{remote}/commit/{sha}" if remote else None,
            )
        )
    return tuple(evidence)


def file_commits(
    repo: str | Path,
    path: str,
    *,
    limit: int = 20,
) -> tuple[CommitEvidence, ...]:
    """Return newest-first commits that explain a file, following renames."""

    if limit < 1:
        raise ValueError("limit must be greater than zero")
    output = _run_git(
        repo,
        "log",
        "--follow",
        f"--max-count={limit}",
        "--date=iso-strict",
        "--format=%x1e%H%x1f%aN%x1f%aI%x1f%s%x1f%b",
        "--numstat",
        "--",
        path,
    )
    return _parse_commit_records(output, repository_url(repo))


def repository_commits(
    repo: str | Path,
    *,
    limit: int = 200,
) -> tuple[CommitEvidence, ...]:
    """Return repository-wide commit evidence for temporal graph construction."""

    if limit < 1:
        raise ValueError("limit must be greater than zero")
    output = _run_git(
        repo,
        "log",
        f"--max-count={limit}",
        "--date=iso-strict",
        "--format=%x1e%H%x1f%aN%x1f%aI%x1f%s%x1f%b",
        "--numstat",
    )
    return _parse_commit_records(output, repository_url(repo))


def hotspots(repo: str | Path, *, limit: int = 10) -> tuple[Hotspot, ...]:
    """Rank frequently changed files by commit count, then line churn."""

    if limit < 1:
        raise ValueError("limit must be greater than zero")
    output = _run_git(repo, "log", "--format=%x1e%H", "--numstat")
    by_path: dict[str, dict[str, int | set[str]]] = {}
    for raw_record in output.split("\x1e"):
        record = raw_record.strip("\n")
        if not record:
            continue
        current_sha, *change_lines = record.splitlines()
        for line in change_lines:
            change = _parse_numstat(line)
            if change is None:
                continue
            entry = by_path.setdefault(change.path, {"commits": set(), "churn": 0})
            commits = entry["commits"]
            assert isinstance(commits, set)
            commits.add(current_sha)
            churn = (change.additions or 0) + (change.deletions or 0)
            entry["churn"] = int(entry["churn"]) + churn

    ranked = [
        Hotspot(path=path, commits=len(values["commits"]), churn=int(values["churn"]))
        for path, values in by_path.items()
    ]
    ranked.sort(key=lambda item: (-item.commits, -item.churn, item.path))
    return tuple(ranked[:limit])
