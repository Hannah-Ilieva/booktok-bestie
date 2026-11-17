import streamlit as st
import psycopg

from app_pages.shared import require_catalog, render_catalog_book
from booktok.catalog import list_taxonomy, log_impressions
from booktok.recommendations import recommend
from booktok.search_intent import parse_search_intent


require_catalog()
taxonomy = list_taxonomy()
tag_options = {
    label["id"]: f"{label['display_name']} · {label['label_type']}"
    for label in taxonomy
    if label["label_type"] != "spice"
}
spice_options = {
    "Any": None,
    "Level 1 · Closed door": 1,
    "Level 2 · Mild": 2,
    "Level 3 · Open door": 3,
    "Level 4 · Steamy": 4,
    "Level 5 · Explicit": 5,
}

st.title("Recommendations")
st.caption("A transparent starting point shaped by your search, verified labels, and reading history.")

with st.form("recommendation_form"):
    query = st.text_input(
        "What would you like to read next?",
        placeholder="cozy fantasy romance with found family",
    )
    selected_labels = st.multiselect(
        "Include these labels",
        options=list(tag_options),
        format_func=lambda label_id: tag_options[label_id],
    )
    spice = st.selectbox("Spice level", list(spice_options))
    submitted = st.form_submit_button(
        "Build my recommendations",
        type="primary",
        icon=":material/auto_awesome:",
        width="stretch",
    )

if submitted:
    intent = parse_search_intent(query, taxonomy)
    label_ids = list(dict.fromkeys(intent["label_ids"] + selected_labels))
    spice_level = spice_options[spice]
    if spice_level is None:
        spice_level = intent["spice_min"]
    results, semantic_enabled = recommend(
        query=query,
        label_ids=label_ids,
        spice_min=spice_level,
        spice_max=spice_level,
        limit=12,
    )
    try:
        log_impressions([book["id"] for book in results], query, source="recommendations")
    except psycopg.Error:
        st.warning("Recommendations loaded, but impressions could not be logged.")
    st.session_state["recommendation_state"] = {
        "query": query,
        "results": results,
        "semantic_enabled": semantic_enabled,
        "matched_phrases": intent["matched_phrases"],
    }

state = st.session_state.get("recommendation_state")
if state:
    if state["matched_phrases"]:
        st.caption("Parsed from your search: " + " · ".join(state["matched_phrases"]))
    if not state["semantic_enabled"]:
        st.info("This run used label matches and reading history. Install the optional ML stack for semantic scoring.")
    if not state["results"]:
        st.info("No unseen catalog matches yet. Search for books in Discover to grow your catalog.")
    else:
        with st.grid("auto", min_column_width=270, gap="medium"):
            for book in state["results"]:
                render_catalog_book(
                    book,
                    f"recommendation_{book['id']}",
                    reasons=book["reasons"],
                    score_parts=book["score_parts"],
                    score_weights=book["score_weights"],
                    rank_score=book["score"],
                    allow_skip=True,
                )

with st.expander("How the baseline ranks books"):
    st.write(
        "The current score combines local description similarity, overlap with your selected "
        "labels, and signals from books you rated or explicitly saved. Unverified model labels "
        "do not shape reading-history preferences. Each card shows its score components and reasons."
    )
    st.caption("No accuracy claims are made. XGBoost training stays off until there is enough reviewed interaction data.")
