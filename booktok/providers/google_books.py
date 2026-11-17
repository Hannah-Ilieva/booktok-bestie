from __future__ import annotations

import os
from typing import Any

from booktok.providers.base import JsonProvider


class GoogleBooksProvider(JsonProvider):
    provider_name = "Google Books"
    minimum_request_gap = 0.25
    search_url = "https://www.googleapis.com/books/v1/volumes"

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "q": query.strip(),
            "maxResults": min(max(limit, 1), 40),
            "orderBy": "relevance",
            "projection": "full",
        }
        api_key = os.environ.get("GOOGLE_BOOKS_API_KEY")
        if api_key:
            params["key"] = api_key
        payload = self.request_json("GET", self.search_url, params=params)

        results = []
        for item in payload.get("items", []):
            info = item.get("volumeInfo") or {}
            title = info.get("title")
            record_id = item.get("id")
            if not title or not record_id:
                continue
            identifiers = {
                entry.get("type"): entry.get("identifier")
                for entry in info.get("industryIdentifiers", [])
                if entry.get("type") and entry.get("identifier")
            }
            image_links = info.get("imageLinks") or {}
            cover = image_links.get("thumbnail") or image_links.get("smallThumbnail")
            if cover and cover.startswith("http://"):
                cover = "https://" + cover[len("http://") :]
            published_date = info.get("publishedDate") or ""
            year = None
            if len(published_date) >= 4 and published_date[:4].isdigit():
                year = int(published_date[:4])
            results.append(
                {
                    "provider": "google_books",
                    "provider_record_id": record_id,
                    "title": title,
                    "authors": info.get("authors") or [],
                    "description": info.get("description"),
                    "first_publication_year": year,
                    "isbn_13": identifiers.get("ISBN_13"),
                    "isbn_10": identifiers.get("ISBN_10"),
                    "publisher": info.get("publisher"),
                    "publication_year": year,
                    "page_count": info.get("pageCount"),
                    "language_code": info.get("language"),
                    "format": info.get("printType"),
                    "cover_url": cover,
                    "source_url": info.get("infoLink") or item.get("selfLink"),
                    "provider_label": "Google Books",
                }
            )
        return results
