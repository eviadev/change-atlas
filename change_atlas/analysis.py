"""Build concise answers that remain anchored to Git evidence."""

from pathlib import Path
import re

from .git_history import blame_line, file_commits
from .models import CommitEvidence, FileStory, LineStory, ReferenceEvidence


FULL_GITHUB_REFERENCE = re.compile(
    r"https://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/"
    r"(?P<kind>issues|pull)/(?P<number>\d+)"
)
LOCAL_GITHUB_REFERENCE = re.compile(r"(?<![\w/])#(?P<number>\d+)\b")
COMMIT_REFERENCE = re.compile(r"(?<![0-9a-f])(?P<sha>[0-9a-f]{7,40})(?![0-9a-f])", re.I)


def _repository_base(commit: CommitEvidence) -> str | None:
    if not commit.url or "/commit/" not in commit.url:
        return None
    return commit.url.rsplit("/commit/", 1)[0]


def extract_references(commit: CommitEvidence) -> tuple[ReferenceEvidence, ...]:
    """Extract inspectable GitHub references from commit intent text."""

    text = f"{commit.subject}\n{commit.body}"
    base = _repository_base(commit)
    references: list[ReferenceEvidence] = []
    seen: set[tuple[str, str]] = set()

    def add(reference: ReferenceEvidence) -> None:
        key = (reference.kind, reference.url or reference.value)
        if key not in seen:
            references.append(reference)
            seen.add(key)

    for match in FULL_GITHUB_REFERENCE.finditer(text):
        kind = "pull_request" if match.group("kind") == "pull" else "issue"
        url = match.group(0)
        add(
            ReferenceEvidence(
                kind=kind,
                label=f"{match.group('owner')}/{match.group('repo')}#{match.group('number')}",
                value=match.group("number"),
                url=url,
            )
        )

    for match in LOCAL_GITHUB_REFERENCE.finditer(text):
        number = match.group("number")
        add(
            ReferenceEvidence(
                kind="issue_or_pull_request",
                label=f"#{number}",
                value=number,
                url=f"{base}/issues/{number}" if base else None,
            )
        )

    for match in COMMIT_REFERENCE.finditer(text):
        sha = match.group("sha")
        if commit.sha.startswith(sha):
            continue
        add(
            ReferenceEvidence(
                kind="commit",
                label=sha,
                value=sha,
                url=f"{base}/commit/{sha}" if base else None,
            )
        )
    return tuple(references)


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


def explain_line(repo: str | Path, path: str, line: int) -> LineStory:
    """Explain the last recorded reason for one current line."""

    evidence = blame_line(repo, path, line)
    references = extract_references(evidence.commit)
    date = evidence.commit.authored_at[:10]
    summary = (
        f"Git blame attributes {path}:{line} to {evidence.commit.short_sha} "
        f"({evidence.commit.subject}), authored by {evidence.commit.author} on {date}. "
        f"The commit message contains {len(references)} inspectable intent reference"
        f"{'s' if len(references) != 1 else ''}."
    )
    return LineStory(
        path=path,
        line=line,
        original_line=evidence.original_line,
        content=evidence.content,
        summary=summary,
        commit=evidence.commit,
        references=references,
    )
