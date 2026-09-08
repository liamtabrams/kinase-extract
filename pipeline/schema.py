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


# ---------------------------------------------------------------------------
# M3 -- validation types.
#
# The Validator (M3b) does NOT change the extracted triple; it *annotates* it
# with a verdict from the reference database. So ValidatedTriple keeps the
# original triple intact and adds the validation fields alongside it. Keeping
# the source triple untouched means we never lose what the paper actually said.
# ---------------------------------------------------------------------------

# The three verdicts. Note these are validation types, not Pydantic BaseModels.
ValidationStatus = Literal["confirmed", "contradicted", "novel"]


class ValidatedTriple(BaseModel):
    """One extracted triple plus the verdict from checking it against OmniPath."""

    triple: KinaseTriple

    # The normalized identifiers we actually looked up (from M3a):
    kinase_symbol: str
    substrate_symbol: str
    normalized_site: Optional[str] = None

    status: ValidationStatus
    # True/False if a site was given and we could check it against the DB;
    # None if there was no site, or the pair wasn't found at all.
    site_in_db: Optional[bool] = None

    explanation: str  # plain-language reason for the verdict


class ValidationReport(BaseModel):
    """The Validator's output for one paper: every triple, labeled."""

    pmcid: str
    reference: str  # which database backed the check, e.g. "omnipath" or "fixture"
    results: list[ValidatedTriple] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# M5 -- human-in-the-loop review types.
#
# A reviewer looks at a flagged triple and does one of three things. We capture
# the decision AND (if edited) the corrected triple, because these decisions
# become the GOLD LABELS that M6 evaluates against and any future fine-tune
# would train on. The reviewed batch is the whole point of the HITL step:
# it turns a person's judgment into reusable, structured data.
# ---------------------------------------------------------------------------

ReviewDecision = Literal["approved", "rejected", "edited"]


class ReviewedTriple(BaseModel):
    """A reviewer's verdict on one validated triple."""

    validated: ValidatedTriple            # what the machine produced (kept intact)
    decision: ReviewDecision
    corrected: Optional[KinaseTriple] = None  # the fixed triple, only if edited
    note: str = ""                        # optional free-text reviewer comment


class ReviewBatch(BaseModel):
    """All of one reviewer's decisions for one paper."""

    pmcid: str
    reviewer: str = ""
    decisions: list[ReviewedTriple] = Field(default_factory=list)
