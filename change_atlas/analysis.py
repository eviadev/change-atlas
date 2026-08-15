"""Build concise answers that remain anchored to Git evidence."""

from pathlib import Path

from .git_history import file_commits
from .models import FileStory


def explain_file(
    repo: str | Path,
    path: str,
    *,
    limit: int = 10,
) -> FileStory:
    evidence = file_commits(repo, path, limit=limit)
    if not evidence:
        return FileStory(
            path=path,
            summary="No commit evidence was found for this path.",
            evidence=(),
        )

    origin = evidence[-1]
    latest = evidence[0]
    summary = (
        f"{path} is first explained by {origin.short_sha} ({origin.subject}). "
        f"Its latest recorded change is {latest.short_sha} ({latest.subject}). "
        f"The answer is backed by {len(evidence)} commit citation"
        f"{'s' if len(evidence) != 1 else ''}."
    )
    return FileStory(path=path, summary=summary, evidence=evidence)
