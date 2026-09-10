"""
Milestone 3a + M7 -- entity normalization (now family-aware).

The problem: papers and databases speak different dialects. Papers say "MEK1",
"ERK2", "Ser383"; OmniPath says "MAP2K1", "MAPK1", residue "S" at offset 383.
Comparing raw strings misses everything, so we translate both sides into one
shared vocabulary (HGNC gene symbols + a canonical site form) before any lookup.
That step is ENTITY NORMALIZATION.

M7 upgrade, driven by the evaluation: real papers constantly use *family* names
("MEK", "ERK", "RAF proteins", "MEK 1/2") that don't map to a single gene. Our
first version marked all of those "novel" -- a normalization failure, not real
novelty. So we now:
  * expand a family name to its set of gene symbols (MEK -> {MAP2K1, MAP2K2}),
    and a triple confirms if ANY member pairing is in the database;
  * parse multi-site strings ("Ser218 and Ser222" -> ["S218", "S222"]).

Honest limitation, unchanged: this is a curated map, not a full HGNC/UniProt
resolver. But it's transparent and testable, and it's now family-aware.

Demo:
    python -m pipeline.normalize
"""

from __future__ import annotations

import re
from typing import Optional

# Specific common name -> HGNC gene symbol. Names already equal to their symbol
# (BRAF, ELK1, KSR1) need no entry; the function falls back to the name itself.
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
    "CK2": "CSNK2A1",
    "PDK1": "PDPK1",
}

# Family / generic name -> the set of gene symbols it can mean. A triple using a
# family name matches if ANY member forms a known pairing.
PROTEIN_FAMILIES: dict[str, list[str]] = {
    "MEK": ["MAP2K1", "MAP2K2"],
    "ERK": ["MAPK3", "MAPK1"],
    "RAF": ["ARAF", "BRAF", "RAF1"],
    "AKT": ["AKT1", "AKT2", "AKT3"],
}

# Amino-acid codes for phosphorylated residues. OmniPath stores the one-letter
# code + a position number.
AMINO_ACIDS: dict[str, str] = {
    "SER": "S", "S": "S",
    "THR": "T", "T": "T",
    "TYR": "Y", "Y": "Y",
    "HIS": "H", "H": "H",
}


def _canonical_family_key(name: str) -> str:
    """Strip generic words so 'RAF kinases', 'RAFs', 'MEK 1/2' all reduce to a
    family key like 'RAF' or 'MEK'."""
    key = name.strip().upper()
    key = re.sub(r"\b(KINASES?|PROTEINS?|FAMILY|ISOFORMS?)\b", "", key)
    key = re.sub(r"\s*1\s*/\s*2\b", "", key)   # "MEK 1/2" / "MEK1/2" -> "MEK"
    key = key.replace("/", " ")
    key = re.sub(r"\s+", " ", key).strip()
    if key.endswith("S") and key[:-1] in PROTEIN_FAMILIES:  # RAFS -> RAF
        key = key[:-1]
    return key


def to_gene_symbol(name: str) -> str:
    """Translate ONE protein name to a single gene symbol (unknown -> uppercased)."""
    key = name.strip().upper()
    return GENE_SYMBOL_ALIASES.get(key, key)


def to_gene_symbols(name: str) -> list[str]:
    """Translate a protein name to the list of gene symbols it can mean.

    A specific name yields one symbol (MEK1 -> [MAP2K1]); a family name yields
    several (MEK -> [MAP2K1, MAP2K2]).
    """
    family_key = _canonical_family_key(name)
    if family_key in PROTEIN_FAMILIES:
        return list(PROTEIN_FAMILIES[family_key])
    return [to_gene_symbol(name)]


def normalize_sites(site: Optional[str]) -> list[str]:
    """Parse every residue+position in a site string into OmniPath's form.

    'Ser383'            -> ['S383']
    'Ser218 and Ser222' -> ['S218', 'S222']
    'Thr202 and Tyr204' -> ['T202', 'Y204']
    """
    if not site:
        return []
    out: list[str] = []
    for word, position in re.findall(r"([A-Za-z]{1,4})[-\s]?(\d+)", site):
        residue = AMINO_ACIDS.get(word.upper())
        if residue and (s := f"{residue}{position}") not in out:
            out.append(s)
    return out


def normalize_site(site: Optional[str]) -> Optional[str]:
    """The first site in a string, or None. (Kept for single-site callers.)"""
    sites = normalize_sites(site)
    return sites[0] if sites else None


def _demo() -> None:
    print("Gene-symbol normalization (name -> symbol(s)):")
    for name in ["MEK1", "MEK", "MEK 1/2", "ERK2", "RAF kinases", "RAFs", "BRAF"]:
        print(f"  {name:14} -> {to_gene_symbols(name)}")
    print("\nSite normalization (written form -> database form):")
    for site in ["Ser383", "Ser218 and Ser222", "Thr202 and Tyr204", "S218", None]:
        print(f"  {str(site):20} -> {normalize_sites(site)}")


if __name__ == "__main__":
    _demo()
