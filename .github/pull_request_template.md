<!-- Thanks for contributing to obsify! -->

## What & why

Briefly, what does this change and why?

## Checklist

- [ ] `pytest tests/` passes locally (Linux/Windows, Python 3.11+).
- [ ] New behavior is covered by a test; detection/masking changes update the `eval/` harness.
- [ ] No real data or client names in code, tests, fixtures, or docs — all synthetic.
- [ ] Preserves the invariants: no LLM calls in the library, no runtime network (beyond the
      one-time model download), shape-not-substance (no tool returns raw values to the model).
- [ ] Docs/README updated if behavior or the public API changed.

## Notes for the reviewer

Anything worth calling out (tradeoffs, follow-ups, out-of-scope bits deliberately left).
