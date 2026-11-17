import streamlit as st


st.set_page_config(
    page_title="BookTok Bestie",
    page_icon=":material/auto_stories:",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("BookTok Bestie")
st.sidebar.caption("Your local bookshop for the next favorite read.")

pages = {
    "Read": [
        st.Page("app_pages/discover.py", title="Discover", icon=":material/search:"),
        st.Page("app_pages/shelf.py", title="My shelf", icon=":material/bookmark:"),
        st.Page("app_pages/recommendations.py", title="Recommendations", icon=":material/auto_awesome:"),
        st.Page("app_pages/stats.py", title="Reading stats", icon=":material/insights:"),
    ],
    "Improve the catalog": [
        st.Page("app_pages/review.py", title="Labels and review", icon=":material/rule:"),
        st.Page("app_pages/settings.py", title="Local setup", icon=":material/settings:"),
    ],
}

page = st.navigation(pages, position="sidebar")
page.run()
