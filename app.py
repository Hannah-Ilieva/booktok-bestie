from pathlib import Path

import streamlit as st

from database import add_book, get_books, initialize_database

from database import add_book, get_books, initialize_database, update_book

def load_css():
    css_path = Path(__file__).parent / "styles.css"
    css = css_path.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


st.set_page_config(
    page_title="BookTok Bestie",
    page_icon="📚",
    layout="wide"
)

load_css()
initialize_database()

st.title("📚 BookTok Bestie")
st.caption("Your cozy corner for tracking your next favorite read.")

st.subheader("Add a book")

with st.form("add_book_form", clear_on_submit=True):
    left_column, right_column = st.columns(2)

    title = left_column.text_input("Title")
    author = right_column.text_input("Author")
    genre = left_column.text_input("Genre (optional)")

    status = right_column.selectbox(
        "Reading status",
        ["Want to Read", "Currently Reading", "Finished", "DNF"]
    )

    total_pages = left_column.number_input(
        "Total pages (optional)",
        min_value=0,
        step=1
    )

    submitted = st.form_submit_button("Add to my shelf")

if submitted:
    if not title.strip() or not author.strip():
        st.error("Please enter both a title and an author.")
    else:
        pages = total_pages if total_pages > 0 else None
        add_book(title.strip(), author.strip(), genre.strip(), status, pages)
        st.success(f"Added *{title.strip()}* to your shelf!")
        st.rerun()

st.subheader("My shelf")

books = get_books()

if not books:
    st.info("Your shelf is empty. Add your first book above!")
else:
    visible_books = [
        {key: value for key, value in book.items() if key != "id"}
        for book in books
    ]
    st.dataframe(visible_books, hide_index=True, use_container_width=True)

    st.subheader("Update progress, rating, and review")

    selected_book = st.selectbox(
        "Choose a book",
        books,
        format_func=lambda book: f"{book['title']} — {book['author']}"
    )

    status_options = [
        "Want to Read",
        "Currently Reading",
        "Finished",
        "DNF"
    ]

    with st.form("update_book_form"):
        current_page = st.number_input(
            "Current page",
            min_value=0,
            max_value=selected_book["total_pages"],
            value=selected_book["current_page"],
            step=1
        )

        status = st.selectbox(
            "Reading status",
            status_options,
            index=status_options.index(selected_book["status"])
        )

        rating = st.slider(
            "Rating (0 means unrated)",
            min_value=0.0,
            max_value=5.0,
            value=float(selected_book["rating"] or 0),
            step=0.5
        )

        review = st.text_area(
            "Review",
            value=selected_book["review"] or ""
        )

        save_changes = st.form_submit_button("Save changes")

    if save_changes:
        update_book(
            selected_book["id"],
            current_page,
            status,
            rating if rating > 0 else None,
            review.strip()
        )
        st.success("Your book details have been updated.")
        st.rerun()