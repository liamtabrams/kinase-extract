"""
Milestone 5 (logic) -- loading flagged triples and saving review decisions.

This module holds the *data* side of the human-in-the-loop step, with no UI.
Keeping it separate from app.py means (a) we can unit-test it offline, and
(b) the Streamlit app stays a thin presentation layer -- the offline/interactive
split we planned for deployment.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.schema import ReviewBatch, ValidatedTriple, ValidationReport

DATA = Path(__file__).resolve().parent.parent / "data"
VALIDATIONS = DATA / "validations"
REVIEWS = DATA / "reviews"

# The verdicts a human should adjudicate. "confirmed" triples agree with curated
# knowledge, so we auto-accept them and spend human attention only on the rest.
FLAGGED_STATUSES = {"contradicted", "novel"}


def load_report(pmcid: str) -> ValidationReport:
    path = VALIDATIONS / f"{pmcid}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found -- run `python -m pipeline.validator {pmcid}` first."
        )
    return ValidationReport.model_validate_json(path.read_text(encoding="utf-8"))


def flagged(report: ValidationReport) -> list[ValidatedTriple]:
    """The triples that need human review (contradicted or novel)."""
    return [r for r in report.results if r.status in FLAGGED_STATUSES]


def review_path(pmcid: str) -> Path:
    return REVIEWS / f"{pmcid}.json"


def save_batch(batch: ReviewBatch) -> Path:
    REVIEWS.mkdir(parents=True, exist_ok=True)
    path = review_path(batch.pmcid)
    path.write_text(batch.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_batch(pmcid: str) -> ReviewBatch | None:
    """Return a previously saved review batch, or None if there isn't one yet."""
    path = review_path(pmcid)
    if not path.exists():
        return None
    return ReviewBatch.model_validate_json(path.read_text(encoding="utf-8"))
