"""
Milestone 5 (UI) -- the human-in-the-loop review app.

Run it:
    streamlit run app.py

HOW STREAMLIT WORKS (the mental model you need):
  * Streamlit runs this whole script top-to-bottom EVERY TIME you interact with
    any widget. Click a button, move a radio -> the entire file re-executes.
  * So you don't write callbacks and event loops; you write a script that
    "draws" the page from the current state, and Streamlit re-runs it.
  * Widget values survive those re-runs via `st.session_state`, keyed by the
    `key=` you give each widget. That's how a radio remembers your choice.
  * Anything you want to keep BEYOND the session (across app restarts) you must
    write to disk yourself -- that's what the Save button does.

This file is intentionally thin: all data loading/saving lives in
pipeline/review.py. app.py only turns that data into widgets.
"""

from __future__ import annotations

import streamlit as st

from pipeline.curation import add_reviewed, count as curated_count
from pipeline.review import flagged, load_batch, load_report, save_batch
from pipeline.schema import KinaseTriple, ReviewBatch, ReviewedTriple

st.set_page_config(page_title="kinase-extract review", layout="centered")
st.title("🧪 Kinase triple review")

# --- Sidebar: which paper, and who's reviewing -------------------------------
with st.sidebar:
    pmcid = st.text_input("Paper (PMCID)", value="PMC_SAMPLE")
    reviewer = st.text_input("Reviewer name", value="")
    st.caption("Only *flagged* triples (contradicted / novel) are shown. "
               "Confirmed triples are auto-accepted.")

# --- Load this paper's validation report -------------------------------------
try:
    report = load_report(pmcid)
except FileNotFoundError as exc:
    st.error(str(exc))
    st.stop()  # halts the script cleanly -- nothing below runs

to_review = flagged(report)
existing = load_batch(pmcid)  # prior decisions, if any, to pre-fill the widgets
prior = {rt.validated.triple.evidence: rt for rt in (existing.decisions if existing else [])}

st.write(f"**{len(to_review)}** flagged triple(s) to review in `{pmcid}` "
         f"(reference: {report.reference}).")

if not to_review:
    st.success("Nothing flagged — every triple was confirmed. 🎉")
    st.stop()

DECISION_LABELS = ["Approve", "Reject", "Edit"]
LABEL_TO_VALUE = {"Approve": "approved", "Reject": "rejected", "Edit": "edited"}

# --- One review card per flagged triple --------------------------------------
for i, vt in enumerate(to_review):
    t = vt.triple
    with st.container(border=True):
        badge = "❌ contradicted" if vt.status == "contradicted" else "❓ novel"
        st.markdown(f"### {t.kinase} → {t.substrate}  &nbsp; {badge}")
        st.markdown(f"- **Normalized:** `{vt.kinase_symbol} → {vt.substrate_symbol}`"
                    + (f" @ `{vt.normalized_site}`" if vt.normalized_site else ""))
        st.markdown(f"- **Machine verdict:** {vt.explanation}")
        st.markdown(f"- **Extractor confidence:** {t.confidence}")
        st.info(f"📄 Evidence: *{t.evidence}*")

        # Pre-select the decision from a prior saved review, if present.
        default_idx = 0
        if t.evidence in prior:
            saved_value = prior[t.evidence].decision
            default_idx = ["approved", "rejected", "edited"].index(saved_value)

        decision = st.radio(
            "Your decision", DECISION_LABELS, index=default_idx,
            horizontal=True, key=f"decision_{i}",
        )

        # Only when editing do we show the correction fields.
        if decision == "Edit":
            c1, c2, c3 = st.columns(3)
            c1.text_input("kinase", value=t.kinase, key=f"kinase_{i}")
            c2.text_input("substrate", value=t.substrate, key=f"substrate_{i}")
            c3.text_input("phosphosite", value=t.phosphosite or "", key=f"site_{i}")

        st.text_input("Note (optional)", key=f"note_{i}",
                      value=prior[t.evidence].note if t.evidence in prior else "")

# --- Save all decisions ------------------------------------------------------
if st.button("💾 Save decisions", type="primary"):
    decisions: list[ReviewedTriple] = []
    for i, vt in enumerate(to_review):
        label = st.session_state.get(f"decision_{i}", "Approve")
        value = LABEL_TO_VALUE[label]

        corrected = None
        if value == "edited":
            corrected = KinaseTriple(
                kinase=st.session_state.get(f"kinase_{i}", vt.triple.kinase),
                substrate=st.session_state.get(f"substrate_{i}", vt.triple.substrate),
                phosphosite=st.session_state.get(f"site_{i}") or None,
                evidence=vt.triple.evidence,       # evidence + confidence come from
                confidence=vt.triple.confidence,   # the source; edits fix the entities
            )

        decisions.append(ReviewedTriple(
            validated=vt, decision=value, corrected=corrected,
            note=st.session_state.get(f"note_{i}", ""),
        ))

    batch = ReviewBatch(pmcid=pmcid, reviewer=reviewer, decisions=decisions)
    path = save_batch(batch)
    # Complete the loop: push approved/edited findings into the curated atlas.
    added = add_reviewed(batch)
    st.success(f"Saved {len(decisions)} decision(s) to {path}. "
               f"Added {added} new finding(s) to the curated atlas "
               f"(now {curated_count()} total).")
