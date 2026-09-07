"""
Milestone 2 (part 2) -- the Reader Agent.

Takes the clean sentences from M1 and asks a language model to extract
kinase-substrate-phosphosite triples that match our Pydantic schema (M2 part 1).

Design: ONE INTERFACE, THREE BACKENDS.
  We define an abstract `ReaderBackend` with a single method, `extract(text)`,
  and three concrete implementations:

    * ClaudeBackend -- the hosted Anthropic API. Uses `messages.parse`, which
      enforces our schema server-side and returns a *validated* object.
    * OllamaBackend -- a free, local open-weights model (e.g. qwen2.5:7b). We
      send the schema as the `format`, get back JSON text, and validate it
      OURSELVES. (Contrast worth noting: with Claude the SDK validates for you;
      with a local model you own that step -- the model can still hand you junk.)
    * MockBackend  -- returns a canned Extraction from a file. Zero cost, no
      network. Use it to run the whole pipeline offline before spending money.

  This "swap the backend, keep the interface" pattern is called a provider
  abstraction. It's why the rest of the codebase never has to care which model
  produced the triples.

Run it:
    python -m pipeline.reader                      # default: claude backend
    python -m pipeline.reader --backend mock       # offline, free demo
    python -m pipeline.reader --backend ollama     # local open-weights model
"""

from __future__ import annotations

import argparse
import json
import sys
from abc import ABC, abstractmethod
from pathlib import Path

from pipeline.schema import Extraction

DATA = Path(__file__).resolve().parent.parent / "data"
PROCESSED = DATA / "processed"
EXTRACTIONS = DATA / "extractions"
MOCK = DATA / "mock"

# Default hosted model. Sonnet is the cost/quality sweet spot for extraction;
# change this one line to "claude-opus-5" for maximum quality, or
# "claude-haiku-4-5" for the cheapest hosted option.
DEFAULT_CLAUDE_MODEL = "claude-sonnet-5"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"

# The system prompt is the *content* instruction. (The *shape* is enforced
# separately by the schema.) Keep the two concerns separate in your head:
# schema = structure, prompt = what to look for and how carefully.
SYSTEM_PROMPT = """\
You are a careful biomedical relation extractor. From the text, extract every \
explicitly stated kinase-substrate phosphorylation relationship: one protein \
(the kinase) phosphorylating another protein (the substrate), optionally at a \
named residue and position.

Rules:
- Only extract relationships the text actually asserts. Do NOT use outside \
knowledge or infer relationships that are not stated in the text.
- Copy protein names exactly as they appear; do not rename or normalize them.
- Quote the exact source sentence as the evidence.
- If the text names no specific site, leave phosphosite null.
- Set confidence by how directly the text states that specific relationship.
"""


class ReaderBackend(ABC):
    """The one interface every backend implements."""

    @abstractmethod
    def extract(self, text: str) -> Extraction:
        """Return the triples found in `text` as a validated Extraction."""


class ClaudeBackend(ReaderBackend):
    def __init__(self, model: str = DEFAULT_CLAUDE_MODEL):
        self.model = model

    def extract(self, text: str) -> Extraction:
        import anthropic  # imported here so mock/ollama users don't need it

        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the env
        response = client.messages.parse(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
            output_format=Extraction,  # <-- our schema IS the contract
        )
        return response.parsed_output  # already a validated Extraction


class OllamaBackend(ReaderBackend):
    def __init__(self, model: str = DEFAULT_OLLAMA_MODEL,
                 host: str = "http://localhost:11434"):
        self.model = model
        self.host = host

    def extract(self, text: str) -> Extraction:
        import requests

        response = requests.post(
            f"{self.host}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                "format": Extraction.model_json_schema(),  # schema as guidance
                "stream": False,
                "options": {"temperature": 0},  # deterministic-ish extraction
            },
            timeout=300,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
        # A local model gives no guarantee -- WE validate against the schema.
        return Extraction.model_validate_json(content)


class MockBackend(ReaderBackend):
    def __init__(self, fixture: Path = MOCK / "PMC_SAMPLE.json"):
        self.fixture = fixture

    def extract(self, text: str) -> Extraction:
        # Ignores `text`; returns a fixed, pre-written answer. For offline demos.
        return Extraction.model_validate_json(self.fixture.read_text())


def make_backend(name: str, model: str | None = None) -> ReaderBackend:
    """Factory: turn a backend name into the matching object."""
    if name == "claude":
        return ClaudeBackend(model or DEFAULT_CLAUDE_MODEL)
    if name == "ollama":
        return OllamaBackend(model or DEFAULT_OLLAMA_MODEL)
    if name == "mock":
        return MockBackend()
    raise ValueError(f"unknown backend: {name!r} (choose claude, ollama, or mock)")


def read_paper(pmcid: str, backend: ReaderBackend) -> Extraction:
    """Load M1's sentences for a paper, extract triples, save them."""
    processed = PROCESSED / f"{pmcid}.json"
    if not processed.exists():
        raise FileNotFoundError(
            f"{processed} not found -- run `python -m pipeline.ingest {pmcid}` first."
        )
    doc = json.loads(processed.read_text(encoding="utf-8"))
    text = "\n".join(doc["sentences"])

    extraction = backend.extract(text)

    EXTRACTIONS.mkdir(parents=True, exist_ok=True)
    out_path = EXTRACTIONS / f"{pmcid}.json"
    out_path.write_text(extraction.model_dump_json(indent=2), encoding="utf-8")
    return extraction


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract kinase triples from a paper.")
    parser.add_argument("pmcid", nargs="?", default="PMC_SAMPLE")
    parser.add_argument("--backend", choices=["claude", "ollama", "mock"], default="claude")
    parser.add_argument("--model", default=None, help="Override the model id for the backend.")
    args = parser.parse_args(argv)

    backend = make_backend(args.backend, args.model)
    extraction = read_paper(args.pmcid, backend)

    print(f"Extracted {len(extraction.triples)} triples from {args.pmcid} "
          f"(backend={args.backend}):\n")
    for t in extraction.triples:
        site = t.phosphosite or "-"
        print(f"  [{t.confidence:>6}] {t.kinase} -> {t.substrate} @ {site}")
        print(f"           evidence: {t.evidence}")
    print(f"\nSaved to data/extractions/{args.pmcid}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
