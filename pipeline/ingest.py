"""
Milestone 1 -- Paper ingestion.

Goal: turn a PubMed Central (PMC) open-access paper into clean, sentence-split
text that the Reader Agent (M2) can mine for kinase-substrate-phosphosite
triples.

Three design choices worth understanding:

  1. SOURCE. We fetch from Europe PMC's REST API. It mirrors the PMC
     open-access subset, needs no API key, and returns full-text JATS XML.
     (NCBI's own E-utilities work too; Europe PMC is simpler and friendlier.)

  2. CACHE-FIRST. Every fetched paper is saved to data/raw/ and we only touch
     the network on a cache miss. This makes runs reproducible, is polite to
     the API, and -- importantly -- lets the pipeline run in environments that
     cannot reach PMC at all (like a locked-down CI sandbox). The included
     sample paper is exactly such a cached file.

  3. SENTENCES. We split the body into sentences and keep them, because each
     extracted triple later carries the *evidence sentence* a human reviewer
     reads to judge the claim. Ingestion is where that evidence is preserved.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

# Europe PMC full-text endpoint. {pmcid} looks like "PMC6582307".
EUROPE_PMC_XML = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"

# Project data folders. raw/ = exactly what we fetched (XML); processed/ = the
# cleaned, sentence-split JSON that later milestones consume.
DATA = Path(__file__).resolve().parent.parent / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"


def fetch_fulltext_xml(pmcid: str, timeout: int = 30) -> str:
    """Return the JATS full-text XML for a PMC id, using a disk cache.

    Cache-first: if data/raw/<pmcid>.xml already exists, we return it and never
    touch the network. Otherwise we download it, save it, and return it. This
    is why the bundled sample paper works with no internet access.
    """
    RAW.mkdir(parents=True, exist_ok=True)
    cache = RAW / f"{pmcid}.xml"
    if cache.exists():
        return cache.read_text(encoding="utf-8")

    url = EUROPE_PMC_XML.format(pmcid=pmcid)
    resp = requests.get(
        url, timeout=timeout, headers={"User-Agent": "kinase-extract/0.1"}
    )
    resp.raise_for_status()
    xml = resp.text
    cache.write_text(xml, encoding="utf-8")
    return xml


def xml_to_text(xml: str) -> dict:
    """Pull the title and body paragraphs out of JATS XML.

    JATS is the standard XML schema PMC uses for articles. We keep parsing
    deliberately minimal: take <article-title> and the text of every <p> inside
    <body>. `itertext()` flattens nested inline tags (italic, xref, ...) into
    plain text, so "BRAF<italic>V600E</italic>" becomes "BRAFV600E" rather than
    losing the content. Production parsers also handle sections, tables, and
    figure captions; we don't need those to find phosphorylation sentences.
    """
    root = ET.fromstring(xml)

    def text_of(el) -> str:
        return re.sub(r"\s+", " ", "".join(el.itertext())).strip()

    title_el = root.find(".//article-title")
    title = text_of(title_el) if title_el is not None else ""

    body = root.find(".//body")
    paragraphs = []
    if body is not None:
        for p in body.iter("p"):
            t = text_of(p)
            if t:
                paragraphs.append(t)
    return {"title": title, "paragraphs": paragraphs}


def split_sentences(text: str) -> list[str]:
    """Split a paragraph into sentences.

    Pragmatic rule: break after a '.', '!' or '?' that is followed by
    whitespace and an uppercase letter or digit. We drop very short fragments
    (stray headings, list markers). This is "good enough" for a demo -- but
    note the honest limitation: naive splitters mishandle biomedical text like
    "S. cerevisiae" or "approx. 5 min". Production pipelines use spaCy /
    scispaCy sentence segmentation, which is trained to handle these cases.
    """
    rough = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    return [s.strip() for s in rough if len(s.strip()) > 20]


def ingest_paper(pmcid: str) -> dict:
    """Fetch (or load from cache) a paper, clean it, and write processed JSON."""
    xml = fetch_fulltext_xml(pmcid)
    doc = xml_to_text(xml)

    sentences: list[str] = []
    for paragraph in doc["paragraphs"]:
        sentences.extend(split_sentences(paragraph))

    result = {
        "pmcid": pmcid,
        "title": doc["title"],
        "n_paragraphs": len(doc["paragraphs"]),
        "sentences": sentences,
    }

    PROCESSED.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED / f"{pmcid}.json"
    out_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest a PMC paper into clean sentences.")
    parser.add_argument(
        "pmcid",
        nargs="?",
        default="PMC_SAMPLE",
        help="PMC id, e.g. PMC6582307. Defaults to the bundled offline sample.",
    )
    args = parser.parse_args(argv)

    result = ingest_paper(args.pmcid)

    print(f"Ingested {result['pmcid']}: {result['title'][:80]!r}")
    print(f"  paragraphs: {result['n_paragraphs']}")
    print(f"  sentences : {len(result['sentences'])}")
    print(f"  saved to  : data/processed/{result['pmcid']}.json")
    print()
    print("First few sentences:")
    for s in result["sentences"][:5]:
        print(f"  - {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
