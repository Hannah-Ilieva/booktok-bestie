from __future__ import annotations

from typing import Any

import streamlit as st
import psycopg

from booktok.catalog import log_interaction
from booktok.db import connect, schema_status
from booktok.catalog import add_to_shelf
from booktok.discovery import save_provider_record, search_provider


STATUSES = ["Want to Read", "Currently Reading", "Finished", "DNF"]


def require_catalog() -> None:
    ready, message = schema_status()
    if ready:
        return
    st.title("BookTok Bestie")
    st.warning(message, icon=":material/database:")
    st.markdown(
        "Start Docker Desktop, then run `docker compose up -d db` and "
        "`.\\.venv\\Scripts\\python.exe -m scripts.apply_migrations`."
    )
    st.caption("Your existing SQLite shelf remains available with `streamlit run app.py`.")
    st.stop()


@st.cache_data(ttl=900, max_entries=64)
def cached_provider_search(provider: str, query: str, limit: int = 20) -> list[dict[str, Any]]:
    return search_provider(provider, query, limit)


@st.cache_data(ttl=120, max_entries=32)
def cached_catalog_search(
    query: str,
    query_vector: tuple[float, ...] | None,
    label_ids: tuple[int, ...],
    spice_min: int | None,
    spice_max: int | None,
    exclude_shelf: bool = False,
) -> list[dict[str, Any]]:
    from booktok.catalog import catalog_search

    return catalog_search(
        query=query,
        query_vector=list(query_vector) if query_vector else None,
        label_ids=list(label_ids),
        spice_min=spice_min,
        spice_max=spice_max,
        limit=40,
        exclude_shelf=exclude_shelf,
    )


def render_sources(sources: list[dict[str, Any]]) -> None:
    linked = [source for source in sources if source.get("url")]
    if not linked:
        st.caption("Source link not provided")
        return
    with st.container(horizontal=True, vertical_alignment="center"):
        for source in linked[:3]:
            st.link_button(
                source.get("provider", "Source").replace("_", " ").title(),
                source["url"],
                icon=":material/open_in_new:",
            )


def record_event(work_id: int, event_type: str, details: dict[str, Any] | None = None) -> None:
    with connect() as connection:
        log_interaction(connection, work_id, event_type, details=details)


@st.dialog("Book details", width="large")
def show_book_details(book: dict[str, Any]) -> None:
    st.subheader(book.get("title") or "Untitled")
    st.caption(book.get("authors") or "Author details not available")
    if book.get("description"):
        st.write(book["description"])
    else:
        st.info("This provider has not supplied a description.")
    labels = book.get("labels") or []
    if labels:
        st.markdown("**Current catalog labels**")
        for label in labels:
            state = "reader verified" if label.get("human_verified") else "model suggestion"
            detail = f" · similarity/cue score {float(label['confidence']):.2f}" if label.get("confidence") is not None else ""
            st.caption(f"{label['type'].title()} · {label['name']} · {state}{detail}")
    render_sources(book.get("sources") or [])


def render_catalog_book(
    book: dict[str, Any],
    key: str,
    status: str = "Want to Read",
    reasons: list[str] | None = None,
    score_parts: dict[str, float] | None = None,
    score_weights: dict[str, float] | None = None,
    rank_score: float | None = None,
    allow_skip: bool = False,
) -> None:
    with st.container(border=True, height="stretch"):
        cover = book.get("cover_url")
        if cover:
            st.image(cover, alt=f"Cover of {book['title']}", width="stretch")
        else:
            st.caption("Cover not available")
        st.subheader(book.get("title") or "Untitled")
        st.caption(book.get("authors") or "Author details not available")
        year = book.get("first_publication_year")
        if year:
            st.caption(f"First published · {year}")
        if book.get("semantic_score") is not None:
            semantic_score = min(max(float(book["semantic_score"]), 0.0), 1.0)
            st.caption(f"Description similarity · {semantic_score:.0%}")
        if book.get("description"):
            with st.expander("About this book"):
                st.write(book["description"])
        labels = book.get("labels") or []
        if labels:
            st.caption(
                " · ".join(
                    label["name"] if label["human_verified"] else f"{label['name']} (suggested)"
                    for label in labels[:4]
                )
            )
        elif not book.get("description"):
            st.caption("Metadata is incomplete; no description or verified labels yet.")
        if reasons:
            st.caption("Why it fits · " + "; ".join(reasons))
        if rank_score is not None:
            st.caption(f"Ranking score · {rank_score:.0%} (used to order these results)")
        sources = book.get("sources") or []
        render_sources(sources)
        if score_parts:
            with st.expander("Recommendation score details"):
                st.write(
                    " · ".join(
                        f"{name.replace('_', ' ').title()}: {value:.0%} "
                        f"(weight {(score_weights or {}).get(name, 0):.0%})"
                        for name, value in score_parts.items()
                    )
                )
        if st.button("View details", key=f"details_{key}", width="stretch"):
            try:
                record_event(book["id"], "click", {"source": "catalog_card"})
            except psycopg.Error:
                st.caption("Interaction logging was unavailable.")
            show_book_details(book)

        add_column, skip_column = st.columns(2) if allow_skip else (st.container(), None)
        if add_column.button("Add to my shelf", key=f"shelf_{key}", width="stretch"):
            try:
                if add_to_shelf(book["id"], status):
                    st.success(f"Added {book['title']} to your shelf.")
                else:
                    st.info("This work is already on your shelf.")
            except psycopg.Error:
                st.error("Could not update the shelf. Check the local PostgreSQL service.")
        if skip_column and skip_column.button("Not for me", key=f"skip_{key}", width="stretch"):
            try:
                record_event(book["id"], "skip", {"source": "recommendations"})
                st.info("Got it. I’ll use that feedback in future recommendations.")
            except psycopg.Error:
                st.error("Could not record that feedback.")


def render_provider_result(record: dict[str, Any], key: str) -> None:
    with st.container(border=True, height="stretch"):
        if record.get("cover_url"):
            st.image(record["cover_url"], alt=f"Cover of {record['title']}", width="stretch")
        else:
            st.caption("Cover not available")
        st.subheader(record.get("title") or "Untitled")
        st.caption(record.get("authors") and ", ".join(record["authors"]) or "Author details not available")
        details = []
        if record.get("publication_year") or record.get("first_publication_year"):
            details.append(str(record.get("publication_year") or record["first_publication_year"]))
        if record.get("page_count"):
            details.append(f"{record['page_count']} pages")
        st.caption(" · ".join(details) if details else "Edition details not provided")
        if record.get("description"):
            with st.expander("About this book"):
                st.write(record["description"])
        else:
            st.caption("Description not provided by this source")
        if record.get("source_url"):
            st.link_button(
                f"View on {record.get('provider_label', 'source')}",
                record["source_url"],
                icon=":material/open_in_new:",
                width="stretch",
            )
        else:
            st.caption("Source link not provided")

        catalog_column, shelf_column = st.columns(2, vertical_alignment="bottom")
        if catalog_column.button("Save to catalog", key=f"catalog_{key}", width="stretch"):
            try:
                saved = save_provider_record(record)
                cached_catalog_search.clear()
                st.success(f"Saved to catalog (record {saved['work_id']}).")
                try:
                    record_event(saved["work_id"], "save", {"source": "provider_result"})
                except psycopg.Error:
                    st.caption("Catalog record saved; interaction logging was unavailable.")
            except (ValueError, RuntimeError) as exc:
                st.warning(str(exc))
            except psycopg.Error:
                st.error("Could not save this record. Check the local PostgreSQL service.")
        if shelf_column.button("Add to shelf", key=f"shelf_external_{key}", width="stretch"):
            try:
                saved = save_provider_record(record)
            except (ValueError, RuntimeError) as exc:
                st.warning(str(exc))
            except psycopg.Error:
                st.error("Could not save this work to the catalog. Check the local PostgreSQL service.")
            else:
                try:
                    if add_to_shelf(saved["work_id"]):
                        cached_catalog_search.clear()
                        st.success(f"Added {record['title']} to your shelf.")
                    else:
                        st.info("This work is already on your shelf.")
                except psycopg.Error:
                    st.warning("Saved to the catalog, but the shelf could not be updated.")
