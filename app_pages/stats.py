import pandas as pd
import streamlit as st

from app_pages.shared import require_catalog
from booktok.catalog import catalog_activity_stats, reading_stat_breakdowns, reading_stats


require_catalog()
st.title("Reading stats")
st.caption("A clear view of your shelf and the local catalog behind your recommendations.")

stats = reading_stats()
metrics = [
    ("Books on shelf", stats["total_books"]),
    ("Finished", stats["finished_books"]),
    ("Currently reading", stats["currently_reading"]),
    ("Pages read", stats["pages_read"]),
]
with st.grid(4, gap="medium"):
    for label, value in metrics:
        st.metric(label, value, border=True, height="stretch")

average_rating = stats["average_rating"]
st.metric(
    "Average rating",
    f"{average_rating} / 5" if average_rating is not None else "Not rated yet",
    border=True,
)

breakdowns = reading_stat_breakdowns()
left, right = st.columns(2)
with left.container(border=True):
    st.subheader("Books by status")
    if breakdowns["statuses"]:
        st.bar_chart(
            pd.DataFrame(breakdowns["statuses"]),
            x="label",
            y="total",
            alt="Number of books in each reading status",
        )
    else:
        st.caption("Your shelf is empty so far.")
with right.container(border=True):
    st.subheader("Books by genre")
    if breakdowns["genres"]:
        st.bar_chart(
            pd.DataFrame(breakdowns["genres"]),
            x="label",
            y="total",
            alt="Number of shelf books by genre",
        )
    else:
        st.caption("Add genre details to see this chart.")

if breakdowns["ratings"]:
    st.subheader("Your ratings")
    st.bar_chart(
        pd.DataFrame(breakdowns["ratings"]),
        x="label",
        y="total",
        alt="Number of shelf books at each rating",
    )

activity = catalog_activity_stats()
st.subheader("Catalog and recommendation data")
catalog_metrics = [
    ("Catalog works", activity["catalog_works"]),
    ("Description embeddings", activity["embedded_works"]),
    ("Unverified label suggestions", activity["unverified_labels"]),
    ("Human label corrections", activity["label_corrections"]),
    ("Pending match reviews", activity["pending_match_reviews"]),
    ("Recorded interactions", activity["interactions"]),
]
with st.grid(3, gap="medium"):
    for label, value in catalog_metrics:
        st.metric(label, value, border=True, height="stretch")
