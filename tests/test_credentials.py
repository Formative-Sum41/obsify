"""Tests for the credential/secret recognizer (obsify.recognizers.CredentialRecognizer).

Proves the anchored patterns catch real secret shapes while the keyword-anchored generics
stay precise on prose (no entropy heuristics, so hex/base64 noise is not swept up).

The recognizer is a Presidio PatternRecognizer, so it is tested DIRECTLY (no spaCy model
needed) — fast, and it isolates the regex behaviour from NER.

Every value here is SYNTHETIC and non-functional. Where a vendor publishes a canonical
example we use it (AWS ``AKIAIOSFODNN7EXAMPLE``); otherwise tokens are built from split
literals / filler so no contiguous real-looking secret (or ``BEGIN PRIVATE KEY`` header)
appears in the source — which also keeps GitHub push-protection from blocking the commit.

Run: python tests/test_credentials.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from obsify.recognizers import CredentialRecognizer  # noqa: E402

_REC = CredentialRecognizer()


def _spans(text: str):
    """Return the detected CREDENTIAL spans (as substrings) for `text`."""
    return [text[r.start:r.end] for r in _REC.analyze(text, entities=["CREDENTIAL"])]


def _hit(text: str) -> bool:
    return bool(_REC.analyze(text, entities=["CREDENTIAL"]))


# --- synthetic secrets (built so no contiguous real-looking token is committed) -----
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"                       # AWS's own documented example
GH_TOKEN = "ghp_" + "0" * 36                            # ghp_ + 36 chars (fails GH checksum)
GOOGLE_KEY = "AIza" + "Sy" + "0" * 33                   # AIza + 35 chars
SLACK_TOKEN = "xoxb-" + "0000000000-0000000000-" + "EXAMPLEtoken0"
STRIPE_KEY = "sk_live_" + "0" * 24
JWT = "eyJ" + "hbGciOiJIUzI1" + "." + "eyJzdWI6MX0AAAA" + "." + "c2lnbmF0dXJlAAA"
CONN = "postgresql://appuser:" + "s3cr3tPass0rd" + "@db.internal.example:5432/ledger"
# BEGIN/END markers assembled from split literals so the contiguous header never appears
# in source (push-protection / secret scanners key on that exact string).
_PK_BEGIN = "-----BEGIN " + "RSA PRIVATE KEY" + "-----"
_PK_END = "-----END " + "RSA PRIVATE KEY" + "-----"
PRIVATE_KEY = _PK_BEGIN + "\nMIIBExampleNotARealKeyBody00000000000000\n" + _PK_END


def test_vendor_anchored_tokens_detected():
    for secret in (AWS_KEY, GH_TOKEN, GOOGLE_KEY, SLACK_TOKEN, STRIPE_KEY, JWT):
        assert _hit(f"deploy config: {secret} rotated"), f"missed {secret!r}"


def test_connection_string_with_credentials_detected():
    assert _hit(f"DATABASE_URL={CONN}")


def test_private_key_block_masks_whole_block():
    # The whole BEGIN..END block must be one span, so redaction removes the key BODY,
    # not just the header (a header-only match would leak the key material).
    spans = _spans(f"key material:\n{PRIVATE_KEY}\nend")
    assert spans, "private key block not detected"
    assert any(_PK_BEGIN in s and _PK_END in s and "MIIB" in s for s in spans), \
        "private key match did not cover the whole block (body would leak)"


def test_generic_secret_assignment_detected():
    assert _hit('api_key = "AbC123def456GhI789"')      # quoted value
    assert _hit("aws_secret_access_key=wJalrXUtnFEMIK7MDENGbPxRfiCY3x9")  # value has a digit
    assert _hit("Authorization: Bearer abcDEF123456ghiJKL789mno")


# --- precision: prose and benign identifiers must NOT be flagged --------------------

def test_prose_not_flagged():
    benign = [
        "Please reset your password: click the emailed link to continue.",  # no tokeny value
        "The API key rotates monthly per the security policy.",             # no `=`/`:` value
        "password: hunter2",                                                 # value < 8 chars
        "Contact the token holder about the secret ballot next week.",
    ]
    for t in benign:
        assert not _hit(t), f"false positive on prose: {t!r}"


def test_benign_identifiers_not_flagged():
    # A UUID, a plain long number, and an alnum journal code are not credentials.
    for t in ("550e8400-e29b-41d4-a716-446655440000",
              "Journal 184000123 posted on 2025-06-14",
              "code EP180102 amount 24728837.75"):
        assert not _hit(t), f"false positive on benign token: {t!r}"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
