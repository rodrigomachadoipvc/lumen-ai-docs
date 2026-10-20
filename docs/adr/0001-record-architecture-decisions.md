# 0001. Record architecture decisions

- Status: accepted
- Date: 2026-10-20

## Context

Lumen makes many technical choices (database, search strategy, providers, deployment target). Months later
it is hard to remember why a choice was made, and reviewers of a portfolio project want to see the
reasoning, not just the result.

## Decision

Record every significant technical decision as a short Architecture Decision Record in `docs/adr/`,
following [Michael Nygard's format](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

- Files are named `NNNN-short-title.md`, numbered in order, starting from `0000-template.md`.
- An ADR is written in the same pull request as the code it describes.
- Accepted ADRs are not rewritten. A changed decision gets a new ADR that supersedes the old one.

## Alternatives considered

- **Only the architecture document**: good for the current picture, but loses the history and the
  rejected options.
- **Decisions in PR descriptions**: hard to find later and tied to GitHub.

## Consequences

Each significant change costs a few extra minutes of writing. In return the reasoning stays next to the
code, and `docs/ARCHITECTURE.md` can stay short and link here.
