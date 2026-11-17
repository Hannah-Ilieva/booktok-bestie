import streamlit as st
import psycopg

from app_pages.shared import require_catalog
from booktok.catalog import (
    add_or_update_taxonomy,
    classification_queue,
    list_pending_match_reviews,
    list_taxonomy,
    mark_match_review,
    merge_review_candidate,
    replace_work_label_type,
    set_taxonomy_active,
    work_labels,
)


require_catalog()
st.title("Labels and review")
st.caption("Model suggestions stay unverified until you review them. Unknown is a valid result.")

taxonomy = list_taxonomy()
taxonomy_by_type = {
    label_type: [label for label in taxonomy if label["label_type"] == label_type]
    for label_type in ("genre", "trope", "theme", "spice")
}
works = classification_queue()

st.subheader("Review book labels")
if not works:
    st.info("The catalog has no works to review yet. Search for books in Discover first.")
else:
    selected_work = st.selectbox(
        "Choose a book",
        works,
        format_func=lambda work: (
            f"{work['title']} — {work['authors'] or 'author unknown'} "
            f"· {work['unverified_labels']} suggestions · {work['verified_labels']} verified"
        ),
    )
    st.write(selected_work["description"] or "No description supplied. Labels remain unknown until there is enough source text.")
    assignments = work_labels(selected_work["id"])
    if assignments:
        for label in assignments:
            verification = "Reader verified" if label["human_verified"] else "Model suggestion · unverified"
            score = (
                f" · similarity/cue score {float(label['confidence']):.2f}"
                if label["confidence"] is not None
                else ""
            )
            version = f" · {label['model_name']} {label['model_version']}" if label["model_name"] else ""
            st.caption(f"{label['label_type'].title()} · {label['display_name']} · {verification}{score}{version}")
    else:
        st.info("No current labels. The source may be too short or the model found no strong match.")

    current_type = st.selectbox("Label category to review", ["genre", "trope", "theme", "spice"])
    current_ids = list(dict.fromkeys(
        label["label_id"] for label in assignments
        if label["label_type"] == current_type
    ))
    available = taxonomy_by_type[current_type]
    with st.form(f"review_labels_{selected_work['id']}_{current_type}"):
        selected_ids = st.multiselect(
            "Verified labels",
            options=[label["id"] for label in available],
            default=[label_id for label_id in current_ids if label_id in {row["id"] for row in available}],
            format_func=lambda label_id: next(
                row["display_name"] for row in available if row["id"] == label_id
            ),
        )
        note = st.text_input("Correction note (optional)")
        save = st.form_submit_button("Save reviewed labels", type="primary")
    if save:
        try:
            replace_work_label_type(
                selected_work["id"], current_type, selected_ids, note
            )
            st.success("Your label review and correction history were saved.")
            st.rerun()
        except (ValueError, psycopg.Error) as exc:
            st.error(str(exc) if isinstance(exc, ValueError) else "Could not save the label review.")

with st.expander("Edit the label taxonomy"):
    st.caption("Spice is subjective; descriptions are editable reader guidance, not an objective scale.")
    all_labels = list_taxonomy(active_only=False)
    label_choices = {label["id"]: f"{label['label_type'].title()} · {label['display_name']}" for label in all_labels}
    selected_label_id = st.selectbox(
        "Edit an existing label",
        [None, *label_choices],
        format_func=lambda label_id: "Create a new label" if label_id is None else label_choices[label_id],
    )
    existing_label = next((label for label in all_labels if label["id"] == selected_label_id), None)
    with st.form("taxonomy_form"):
        if existing_label:
            label_type = st.selectbox(
                "Category",
                [existing_label["label_type"]],
                disabled=True,
            )
            name = st.text_input("Name", value=existing_label["display_name"])
            description = st.text_area("Definition", value=existing_label["description"] or "")
            spice_level = st.selectbox(
                "Spice level",
                [1, 2, 3, 4, 5],
                index=(existing_label["spice_level"] or 1) - 1,
                disabled=existing_label["label_type"] != "spice",
            )
        else:
            label_type = st.selectbox("Category", ["genre", "trope", "theme", "spice"])
            name = st.text_input("Name")
            description = st.text_area("Definition")
            spice_level = st.selectbox("Spice level", [1, 2, 3, 4, 5])
        save_label = st.form_submit_button("Save taxonomy label")
    if save_label:
        try:
            add_or_update_taxonomy(
                label_type,
                name,
                description,
                spice_level if label_type == "spice" else None,
                selected_label_id,
            )
            st.success("Taxonomy label saved.")
            st.rerun()
        except (ValueError, psycopg.Error) as exc:
            st.error(str(exc) if isinstance(exc, ValueError) else "Could not update the taxonomy.")
    if existing_label:
        if existing_label["is_active"]:
            if st.button("Archive this label", key=f"archive_label_{selected_label_id}"):
                set_taxonomy_active(selected_label_id, False)
                st.rerun()
        else:
            if st.button("Restore this label", key=f"restore_label_{selected_label_id}"):
                set_taxonomy_active(selected_label_id, True)
                st.rerun()

st.subheader("Possible duplicate works")
reviews = list_pending_match_reviews()
if not reviews:
    st.caption("No possible duplicates need review.")
else:
    for review in reviews:
        with st.container(border=True):
            st.markdown(
                f"**{review['incoming_title']}**  \nmay match  \n"
                f"**{review['candidate_title']}**"
            )
            st.caption(f"Title similarity · {float(review['similarity_score']):.0%} · review required; records were not merged automatically.")
            merge_column, separate_column = st.columns(2)
            if merge_column.button("Merge as the same work", key=f"merge_{review['id']}"):
                try:
                    merge_review_candidate(review["id"])
                    st.success("Catalog records merged; shelf, source, and interaction links were retained.")
                    st.rerun()
                except (ValueError, psycopg.Error) as exc:
                    st.error(str(exc) if isinstance(exc, ValueError) else "Could not merge these records safely.")
            if separate_column.button("Keep separate", key=f"separate_{review['id']}"):
                mark_match_review(review["id"], "kept_separate")
                st.rerun()

st.subheader("Run local classification")
st.code(
    r".\.venv\Scripts\python.exe -m scripts.classify_catalog --limit 100",
    language="powershell",
)
st.caption("Predictions are suggestions. Similarity scores are not calibrated probabilities or accuracy claims.")
