"""Read Git evidence without a shell or network dependency."""

from pathlib import Path
import re
import subprocess

from .models import BlamedLine, CommitEvidence, FileChange, Hotspot


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
        metadata, separator, changes = record.partition("\x1d")
        if not separator:
            metadata, *legacy_changes = record.splitlines()
            change_lines = legacy_changes
        else:
            change_lines = changes.strip("\n").splitlines()
        fields = metadata.strip("\n").split("\x1f", 4)
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
        "--format=%x1e%H%x1f%aN%x1f%aI%x1f%s%x1f%b%x1d",
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
        "--format=%x1e%H%x1f%aN%x1f%aI%x1f%s%x1f%b%x1d",
        "--numstat",
    )
    return _parse_commit_records(output, repository_url(repo))


def commit_evidence(repo: str | Path, revision: str) -> CommitEvidence:
    """Return one commit with the same evidence contract used by file stories."""

    output = _run_git(
        repo,
        "show",
        "--date=iso-strict",
        "--format=%x1e%H%x1f%aN%x1f%aI%x1f%s%x1f%b%x1d",
        "--numstat",
        revision,
        "--",
    )
    matches = _parse_commit_records(output, repository_url(repo))
    if len(matches) != 1:
        raise GitHistoryError(f"could not resolve commit evidence for {revision}")
    return matches[0]


def blame_line(repo: str | Path, path: str, line: int) -> BlamedLine:
    """Attribute one current line to the commit that last changed it."""

    if line < 1:
        raise ValueError("line must be greater than zero")
    output = _run_git(
        repo,
        "blame",
        "--line-porcelain",
        "--root",
        "-L",
        f"{line},{line}",
        "HEAD",
        "--",
        path,
    )
    lines = output.splitlines()
    if not lines:
        raise GitHistoryError(f"no blame evidence found for {path}:{line}")
    header = lines[0].split()
    if len(header) < 3 or not re.fullmatch(r"[0-9a-f]{40}", header[0]):
        raise GitHistoryError(f"unexpected blame evidence for {path}:{line}")
    content_line = next((item[1:] for item in lines if item.startswith("\t")), None)
    if content_line is None:
        raise GitHistoryError(f"no source content found for {path}:{line}")
    filename = next(
        (item.removeprefix("filename ") for item in lines if item.startswith("filename ")),
        path,
    )
    return BlamedLine(
        path=filename,
        line=line,
        original_line=int(header[1]),
        content=content_line,
        commit=commit_evidence(repo, header[0]),
    )


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
