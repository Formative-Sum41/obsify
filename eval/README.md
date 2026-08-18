# obsify evaluation harness

Measurable confidence, not vibes. This directory is **dev tooling — not shipped in the
wheel.** It generates a labelled synthetic corpus, scores obsify's *shipping* detector
against it, and cross-checks recall against an independent third-party benchmark.

```bash
pip install -e ".[eval]"           # faker + reportlab

python eval/generate.py --out ./eval_corpus            # labelled corpus + answer_key.jsonl
python eval/score.py    --corpus ./eval_corpus --out eval_report.md
python eval/bench_external.py --sample 300             # independent cross-check (fetches from GitHub)
```

The scored test (`tests/test_evaluation.py`) runs in the normal suite and gates regressions.

## Design principles

- **The answer key encodes *designed* behaviour, not "value present."** obsify is
  context-gated: a bare ABN with no nearby label word is *supposed* to be suppressed. Each
  planted item is tagged `detect` / `suppress` / `gap`, so a deliberate suppression scores as
  correct, not as a recall miss.
- **Difficulty is where it's informative.** Clean in-context IDs are ~100% by construction
  (the minter uses the same checksum the validator does) and prove nothing. The scored
  difficulty lives in adversarial cases (unicode names, in-cell newlines, missing context) and
  in the **FP-torture** `Journals` sheet — 220 rows of bare 8–9 digit IDs, codes and amounts
  that plant *no* PII, so any detection there is an emergent false positive: the honest
  precision signal.
- **Score the config that ships.** The scorer runs `_DETECT_CFG` (the exact suppressors
  `mcp_server` uses), not a friendlier one.
- **Synthetic only.** The scorer reads detected *values* to match them — safe solely because
  the corpus is fabricated. Never point it at real data.
- **Independent cross-check.** `bench_external.py` scores recall against Microsoft
  `presidio-research`'s synthetic set — different team, different taxonomy — to avoid grading
  our own homework. It's in-family (obsify *is* Presidio) and only covers generic types, so
  it's a weak-but-real signal, reported honestly.

## Representative results

Scored harness (`eval/score.py`, 33 planted items across PDF/Excel/DOCX). Numbers below are
a captured snapshot; the NER-dependent ones vary slightly with the spaCy model version, so the
tests assert them as thresholds, not equalities:

| Metric | Result |
|---|---|
| Recall (expected=detect) | **100%** (29/29) |
| Precision (TP / TP+FP) | ~73% — residual FPs are `ORGANIZATION`/`PERSON` on headings (documented NER-noise tradeoff) |
| **FP-torture** (numeric ledger + grouped-number guard, no PII) | **0** — the numeric-noise filter holds |
| Suppression (bare context-gated IDs) | 3/3 correctly dropped |
| Remaining coverage gap (SWIFT/BIC) | 0/1 detected — one documented gap, confirmed |

External cross-check (`presidio-research`, 300 records): overall recall **87%** — EMAIL 100%,
IBAN 100%, PERSON 94%, ORGANIZATION 74%, CREDIT_CARD 70%, PHONE_NUMBER **53%** (up from 13%
before the phone fix).

## Findings the harness surfaced (and how they were CLOSED)

1. **Credit cards were silently suppressed → fixed.** The scored harness caught that
   letterless suppression (which kills bare-number ledger noise) also dropped Luhn-valid
   cards. A card is checksum-validated PII, not coincidental noise, so it's now exempt from
   letterless suppression (like BSB-adjacent accounts). Recall 95% → 100%.
2. **Phones were suppressed in detect-mode → fixed.** The external benchmark found 13% phone
   recall. Rather than blanket-exempt (which would reintroduce ledger FPs), phones now survive
   suppression only with a phone context word nearby OR a phone shape (leading `+`/`(area)`/`0x`/
   `13`/`1800`, or separator-grouped digits) — and never if a decimal point marks an amount.
   Scored-harness phone recall 100%; external 13% → 53%; **FP-torture stayed 0**, verified with
   a grouped-number guard column.
3. **Missing recognizers → added.** Medicare (weighted-modulus-10 checksum), IP address
   (Presidio built-in, enabled + exempted from letterless suppression), and a context-gated
   date-of-birth recognizer. All now 100% in the scored harness; the FP cost is contained by
   require-context (Medicare/DOB) and format validation (IP).

## Coverage note

obsify detects: PERSON, ORGANIZATION, EMAIL_ADDRESS, PHONE_NUMBER, LOCATION, CREDIT_CARD,
IBAN_CODE, IP_ADDRESS, AU_ABN, AU_ACN, AU_TFN, AU_BANK_ACCOUNT, AU_ADDRESS, MEDICARE,
DATE_OF_BIRTH, AU_PASSPORT, AU_DRIVER_LICENCE (the last four context-gated), ENGAGEMENT_CODE.
Still out of scope (documented gaps): SWIFT/BIC, standalone BSB, and non-DOB DATE_TIME. Phone
recall in detect-mode is strong for AU formats and partial for arbitrary international ones —
knowing the edges is part of the confidence.
