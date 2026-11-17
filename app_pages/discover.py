from __future__ import annotations

import streamlit as st
import psycopg

from app_pages.shared import (
    cached_catalog_search,
    cached_provider_search,
    render_catalog_book,
    render_provider_result,
    require_catalog,
)
from booktok.catalog import list_taxonomy, log_impressions
from booktok.discovery import configured_providers
from booktok.embeddings import EmbeddingUnavailable, encode_query
from booktok.providers.base import ProviderError
from booktok.search_intent import parse_search_intent


require_catalog()
taxonomy = list_taxonomy()
provider_options = configured_providers()
label_options = {
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

st.title("Discover your next read")
st.caption("Search naturally, browse local catalog matches, and see where each record came from.")

with st.form("discover_form"):
    query = st.text_input(
        "What are you in the mood for?",
        placeholder="dark romance, enemies to lovers, very spicy",
    )
    selected_labels = st.multiselect(
        "Genre, trope, and theme filters",
        options=list(label_options),
        format_func=lambda label_id: label_options[label_id],
    )
    selected_spice = st.selectbox("Spice level", list(spice_options), index=0)
    selected_providers = st.multiselect(
        "Search metadata providers",
        options=provider_options,
        default=[provider for provider in ("open_library", "google_books") if provider in provider_options],
        format_func=lambda provider: {
            "open_library": "Open Library",
            "google_books": "Google Books",
            "hardcover": "Hardcover",
        }[provider],
    )
    submitted = st.form_submit_button(
        "Search books",
        type="primary",
        icon=":material/search:",
        width="stretch",
    )

if submitted:
    intent = parse_search_intent(query, taxonomy)
    label_ids = list(dict.fromkeys(intent["label_ids"] + selected_labels))
    spice = spice_options[selected_spice]
    if spice is None:
        spice = intent["spice_min"]
    vector = None
    if query.strip():
        try:
            vector = tuple(encode_query(query.strip()))
        except EmbeddingUnavailable:
            vector = None

    local_results = cached_catalog_search(
        intent["free_text"],
        vector,
        tuple(label_ids),
        spice,
        spice,
    )
    try:
        log_impressions([book["id"] for book in local_results], query)
    except psycopg.Error:
        st.warning("Search results loaded, but interaction logging could not reach PostgreSQL.")

    provider_results = {}
    provider_errors = {}
    if query.strip():
        for provider in selected_providers:
            try:
                provider_results[provider] = cached_provider_search(provider, query.strip(), 16)
            except ProviderError as exc:
                provider_errors[provider] = str(exc)
    st.session_state["discover_state"] = {
        "query": query,
        "label_ids": label_ids,
        "spice": spice,
        "vector": vector,
        "local": local_results,
        "providers": provider_results,
        "provider_errors": provider_errors,
        "matched_phrases": intent["matched_phrases"],
    }

state = st.session_state.get("discover_state")
if state:
    if state["matched_phrases"]:
        st.caption("Parsed from your search: " + " · ".join(state["matched_phrases"]))
    if state["query"] and not state["vector"]:
        st.info("Showing keyword and label matches. Install the optional local ML stack for semantic search.")

    st.subheader("From your local catalog")
    books = state["local"]
    if books:
        with st.grid("auto", min_column_width=210, gap="medium"):
            for book in books:
                render_catalog_book(book, f"discover_{book['id']}")
    else:
        st.info("No local matches yet. Add a provider result to grow your catalog.")

    if state["provider_errors"]:
        for provider, message in state["provider_errors"].items():
            st.warning(f"{provider.replace('_', ' ').title()}: {message}")

    for provider, results in state["providers"].items():
        provider_name = provider.replace("_", " ").title()
        st.subheader(f"{provider_name} results")
        if results:
            with st.grid("auto", min_column_width=210, gap="medium"):
                for record in results:
                    key = f"{provider}_{record['provider_record_id']}"
                    render_provider_result(record, key)
        else:
            st.caption("No results from this provider.")
elif not provider_options:
    st.info("No metadata providers are enabled.")

with st.expander("How search works"):
    st.write(
        "The app filters on the tags you named and combines them with semantic similarity "
        "when a local description embedding is available. Provider searches run only after "
        "you press Search books. Missing metadata stays visibly missing."
    )
