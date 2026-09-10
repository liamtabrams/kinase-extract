"""
Milestone 6 -- evaluation.

The point of this milestone is not the arithmetic (it's simple) -- it's learning
to say precisely WHAT a number measures and what it does NOT. Good eval design is
mostly honesty about the limits of your labels.

We compute four things from the artifacts already on disk:

  1. DB agreement rate  -- of all extracted triples, the fraction OmniPath already
     records (status == confirmed). This is coverage against curated knowledge.
     Caveat: databases hold POSITIVES only, so a non-confirmed triple isn't
     necessarily wrong -- it may just be uncurated. So this is "agreement", not
     "accuracy".

  2. Site accuracy       -- of confirmed triples that named a phosphosite, the
     fraction whose exact site OmniPath also records. A stricter, higher-value
     check than the pair alone.

  3. Human review outcomes -- on the FLAGGED triples the reviewer judged:
     approved / rejected / edited counts.

  4. Validator flag precision -- of the flagged triples the human decided, the
     fraction the human did NOT simply approve (rejected or edited). This asks:
     "when the validator raised a flag, was it justified?" An approved flag was a
     false alarm (the claim was fine; OmniPath was just incomplete).

What we CANNOT compute here, and why -- an eval-design point worth stating:
  * RECALL (did we find every true triple in the paper?) needs an exhaustively
    labeled gold set. We only labeled the flagged subset, so recall is unknown.
  * Extractor precision over ALL triples needs a human to judge the *confirmed*
    ones too; we auto-accepted those, so our human labels only cover the flagged
    subset. Your metric is only ever as broad as your labels.

Run it:
    python -m pipeline.evaluate                 # PMC_SAMPLE
    python -m pipeline.evaluate PMC6582307
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from pipeline.review import FLAGGED_STATUSES, load_batch, load_report

DATA = Path(__file__).resolve().parent.parent / "data"
EVAL = DATA / "eval"


def _pct(numerator: int, denominator: int) -> float | None:
    """Percentage, or None when there's nothing to divide (keeps 0/0 honest)."""
    if denominator == 0:
        return None
    return round(100 * numerator / denominator, 1)


def compute_metrics(pmcid: str) -> dict:
    report = load_report(pmcid)          # the Validator's output (all triples, labeled)
    batch = load_batch(pmcid)            # the human's decisions (may be None)

    results = report.results
    total = len(results)
    by_status = Counter(r.status for r in results)

    # 1. DB agreement.
    confirmed = by_status.get("confirmed", 0)

    # 2. Site accuracy (only over confirmed triples that named a site).
    sited = [r for r in results if r.status == "confirmed" and r.normalized_site]
    site_matches = sum(1 for r in sited if r.site_in_db)

    metrics: dict = {
        "pmcid": pmcid,
        "reference": report.reference,
        "total_extracted": total,
        "status_counts": dict(by_status),
        "db_agreement_rate_pct": _pct(confirmed, total),
        "site_accuracy_pct": _pct(site_matches, len(sited)),
        "site_checked": len(sited),
    }

    # 3 & 4. Human-label metrics -- only if a review batch exists.
    if batch is not None:
        # Map each decision to the triple it was about, keyed by evidence text.
        decision_by_evidence = {
            d.validated.triple.evidence: d.decision for d in batch.decisions
        }
        flagged = [r for r in results if r.status in FLAGGED_STATUSES]
        decided = [r for r in flagged if r.triple.evidence in decision_by_evidence]

        outcomes = Counter(decision_by_evidence[r.triple.evidence] for r in decided)
        approved = outcomes.get("approved", 0)
        rejected = outcomes.get("rejected", 0)
        edited = outcomes.get("edited", 0)

        # Flag precision: flags the human agreed were problems (rejected or edited).
        flag_hits = rejected + edited
        # Pipeline yield: everything that ends up in the curated set.
        accepted = confirmed + approved + edited

        metrics["review"] = {
            "flagged": len(flagged),
            "reviewed": len(decided),
            "approved": approved,
            "rejected": rejected,
            "edited": edited,
            "flag_precision_pct": _pct(flag_hits, len(decided)),
            "pipeline_yield_pct": _pct(accepted, total),
        }
    else:
        metrics["review"] = None

    return metrics


def render(metrics: dict) -> str:
    lines = []
    lines.append(f"Evaluation for {metrics['pmcid']} (reference={metrics['reference']})")
    lines.append("=" * 52)
    lines.append(f"Triples extracted        : {metrics['total_extracted']}")
    sc = metrics["status_counts"]
    lines.append(f"  confirmed / contradicted / novel : "
                 f"{sc.get('confirmed', 0)} / {sc.get('contradicted', 0)} / {sc.get('novel', 0)}")
    lines.append("")
    lines.append(f"DB agreement rate        : {metrics['db_agreement_rate_pct']}%  "
                 f"(fraction OmniPath already records)")
    sa = metrics["site_accuracy_pct"]
    lines.append(f"Site accuracy            : "
                 + (f"{sa}%  (of {metrics['site_checked']} confirmed triples with a site)"
                    if sa is not None else "n/a  (no confirmed triples named a site)"))

    r = metrics["review"]
    lines.append("")
    if r is None:
        lines.append("Human review             : none saved yet -- run the Streamlit app "
                     "and Save decisions to unlock the gold-label metrics.")
    else:
        lines.append(f"Human review (flagged)   : {r['reviewed']}/{r['flagged']} reviewed  "
                     f"-> {r['approved']} approved, {r['rejected']} rejected, {r['edited']} edited")
        fp = r["flag_precision_pct"]
        lines.append(f"Validator flag precision : "
                     + (f"{fp}%  (flags the human agreed were problems)" if fp is not None
                        else "n/a  (no flagged triples were reviewed)"))
        lines.append(f"Pipeline yield           : {r['pipeline_yield_pct']}%  "
                     f"(extracted triples that reached the curated set)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the pipeline for one paper.")
    parser.add_argument("pmcid", nargs="?", default="PMC_SAMPLE")
    args = parser.parse_args(argv)

    metrics = compute_metrics(args.pmcid)
    print(render(metrics))

    EVAL.mkdir(parents=True, exist_ok=True)
    out_path = EVAL / f"{args.pmcid}.json"
    out_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"\nSaved metrics to data/eval/{args.pmcid}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
