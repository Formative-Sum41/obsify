---
name: Feature request
about: Suggest an addition or change
title: ''
labels: enhancement
assignees: ''
---

**The problem**
What are you trying to do that obsify doesn't support today?

**Proposed solution**
What you'd like to see.

**Scope check**
obsify is deliberately narrow (local, privacy-preserving PII handling over MCP) and holds a
few [non-negotiable invariants](../../CONTRIBUTING.md) (no LLM calls in the library, no runtime
network, no real data, shape-not-substance). How does this fit within that? If it's a new
detector, note whether it can be checksum- or context-validated to stay precise.

**Alternatives considered**
