# BookTok Bestie

A local reading tracker built with Python, Streamlit, and SQLite.

## Features

- Add books with a genre, reading status, mood, and tropes
- Track reading progress by page
- Rate and review books
- Find books on your Want to Read shelf by mood and tropes
- View reading statistics

## Run locally

Open a terminal in the project folder and run:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py