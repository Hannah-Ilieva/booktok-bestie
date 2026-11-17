import streamlit as st

from app_pages.shared import require_catalog
from booktok.db import PROJECT_ROOT
from booktok.discovery import configured_providers


require_catalog()
st.title("Local setup")
st.caption("BookTok Bestie runs on this computer. Catalog data and model files stay local.")

st.subheader("Metadata providers")
providers = configured_providers()
provider_names = {
    "open_library": "Open Library",
    "google_books": "Google Books",
    "hardcover": "Hardcover",
}
for provider in ("open_library", "google_books", "hardcover"):
    state = "ready" if provider in providers else "add an API token in .env"
    st.caption(f"{provider_names[provider]} · {state}")

st.write("Optional provider credentials belong in the ignored `.env` file:")
st.code("GOOGLE_BOOKS_API_KEY=\nHARDCOVER_API_TOKEN=", language="text")
st.caption("Google Books search can work without a key. Hardcover needs a personal API token. Restart Streamlit after editing .env.")

st.subheader("Local model")
st.write("Install Sentence Transformers with one command:")
st.code(
    r"powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -WithML",
    language="powershell",
)
st.caption(
    "The first semantic search or embedding run downloads the selected Sentence Transformer model to "
    f"`{PROJECT_ROOT / '.model-cache'}`. It runs locally on CPU and does not send book descriptions to a model API."
)

st.subheader("Manual catalog jobs")
st.write("Provider searches run only when you submit a search. Save individual records from Discover; these jobs process the local catalog:")
st.code(
    ".\\.venv\\Scripts\\python.exe -m scripts.ingest_embeddings --limit 250\n"
    ".\\.venv\\Scripts\\python.exe -m scripts.classify_catalog --limit 100",
    language="powershell",
)

st.subheader("SQLite shelf backup and import")
st.code(
    ".\\.venv\\Scripts\\python.exe -m scripts.backup_sqlite\n"
    ".\\.venv\\Scripts\\python.exe -m scripts.migrate_sqlite_to_postgres",
    language="powershell",
)
st.caption("The importer creates a verified timestamped backup, reads SQLite in read-only mode, skips previously imported IDs, and leaves booktok.db in place.")
