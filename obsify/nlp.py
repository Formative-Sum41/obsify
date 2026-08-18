"""Presidio analyzer construction, and enforcement of the no-network principle.

obsify makes no network calls when processing your data. Presidio's baseline
EmailRecognizer validates domains with tldextract, whose default extractor fetches
the public-suffix list over HTTPS on first use; we reconfigure tldextract to use
only its bundled snapshot, so no recognizer can reach the network. This is enforced
here in code, not relied upon by convention.

The ONE exception is first-run setup: if the spaCy NER model is not installed,
`ensure_model()` downloads it once (a public model; no user data is transmitted).
Set OBSIFY_AUTO_DOWNLOAD=0 to forbid this (e.g. air-gapped installs) and install the
model manually instead. After setup, and always for your data, obsify is offline.

The spaCy model is loaded once and shared by both analyzers (baseline and
baseline+custom) to avoid loading en_core_web_lg twice.
"""

from __future__ import annotations

import os
import sys

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider

from obsify.config import Config
from obsify.recognizers import build_custom_recognizers

_SPACY_MODEL = "en_core_web_lg"


def ensure_model(name: str = _SPACY_MODEL) -> None:
    """Ensure the spaCy model is installed, downloading it once if missing.

    Fast no-op when the model is present (no network). This is the only part of
    obsify that may touch the network, and only at first-run setup: it fetches a
    PUBLIC NER model and transmits no user data. Set OBSIFY_AUTO_DOWNLOAD=0 to
    forbid the download — obsify then raises with the manual install command.
    """
    import spacy.util

    if spacy.util.is_package(name):
        return  # already installed — no network

    manual = f"python -m spacy download {name}"
    if os.environ.get("OBSIFY_AUTO_DOWNLOAD", "1").lower() in ("0", "false", "no"):
        raise RuntimeError(
            f"spaCy model {name!r} is not installed and auto-download is disabled "
            f"(OBSIFY_AUTO_DOWNLOAD=0). Install it once with:  {manual}"
        )

    import subprocess

    sys.stderr.write(
        f"[obsify] one-time setup: downloading spaCy model {name!r} (~560 MB). "
        f"This fetches a public model and sends no user data...\n"
    )
    sys.stderr.flush()
    try:
        subprocess.run([sys.executable, "-m", "spacy", "download", name], check=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        raise RuntimeError(
            f"Failed to auto-download spaCy model {name!r} ({exc}). "
            f"Install it manually with:  {manual}"
        ) from exc

    import importlib

    importlib.invalidate_caches()  # make the freshly-installed package importable now


def configure_offline() -> None:
    """Force tldextract to run entirely offline (bundled public-suffix snapshot).

    Idempotent. Guarantees Presidio's EmailRecognizer performs no network I/O.
    """
    import tldextract

    offline = tldextract.TLDExtract(suffix_list_urls=())
    # Presidio calls the module-level `tldextract.extract(...)`; point it at the
    # offline instance so no suffix-list fetch is ever attempted.
    tldextract.extract = offline


def build_nlp_engine():
    ensure_model()  # first-run: download the NER model once if it is missing
    provider = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": _SPACY_MODEL}],
    })
    return provider.create_engine()


def build_analyzer(config: Config) -> AnalyzerEngine:
    """Build the Presidio analyzer: baseline predefined recognizers plus obsify's
    custom Australian recognizers, sharing one loaded spaCy model."""
    configure_offline()
    nlp_engine = build_nlp_engine()
    registry = RecognizerRegistry()
    registry.load_predefined_recognizers(nlp_engine=nlp_engine, languages=["en"])
    for recognizer in build_custom_recognizers(config):
        registry.add_recognizer(recognizer)
    return AnalyzerEngine(
        nlp_engine=nlp_engine, registry=registry, supported_languages=["en"],
    )
