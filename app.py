from pathlib import Path

import streamlit as st


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

st.title("📚 BookTok Bestie")
st.caption("Your cozy corner for tracking your next favorite read.")
st.write("A little space for books, moods, tropes, and reading stats.")