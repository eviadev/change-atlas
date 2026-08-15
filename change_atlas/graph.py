"""Build a deterministic temporal evidence graph from repository history."""

from pathlib import Path

from .analysis import extract_references
from .git_history import repository_commits
from .models import EvidenceGraph, GraphEdge, GraphNode


def build_temporal_graph(
    repo: str | Path,
    *,
    limit: int = 200,
) -> EvidenceGraph:
    commits = repository_commits(repo, limit=limit)
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    for commit in commits:
        commit_id = f"commit:{commit.sha}"
        nodes[commit_id] = GraphNode(
            id=commit_id,
            kind="commit",
            label=commit.subject,
            data={
                "sha": commit.sha,
                "author": commit.author,
                "authored_at": commit.authored_at,
                "url": commit.url,
            },
        )
        for reference in extract_references(commit):
            reference_key = reference.url or f"{reference.kind}:{reference.value}"
            reference_id = f"reference:{reference_key}"
            nodes.setdefault(
                reference_id,
                GraphNode(
                    id=reference_id,
                    kind="reference",
                    label=reference.label,
                    data={
                        "reference_kind": reference.kind,
                        "value": reference.value,
                        "url": reference.url,
                    },
                ),
            )
            edges.append(
                GraphEdge(
                    source=commit_id,
                    target=reference_id,
                    kind="references",
                    data={},
                )
            )
        for change in commit.changes:
            file_id = f"file:{change.path}"
            nodes.setdefault(
                file_id,
                GraphNode(id=file_id, kind="file", label=change.path, data={"path": change.path}),
            )
            edges.append(
                GraphEdge(
                    source=commit_id,
                    target=file_id,
                    kind="touches",
                    data={
                        "additions": change.additions,
                        "deletions": change.deletions,
                    },
                )
            )

    return EvidenceGraph(
        nodes=tuple(sorted(nodes.values(), key=lambda node: node.id)),
        edges=tuple(sorted(edges, key=lambda edge: (edge.source, edge.target, edge.kind))),
    )
