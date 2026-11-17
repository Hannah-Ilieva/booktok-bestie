import streamlit as st
import psycopg

from app_pages.shared import STATUSES, require_catalog
from booktok.catalog import create_manual_work, shelf_books, update_shelf_entry


require_catalog()
st.title("My shelf")
st.caption("Keep your reading history, progress, ratings, and reviews together.")

with st.expander("Add a book manually"):
    with st.form("manual_book_form", clear_on_submit=True):
        first, second = st.columns(2)
        title = first.text_input("Title")
        authors = second.text_input("Author or authors")
        genre = first.text_input("Genre", placeholder="Romance, fantasy, mystery…")
        status = second.selectbox("Reading status", STATUSES)
        pages = first.number_input("Total pages", min_value=0, step=1)
        description = st.text_area("Description", help="Used for local search and optional classification.")
        submitted = st.form_submit_button("Add to my shelf", type="primary")
    if submitted:
        try:
            create_manual_work(title, authors, description, genre, status, int(pages) or None)
            st.success(f"Added {title.strip()} to your shelf.")
            st.rerun()
        except (ValueError, psycopg.Error) as exc:
            st.error(str(exc) if isinstance(exc, ValueError) else "Could not save the book to PostgreSQL.")

first, second = st.columns([2, 1], vertical_alignment="bottom")
search = first.text_input("Find a shelf book", placeholder="Title or author")
status_filter = second.selectbox("Status", ["All statuses", *STATUSES])
books = shelf_books(search, None if status_filter == "All statuses" else status_filter)

if not books:
    st.info("No shelf entries match yet. Add a book above or save one from Discover.")
else:
    st.caption(f"Showing {len(books)} shelf entr{'y' if len(books) == 1 else 'ies'}.")
    with st.grid("auto", min_column_width=300, gap="medium"):
        for book in books:
            with st.container(border=True, height="stretch"):
                if book.get("cover_url"):
                    st.image(book["cover_url"], alt=f"Cover of {book['title']}", width="stretch")
                else:
                    st.caption("Cover not available")
                st.subheader(book["title"])
                st.caption(book["authors"] or "Author details not available")
                st.caption(f"Reading status · {book['status']}")
                if book["total_pages"]:
                    progress = min(book["current_page"] / book["total_pages"], 1.0)
                    st.progress(progress, text=f"Page {book['current_page']} of {book['total_pages']}")
                if book.get("description"):
                    with st.expander("About this book"):
                        st.write(book["description"])

                with st.form(f"shelf_update_{book['shelf_id']}"):
                    new_status = st.selectbox(
                        "Reading status",
                        STATUSES,
                        index=STATUSES.index(book["status"]),
                        key=f"status_{book['shelf_id']}",
                    )
                    current_page = st.number_input(
                        "Current page",
                        min_value=0,
                        value=int(book["current_page"] or 0),
                        step=1,
                        key=f"page_{book['shelf_id']}",
                    )
                    total_pages = st.number_input(
                        "Total pages",
                        min_value=0,
                        value=int(book["total_pages"] or 0),
                        step=1,
                        key=f"total_{book['shelf_id']}",
                    )
                    rating = st.slider(
                        "Rating · 0 means unrated",
                        min_value=0.0,
                        max_value=5.0,
                        value=float(book["rating"] or 0),
                        step=0.5,
                        key=f"rating_{book['shelf_id']}",
                    )
                    review = st.text_area(
                        "Review",
                        value=book["review"] or "",
                        key=f"review_{book['shelf_id']}",
                    )
                    save = st.form_submit_button("Save changes", width="stretch")
                if save:
                    try:
                        update_shelf_entry(
                            book["shelf_id"],
                            new_status,
                            int(current_page),
                            int(total_pages) or None,
                            float(rating) or None,
                            review.strip(),
                        )
                        st.success("Shelf entry updated.")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
                    except psycopg.Error:
                        st.error("Could not update this shelf entry. Check the local PostgreSQL service.")
