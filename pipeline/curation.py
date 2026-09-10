"""
Milestone 5.5 -- the curated atlas (a local SQLite database).

This is the WRITABLE half of the two-database architecture:
  * OmniPath = read-only public REFERENCE (what's already known).
  * curated.db = our writable CURATION store (what a human has vetted).

We deliberately store only the human-ENDORSED FLAGGED triples (approved or
edited). Confirmed triples already live in OmniPath, so copying them here would
add nothing -- this atlas is the value we add *beyond* the public reference:
novel or corrected findings a person signed off on, with full provenance
(which paper, which reviewer, when).

SQLite is Python's built-in single-file SQL database (`import sqlite3`) -- no
server, no extra dependency. The file is data/curated.db.

CLI:
    python -m pipeline.curation add PMC_SAMPLE   # ingest that paper's review
    python -m pipeline.curation list             # show the atlas
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline.normalize import normalize_site, to_gene_symbol
from pipeline.review import load_batch
from pipeline.schema import ReviewBatch

DATA = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA / "curated.db"

# One table. UNIQUE stops a paper's re-review from duplicating rows; we also
# check explicitly below because SQL treats each NULL site as distinct.
SCHEMA = """
CREATE TABLE IF NOT EXISTS curated_triples (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    kinase           TEXT NOT NULL,
    substrate        TEXT NOT NULL,
    phosphosite      TEXT,
    kinase_symbol    TEXT NOT NULL,
    substrate_symbol TEXT NOT NULL,
    normalized_site  TEXT,
    evidence         TEXT NOT NULL,
    confidence       TEXT,
    machine_status   TEXT,          -- verdict when flagged: novel / contradicted
    decision         TEXT NOT NULL, -- approved / edited
    pmcid            TEXT NOT NULL,
    reviewer         TEXT,
    reviewed_at      TEXT NOT NULL,
    UNIQUE(pmcid, kinase_symbol, substrate_symbol, normalized_site)
);
"""


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row          # rows behave like dicts
    conn.execute(SCHEMA)
    return conn


def add_reviewed(batch: ReviewBatch, db_path: Path = DB_PATH) -> int:
    """Insert the approved/edited triples from a review batch. Returns #added."""
    conn = connect(db_path)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    added = 0
    with conn:  # a transaction: all-or-nothing
        for d in batch.decisions:
            if d.decision not in ("approved", "edited"):
                continue  # rejected triples never enter the atlas
            # For an edit, store the corrected triple; otherwise the original.
            t = d.corrected if (d.decision == "edited" and d.corrected) else d.validated.triple
            ks, ss = to_gene_symbol(t.kinase), to_gene_symbol(t.substrate)
            site = normalize_site(t.phosphosite)

            # Skip if we already have this exact finding from this paper.
            # `IS` (not `=`) so NULL sites compare correctly.
            exists = conn.execute(
                "SELECT 1 FROM curated_triples WHERE pmcid=? AND kinase_symbol=? "
                "AND substrate_symbol=? AND normalized_site IS ?",
                (batch.pmcid, ks, ss, site),
            ).fetchone()
            if exists:
                continue

            conn.execute(
                "INSERT INTO curated_triples (kinase, substrate, phosphosite, "
                "kinase_symbol, substrate_symbol, normalized_site, evidence, "
                "confidence, machine_status, decision, pmcid, reviewer, reviewed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (t.kinase, t.substrate, t.phosphosite, ks, ss, site, t.evidence,
                 t.confidence, d.validated.status, d.decision, batch.pmcid,
                 batch.reviewer, now),
            )
            added += 1
    conn.close()
    return added


def all_triples(db_path: Path = DB_PATH) -> list[dict]:
    conn = connect(db_path)
    rows = conn.execute("SELECT * FROM curated_triples ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count(db_path: Path = DB_PATH) -> int:
    conn = connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM curated_triples").fetchone()[0]
    conn.close()
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The curated-atlas SQLite store.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_add = sub.add_parser("add", help="ingest a paper's saved review decisions")
    p_add.add_argument("pmcid")
    sub.add_parser("list", help="print the atlas contents")
    args = parser.parse_args(argv)

    if args.cmd == "add":
        batch = load_batch(args.pmcid)
        if batch is None:
            print(f"No saved review for {args.pmcid} -- review it in the app first.",
                  file=sys.stderr)
            return 1
        added = add_reviewed(batch)
        print(f"Added {added} new triple(s) from {args.pmcid}. Atlas now holds {count()}.")
    elif args.cmd == "list":
        rows = all_triples()
        print(f"Curated atlas: {len(rows)} triple(s)\n")
        for r in rows:
            site = r["normalized_site"] or "-"
            print(f"  {r['kinase_symbol']}->{r['substrate_symbol']} @ {site}  "
                  f"[{r['decision']}, was {r['machine_status']}]  "
                  f"from {r['pmcid']} by {r['reviewer'] or 'anon'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
