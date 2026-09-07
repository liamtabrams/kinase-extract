"""
Milestone 2 (part 1) -- the extraction schema.

This file defines the TYPED CONTRACT the Reader Agent must fill. We hand these
Pydantic models to Claude via `messages.parse(..., output_format=Extraction)`,
and the API constrains the model's output to match. The SDK then validates the
response and hands us real Python objects -- not a string we have to hope is
valid JSON.

Two models:
  * KinaseTriple -- one extracted relationship.
  * Extraction   -- a container holding a list of triples. We need a container
                    because `output_format` requires a single object/model at
                    the top level, not a bare list.

>>> YOUR TASK: fill in the four TODO field definitions below. <<<

Remember the two ideas from the walkthrough:
  1. The `description=` text is sent to Claude -- write it as an instruction.
  2. Field types + which fields are required = policy the schema enforces.

When you're done, test it with no API calls:

    python -c "from pipeline.schema import KinaseTriple, Extraction; \
        import json; print(json.dumps(Extraction.model_json_schema(), indent=2))"

That prints the exact JSON Schema Claude will see. Then try building one by
hand to watch validation work:

    python -c "from pipeline.schema import KinaseTriple; \
        print(KinaseTriple(kinase='BRAF', substrate='MEK1', phosphosite=None, \
        evidence='BRAF phosphorylates MEK1.', confidence='high'))"
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class KinaseTriple(BaseModel):
    """One kinase -> substrate phosphorylation relationship pulled from text."""

    # TODO 1 -- kinase: str (required)
    #   The enzyme doing the phosphorylating, exactly as named in the text
    #   (e.g. "BRAF", "MEK1"). Write a `description=` that tells Claude to use
    #   the name as written, not to normalize it.
    #
    # TODO 2 -- substrate: str (required)
    #   The protein being phosphorylated (e.g. "MEK1", "ERK2"), as named.
    #
    # TODO 3 -- phosphosite: Optional[str] (default None)
    #   The specific residue + position, e.g. "Ser383" or "Thr202". Many
    #   sentences don't give one -- so this is OPTIONAL. Making it optional is a
    #   policy choice: "a triple is still valid without a named site." Your
    #   description should tell Claude to return null when no site is stated.
    #
    # TODO 4 -- evidence: str (required)
    #   The exact sentence the relationship came from. Required on purpose --
    #   every claim must cite its evidence. Tell Claude to quote verbatim.
    #
    # TODO 5 -- confidence: Literal["high", "medium", "low"] (required)
    #   How explicitly the text asserts THIS specific relationship. Using a
    #   Literal (an enum) instead of a 0-1 float is deliberate: LLMs calibrate
    #   coarse buckets far better than fake-precise numbers, and the enum
    #   constrains the model to three valid answers. Describe what each level
    #   means (high = directly stated; low = hedged/inferred).

    # ... your five fields go here ...


class Extraction(BaseModel):
    """Everything the Reader Agent found in one chunk of text."""

    # TODO 6 -- triples: list[KinaseTriple]
    #   The list of all relationships found. Give it a `description` and a
    #   default of an empty list, so "found nothing" is a valid, clean result
    #   rather than an error.

    # ... your one field goes here ...
