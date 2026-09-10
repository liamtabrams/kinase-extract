"""
Milestone 3b -- the Validator Agent.

For each extracted triple, we ask a curated database (OmniPath) one question:
"do you already know this kinase -> substrate relationship?" and assign a verdict:

  * confirmed   -- OmniPath records this kinase acting on this substrate
                   (same direction). If the paper also named a site and OmniPath
                   has that exact site, we note site_in_db = True.
  * contradicted-- OmniPath records the REVERSE direction (substrate acting on
                   kinase) but not the stated direction. The paper's arrow
                   points the wrong way versus curated knowledge.
  * novel       -- OmniPath has neither direction. Could be a genuine new
                   finding worth a human's attention -- or an extraction error.
                   That ambiguity is exactly why M5 sends these to a reviewer.

An honest caveat you should be able to state: curated databases list
*positives* (known relationships), not negatives. So we can't truly prove a
claim "false" -- "contradicted" here is a heuristic (the direction is reversed
vs. what's curated), and "novel" means "absent from this database", not
"newly true". Naming that limitation is part of understanding the design.

Two reference sources behind one interface (same idea as the Reader's backends):
  * omnipath -- the live curated database (downloads on first use).
  * fixture  -- a small local CSV mirroring OmniPath's columns, so the whole
                thing runs offline. Great for development and for this sandbox.

Run it:
    python -m pipeline.validator --reference fixture   # offline
    python -m pipeline.validator --reference omnipath  # live curated data
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from itertools import product

from pipeline.normalize import normalize_sites, to_gene_symbols
from pipeline.schema import (
    Extraction,
    ValidatedTriple,
    ValidationReport,
    ValidationStatus,
)

DATA = Path(__file__).resolve().parent.parent / "data"
EXTRACTIONS = DATA / "extractions"
VALIDATIONS = DATA / "validations"
REFERENCE = DATA / "reference"

# OmniPath's enzyme-substrate table uses these column names; our fixture CSV
# mirrors them so the same indexing code works for both sources.
COL_ENZYME = "enzyme_genesymbol"
COL_SUBSTRATE = "substrate_genesymbol"
COL_RES_TYPE = "residue_type"     # 'S', 'T', 'Y', ...
COL_RES_OFFSET = "residue_offset"  # position number
COL_MOD = "modification"           # we keep only 'phosphorylation'


def load_reference(source: str) -> pd.DataFrame:
    """Return the enzyme-substrate table as a DataFrame, from live OmniPath or the fixture."""
    if source == "omnipath":
        try:
            from omnipath.requests import Enzsub
        except ImportError as exc:
            raise SystemExit(
                "omnipath is not installed. `pip install omnipath`, or use "
                "--reference fixture to run offline."
            ) from exc
        # Enzsub = enzyme-substrate (PTM) relationships. Downloads on first call,
        # then caches locally. genesymbols=True is REQUIRED: without it OmniPath
        # returns only UniProt accession columns (enzyme/substrate), not the
        # *_genesymbol columns we normalize to.
        return Enzsub.get(genesymbols=True)
    if source == "fixture":
        path = REFERENCE / "omnipath_sample.csv"
        return pd.read_csv(path)
    raise ValueError(f"unknown reference source: {source!r} (use omnipath or fixture)")


def build_index(df: pd.DataFrame) -> dict[tuple[str, str], set[str]]:
    """Index the table as (kinase_symbol, substrate_symbol) -> set of known sites.

    We keep only phosphorylation rows and record each site as 'S218'-style
    strings, so lookups are O(1) instead of scanning the whole table per triple.
    """
    required = (COL_ENZYME, COL_SUBSTRATE, COL_RES_TYPE, COL_RES_OFFSET, COL_MOD)
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(
            f"Reference table is missing expected columns {missing}.\n"
            f"Columns present: {list(df.columns)}\n"
            "For live OmniPath, make sure gene symbols are requested "
            "(Enzsub.get(genesymbols=True))."
        )

    phospho = df[df[COL_MOD] == "phosphorylation"]
    index: dict[tuple[str, str], set[str]] = {}
    # Iterate column-by-column (robust: avoids itertuples' attribute-name quirks).
    for enzyme, substrate, res_type, res_offset in zip(
        phospho[COL_ENZYME], phospho[COL_SUBSTRATE],
        phospho[COL_RES_TYPE], phospho[COL_RES_OFFSET],
    ):
        sites = index.setdefault((enzyme, substrate), set())
        if pd.notna(res_type) and pd.notna(res_offset):
            sites.add(f"{res_type}{int(res_offset)}")
    return index


def validate_triple(triple, index: dict[tuple[str, str], set[str]]) -> ValidatedTriple:
    """Assign a verdict to one triple by looking it up in the index.

    Family-aware: a name like "MEK" expands to {MAP2K1, MAP2K2}, and we try every
    kinase x substrate pairing. The first forward pairing found in OmniPath wins
    (confirmed); failing that, a reverse pairing means contradicted; else novel.
    """
    kinases = to_gene_symbols(triple.kinase)
    substrates = to_gene_symbols(triple.substrate)
    sites = normalize_sites(triple.phosphosite)

    forward = next(((k, s) for k, s in product(kinases, substrates) if (k, s) in index), None)
    reverse = next(((k, s) for k, s in product(kinases, substrates) if (s, k) in index), None)

    status: ValidationStatus
    site_in_db = None
    site_str = "/".join(sites) if sites else None

    if forward is not None:
        status = "confirmed"
        k_used, s_used = forward
        if sites:
            db_sites = index[forward]
            # STRICT site match: EVERY extracted site must be recorded, not just
            # one. Stricter and more honest -- a triple that names Thr202/Tyr204
            # only counts as correct if OmniPath records both. (Lenient `any`
            # would over-credit partial matches.)
            site_in_db = all(s in db_sites for s in sites)
            missing = [s for s in sites if s not in db_sites]
            site_note = (
                f" All site(s) {site_str} match the record."
                if site_in_db
                else f" But site(s) {'/'.join(missing)} are not recorded."
            )
        else:
            site_note = ""
        explanation = f"OmniPath records {k_used} -> {s_used} phosphorylation.{site_note}"
    elif reverse is not None:
        status = "contradicted"
        k_used, s_used = "/".join(kinases), "/".join(substrates)
        rk, rs = reverse
        explanation = (
            f"OmniPath records the reverse direction ({rs} -> {rk}), "
            f"not {k_used} -> {s_used} as stated."
        )
    else:
        status = "novel"
        k_used, s_used = "/".join(kinases), "/".join(substrates)
        explanation = (
            f"OmniPath has no record of {k_used} <-> {s_used} phosphorylation "
            "in either direction."
        )

    return ValidatedTriple(
        triple=triple,
        kinase_symbol=k_used,
        substrate_symbol=s_used,
        normalized_site=site_str,
        status=status,
        site_in_db=site_in_db,
        explanation=explanation,
    )


def validate_paper(pmcid: str, source: str) -> ValidationReport:
    """Load a paper's extracted triples, validate each, and save the report."""
    extraction_path = EXTRACTIONS / f"{pmcid}.json"
    if not extraction_path.exists():
        raise FileNotFoundError(
            f"{extraction_path} not found -- run `python -m pipeline.reader {pmcid}` first."
        )
    extraction = Extraction.model_validate_json(extraction_path.read_text(encoding="utf-8"))

    df = load_reference(source)
    index = build_index(df)
    results = [validate_triple(t, index) for t in extraction.triples]

    report = ValidationReport(pmcid=pmcid, reference=source, results=results)
    VALIDATIONS.mkdir(parents=True, exist_ok=True)
    out_path = VALIDATIONS / f"{pmcid}.json"
    out_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate extracted triples against OmniPath.")
    parser.add_argument("pmcid", nargs="?", default="PMC_SAMPLE")
    parser.add_argument("--reference", choices=["omnipath", "fixture"], default="omnipath")
    args = parser.parse_args(argv)

    report = validate_paper(args.pmcid, args.reference)

    counts: dict[str, int] = {}
    for r in report.results:
        counts[r.status] = counts.get(r.status, 0) + 1

    print(f"Validated {len(report.results)} triples from {args.pmcid} "
          f"(reference={args.reference}):")
    print(f"  {counts.get('confirmed', 0)} confirmed, "
          f"{counts.get('contradicted', 0)} contradicted, "
          f"{counts.get('novel', 0)} novel\n")
    for r in report.results:
        t = r.triple
        flag = {"confirmed": "OK ", "contradicted": "XX ", "novel": "?? "}[r.status]
        print(f"  {flag}[{r.status:<12}] {t.kinase}->{t.substrate} "
              f"({r.kinase_symbol}->{r.substrate_symbol})  [extractor: {t.confidence}]")
        print(f"       verdict : {r.explanation}")
        print(f"       evidence: {t.evidence}")
    print(f"\nSaved to data/validations/{args.pmcid}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
