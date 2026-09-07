"""
Milestone 2 (part 1) -- the extraction schema.

This file defines the TYPED CONTRACT the Reader Agent must fill. We hand these
Pydantic models to Claude via `messages.parse(..., output_format=Extraction)`,
and the API constrains the model's output to match. The SDK then validates the
response and hands us real Python objects -- not a string we have to hope is
valid JSON.

Two models:
  * KinaseTriple -- one extracted relationship (kinase -> substrate [at site]).
  * Extraction   -- a container holding a list of triples. We need a container
                    because `output_format` requires a single object/model at
                    the top level, not a bare list.

The `description=` text on each field is NOT just documentation -- it is sent to
Claude as part of the JSON Schema, so each description is really an instruction
that steers extraction. Read them as prompts.

Test it with no API calls:

    # The exact JSON Schema Claude will see:
    python -c "from pipeline.schema import Extraction; import json; \
        print(json.dumps(Extraction.model_json_schema(), indent=2))"

    # Validation succeeds on a well-formed triple:
    python -c "from pipeline.schema import KinaseTriple; \
        print(KinaseTriple(kinase='BRAF', substrate='MEK1', phosphosite=None, \
        evidence='BRAF phosphorylates MEK1.', confidence='high'))"

    # Validation FAILS on a bad confidence value (this is the point!):
    python -c "from pipeline.schema import KinaseTriple; \
        KinaseTriple(kinase='BRAF', substrate='MEK1', phosphosite=None, \
        evidence='x', confidence='very high')"
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class KinaseTriple(BaseModel):
    """One kinase -> substrate phosphorylation relationship pulled from text."""

    kinase: str = Field(
        description=(
            "The enzyme (kinase) protein that adds the phosphate group, written "
            "exactly as it appears in the text (e.g. 'BRAF', 'MEK1', 'ERK2'). "
            "Do not rename, expand, or normalize it -- copy the name as written."
        )
    )

    substrate: str = Field(
        description=(
            "The protein that receives the phosphate group (the substrate), "
            "written exactly as it appears in the text (e.g. 'MEK1', 'ERK2', "
            "'ELK1'). Do not rename or normalize it -- copy the name as written."
        )
    )

    phosphosite: Optional[str] = Field(
        default=None,
        description=(
            "The specific residue and position that is phosphorylated, if the "
            "text states one (e.g. 'Ser218', 'Thr202', 'Tyr204'). Many sentences "
            "name no site; return null in that case rather than guessing."
        ),
    )

    evidence: str = Field(
        description=(
            "The single sentence from the text that states this relationship, "
            "quoted verbatim. This is the evidence a human reviewer will read, "
            "so it must come straight from the source -- do not paraphrase."
        )
    )

    confidence: Literal["high", "medium", "low"] = Field(
        description=(
            "How explicitly the text asserts THIS specific kinase->substrate "
            "phosphorylation. 'high' = directly and unambiguously stated (e.g. "
            "'X phosphorylates Y'); 'medium' = stated but less direct, or the "
            "roles are slightly implied; 'low' = hedged, indirect, or inferred "
            "rather than clearly claimed."
        )
    )


class Extraction(BaseModel):
    """Everything the Reader Agent found in one chunk of text."""

    triples: list[KinaseTriple] = Field(
        default_factory=list,
        description=(
            "Every kinase-substrate-phosphosite relationship found in the text. "
            "Return an empty list if the text states none -- do not invent "
            "relationships that are not supported by a sentence."
        ),
    )
