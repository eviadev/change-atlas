"""Typed domain objects returned by ChangeAtlas."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FileChange:
    path: str
    additions: int | None
    deletions: int | None


@dataclass(frozen=True)
class CommitEvidence:
    sha: str
    author: str
    authored_at: str
    subject: str
    body: str
    changes: tuple[FileChange, ...]
    url: str | None = None

    @property
    def short_sha(self) -> str:
        return self.sha[:8]


@dataclass(frozen=True)
class FileStory:
    path: str
    summary: str
    evidence: tuple[CommitEvidence, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Hotspot:
    path: str
    commits: int
    churn: int

    def to_dict(self) -> dict:
        return asdict(self)
