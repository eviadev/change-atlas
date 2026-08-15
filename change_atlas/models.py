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
class ReferenceEvidence:
    kind: str
    label: str
    value: str
    url: str | None = None


@dataclass(frozen=True)
class BlamedLine:
    path: str
    line: int
    original_line: int
    content: str
    commit: CommitEvidence


@dataclass(frozen=True)
class LineStory:
    path: str
    line: int
    original_line: int
    content: str
    summary: str
    commit: CommitEvidence
    references: tuple[ReferenceEvidence, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Hotspot:
    path: str
    commits: int
    churn: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GraphNode:
    id: str
    kind: str
    label: str
    data: dict


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    kind: str
    data: dict


@dataclass(frozen=True)
class EvidenceGraph:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    def to_dict(self) -> dict:
        return asdict(self)
