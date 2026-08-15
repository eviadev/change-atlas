# ADR 0001 — Evidence before generation

- Status: accepted
- Date: 2026-08-15

## Context

Repository assistants often generate plausible explanations from the current code
without proving why a design was introduced. That is dangerous during migrations,
incident response, and onboarding: a fluent answer can erase the actual decision
history.

## Decision

ChangeAtlas builds answers from immutable evidence first. The initial evidence
source is local Git history: commit SHA, author, timestamp, message, changed path,
and line statistics. Every human-readable summary must retain those citations.

The deterministic evidence layer is independent from future retrieval or language
model layers. A model may rank or summarize evidence later, but it cannot invent a
source and it cannot remove the underlying citations from the response contract.

## Consequences

- The first release is useful without an API key or network access.
- Answers remain auditable and can be regression-tested.
- Poor commit messages remain visible as a data-quality problem.
- Pull requests, issues, tests, and architecture documents can be added as new
  evidence adapters without replacing the core model.
