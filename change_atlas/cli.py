"""Command-line interface for local software archaeology."""

import argparse
import json
from pathlib import Path
from typing import Sequence

from .analysis import explain_file, explain_line
from .git_history import GitHistoryError, hotspots
from .graph import build_temporal_graph


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="change-atlas",
        description="Explain why code exists using citations from Git history.",
    )
    parser.add_argument("--repo", default=".", help="Path to the Git repository")
    subparsers = parser.add_subparsers(dest="command", required=True)

    story = subparsers.add_parser("file", help="Reconstruct the story of one file")
    story.add_argument("path", help="Repository-relative file path")
    story.add_argument("--limit", type=int, default=10)
    story.add_argument("--json", action="store_true", dest="as_json")

    why = subparsers.add_parser("why", help="Trace one current line to its last-change evidence")
    why.add_argument("path", help="Repository-relative file path")
    why.add_argument("--line", type=int, required=True, help="Current one-based line number")
    why.add_argument("--json", action="store_true", dest="as_json")

    hot = subparsers.add_parser("hotspots", help="Rank files by change frequency and churn")
    hot.add_argument("--limit", type=int, default=10)
    hot.add_argument("--json", action="store_true", dest="as_json")

    graph = subparsers.add_parser("graph", help="Export a temporal commit-to-file evidence graph")
    graph.add_argument("--limit", type=int, default=200)
    graph.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo = Path(args.repo)
    try:
        if args.command == "file":
            story = explain_file(repo, args.path, limit=args.limit)
            if args.as_json:
                print(json.dumps(story.to_dict(), indent=2))
            else:
                print(story.summary)
                for item in story.evidence:
                    citation = item.url or item.sha
                    print(f"- {item.authored_at[:10]} {item.subject} — {citation}")
        elif args.command == "why":
            story = explain_line(repo, args.path, args.line)
            if args.as_json:
                print(json.dumps(story.to_dict(), indent=2))
            else:
                print(story.summary)
                print(f"> {story.content}")
                print(f"- commit: {story.commit.url or story.commit.sha}")
                for reference in story.references:
                    print(f"- {reference.kind}: {reference.url or reference.label}")
        elif args.command == "hotspots":
            items = hotspots(repo, limit=args.limit)
            if args.as_json:
                print(json.dumps([item.to_dict() for item in items], indent=2))
            else:
                for item in items:
                    print(f"{item.commits:>4} commits  {item.churn:>7} lines  {item.path}")
        else:
            payload = json.dumps(build_temporal_graph(repo, limit=args.limit).to_dict(), indent=2)
            if args.output:
                args.output.write_text(payload + "\n", encoding="utf-8")
                print(args.output)
            else:
                print(payload)
    except (GitHistoryError, ValueError) as error:
        print(f"error: {error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
