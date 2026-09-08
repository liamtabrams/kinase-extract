"""
Milestone 3a -- entity normalization.

The problem this solves: the paper and the database speak different dialects.

  * A paper says "MEK1", "ERK2", "Ser383".
  * OmniPath (and most curated databases) say "MAP2K1", "MAPK1", residue "S" at
    offset 383.

If we compared the raw strings, *every* lookup would miss -- "MEK1" != "MAP2K1"
-- and we'd wrongly call real, known relationships "novel". So before we can
validate anything, we have to translate both sides into one shared vocabulary.
That translation step is called ENTITY NORMALIZATION, and it is a real,
load-bearing part of every biomedical (and most non-biomedical) extraction
pipeline. Names are messy; canonical identifiers are the fix.

We do it the pragmatic way: a small curated alias map for the proteins in our
BRAF/MEK/ERK cascade, mapping common names -> HGNC gene symbols (the identifier
OmniPath uses). The honest limitation: this is hand-maintained and only covers
what we put in it. Production systems normalize against a full reference like
HGNC, UniProt, or a tool like mygene -- but the *concept* is identical, and a
curated map is the transparent, testable version for a focused project.

Run a demo:
    python -m pipeline.normalize
"""

from __future__ import annotations

import re
from typing import Optional

# Common protein name (as papers write it) -> HGNC gene symbol (as OmniPath
# stores it). Keys are compared uppercased. Proteins whose common name already
# IS their gene symbol (BRAF, ELK1, KSR1) don't need an entry -- the function
# below falls back to the name itself.
GENE_SYMBOL_ALIASES: dict[str, str] = {
    "MEK1": "MAP2K1",
    "MEK2": "MAP2K2",
    "ERK1": "MAPK3",
    "ERK2": "MAPK1",
    "RSK2": "RPS6KA3",
    "P90RSK": "RPS6KA1",
    "P38": "MAPK14",
    "JNK1": "MAPK8",
    "AKT": "AKT1",
    "PKB": "AKT1",
}

# Three-letter and one-letter amino-acid codes for the residues that get
# phosphorylated. OmniPath stores just the one-letter code + a position number.
AMINO_ACIDS: dict[str, str] = {
    "SER": "S", "S": "S",
    "THR": "T", "T": "T",
    "TYR": "Y", "Y": "Y",
    "HIS": "H", "H": "H",
}


def to_gene_symbol(name: str) -> str:
    """Translate a protein name to its HGNC gene symbol.

    Unknown names fall through unchanged (just uppercased), so a name that is
    already a gene symbol (e.g. 'BRAF') passes straight through.
    """
    key = name.strip().upper()
    return GENE_SYMBOL_ALIASES.get(key, key)


def normalize_site(site: Optional[str]) -> Optional[str]:
    """Turn a written site like 'Ser383' into OmniPath's form 'S383'.

    Returns None when there is no site (or we can't parse one), which keeps
    'no site stated' distinct from 'a specific site'.
    """
    if not site:
        return None
    # Split the letters (residue) from the digits (position), e.g. Ser | 383.
    match = re.match(r"\s*([A-Za-z]+)\s*[-]?\s*(\d+)\s*$", site)
    if not match:
        return None
    residue_word, position = match.group(1), match.group(2)
    residue = AMINO_ACIDS.get(residue_word.upper())
    if residue is None:
        return None
    return f"{residue}{position}"


def _demo() -> None:
    print("Gene-symbol normalization (paper name -> database symbol):")
    for name in ["MEK1", "ERK2", "BRAF", "RSK2", "KSR1", "SomeNovelProtein"]:
        print(f"  {name:18} -> {to_gene_symbol(name)}")
    print("\nSite normalization (written form -> database form):")
    for site in ["Ser383", "Thr202", "Tyr204", "S218", None, "phospho-Ser"]:
        print(f"  {str(site):18} -> {normalize_site(site)}")


if __name__ == "__main__":
    _demo()
