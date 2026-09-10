# kinase-extract

A scaled-down, learning-focused **multi-agent LLM pipeline** that reads
biomedical papers, extracts **kinase → substrate → phosphosite** relationships,
cross-validates them against a curated database, and surfaces uncertain ones
for human review.

Inspired by the PhosphoAtlas++ project (UCSF Radiation Oncology). Built to
demonstrate the core concepts of applied AI engineering — structured output
extraction, tool-grounded validation, human-in-the-loop review, and evaluation
design — on a focused example: **BRAF / MEK / ERK signaling in colorectal
cancer**.

## Roadmap

| # | Milestone | Concept |
|---|-----------|---------|
| **M1** | Paper ingestion (PMC → clean sentences) | Real-world text ingestion, caching |
| M2 | Reader Agent (LLM → typed triples) | Structured output extraction |
| M3 | Validator Agent (triples vs OmniPath) | Tool grounding + entity normalization |
| M4 | Orchestration (Reader → Validator → batch) | Multi-agent handoff |
| M5 | Human-in-the-loop review (Streamlit) | HITL design |
| M6 | Evaluation (precision/recall, coverage) | Eval design |
| +1 | Packaging & deployment (Docker → HF Spaces) | Reproducibility & shipping |

## Setup

```bash
pip install -r requirements.txt
```

## M1 — Paper ingestion

Turns a PubMed Central open-access paper into clean, sentence-split JSON that
later milestones consume.

```bash
# Run on the bundled offline sample (no internet needed):
python -m pipeline.ingest

# Run on a real paper (needs internet access to Europe PMC):
python -m pipeline.ingest PMC6582307
```

Output lands in `data/processed/<pmcid>.json` as:

```json
{
  "pmcid": "PMC_SAMPLE",
  "title": "...",
  "n_paragraphs": 3,
  "sentences": ["The RAF-MEK-ERK cascade ...", "..."]
}
```

### Design notes

- **Source:** Europe PMC REST API (`/fullTextXML`) — mirrors the PMC
  open-access subset, no API key required.
- **Cache-first:** fetched papers are cached to `data/raw/<pmcid>.xml`; the
  network is only used on a cache miss. This makes runs reproducible and lets
  the pipeline work offline. The bundled `PMC_SAMPLE.xml` is a synthetic demo
  article (hand-written JATS) so everything runs without internet — swap in a
  real PMCID when you run locally.
- **Sentences are kept** because each extracted triple later carries the
  *evidence sentence* a human reviewer reads to judge the claim.

## Run the whole batch

`run_pipeline.sh` chains ingest → reader → validator for a list of papers, then
runs the aggregate evaluation. The interactive review UI is separate
(`streamlit run app.py`).

```bash
./run_pipeline.sh                          # default papers, Claude + live OmniPath
./run_pipeline.sh PMC6582307 PMC7694028    # your own PMCIDs
BACKEND=mock REFERENCE=fixture ./run_pipeline.sh PMC_SAMPLE   # offline, no cost
```
