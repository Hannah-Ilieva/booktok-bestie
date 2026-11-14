from pathlib import Path

import streamlit as st
from recommendations import recommend_books
from database import add_book, get_books, initialize_database, update_book
from database import (
    add_book,
    get_books,
    get_reading_stats,
    initialize_database,
    update_book,
)

def load_css():
    css_path = Path(__file__).parent / "styles.css"
    css = css_path.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


mood_options = [
    "Cozy",
    "Romantic",
    "Funny",
    "Emotional",
    "Adventurous",
    "Dark",
    "Thought-provoking"
]

trope_options = [
    "Found family",
    "Enemies to lovers",
    "Friends to lovers",
    "Slow burn",
    "Fake dating",
    "Grumpy x sunshine",
    "Second chance",
    "Forced proximity",
    "Mystery"
]

status_options = [
    "Want to Read",
    "Currently Reading",
    "Finished",
    "DNF"
]


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
    status = right_column.selectbox("Reading status", status_options)

    total_pages = left_column.number_input(
        "Total pages (optional)",
        min_value=0,
        step=1
    )

    mood = left_column.selectbox("Mood", mood_options)
    tropes = right_column.multiselect("Tropes", trope_options)

    submitted = st.form_submit_button("Add to my shelf")

if submitted:
    if not title.strip() or not author.strip():
        st.error("Please enter both a title and an author.")
    else:
        pages = total_pages if total_pages > 0 else None

        add_book(
            title.strip(),
            author.strip(),
            genre.strip() or None,
            status,
            pages,
            mood,
            ", ".join(tropes)
        )

        st.success(f"Added *{title.strip()}* to your shelf!")
        st.rerun()


st.subheader("My shelf")

books = get_books()

stats = get_reading_stats()

st.subheader("Your reading stats")
stat_columns = st.columns(5)

stat_columns[0].metric("Books on shelf", stats["total_books"])
stat_columns[1].metric("Currently reading", stats["currently_reading"])
stat_columns[2].metric("Finished", stats["finished_books"])
stat_columns[3].metric("Pages read", stats["pages_read"])

average_rating = stats["average_rating"]
rating_display = f"{average_rating} / 5" if average_rating is not None else "—"
stat_columns[4].metric("Average rating", rating_display)

if not books:
    st.info("Your shelf is empty. Add your first book above!")
else:
    visible_books = [
        {
            "Title": book["title"],
            "Author": book["author"],
            "Genre": book["genre"] or "",
            "Status": book["status"],
            "Current page": book["current_page"],
            "Total pages": book["total_pages"] or "",
            "Rating": book["rating"] or "",
            "Mood": book["mood"] or "",
            "Tropes": book["tropes"] or ""
        }
        for book in books
    ]

    st.dataframe(
        visible_books,
        hide_index=True,
        use_container_width=True
    )

    st.subheader("Update progress, rating, and review")

    selected_book = st.selectbox(
        "Choose a book",
        books,
        format_func=lambda book: f"{book['title']} — {book['author']}"
    )

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


        st.subheader("Find your next read")

with st.form("recommendation_form"):
    preferred_mood = st.selectbox(
        "What mood are you in?",
        mood_options
    )

    preferred_tropes = st.multiselect(
        "Which tropes sound good?",
        trope_options
    )

    get_recommendations = st.form_submit_button("Find my next read")

if get_recommendations:
    recommendations = recommend_books(
        books,
        preferred_mood,
        preferred_tropes
    )

    if recommendations:
        st.write("Here are your best matches:")

        for book in recommendations[:5]:
            st.markdown(f"**{book['title']}** — {book['author']}")
            st.caption(
                f"Mood: {book['mood']} · Tropes: {book['tropes'] or 'None listed'}"
            )
    else:
        st.info(
            "No matches yet. Add a book marked 'Want to Read' "
            "with a matching mood or trope."
        )