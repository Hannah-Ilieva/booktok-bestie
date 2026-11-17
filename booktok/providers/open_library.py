from __future__ import annotations

from typing import Any

from booktok.providers.base import JsonProvider


class OpenLibraryProvider(JsonProvider):
    provider_name = "Open Library"
    minimum_request_gap = 1.0
    search_url = "https://openlibrary.org/search.json"

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        payload = self.request_json(
            "GET",
            self.search_url,
            params={
                "q": query.strip(),
                "limit": min(max(limit, 1), 30),
                "fields": (
                    "key,title,author_name,first_publish_year,cover_i,"
                    "first_sentence,edition_key"
                ),
            },
        )
        results = []
        for item in payload.get("docs", []):
            record_id = item.get("key")
            title = item.get("title")
            if not record_id or not title:
                continue
            if record_id.startswith("/"):
                record_id = record_id[1:]
            cover_id = item.get("cover_i")
            first_sentence = item.get("first_sentence")
            if isinstance(first_sentence, list):
                first_sentence = " ".join(str(sentence) for sentence in first_sentence[:2])
            results.append(
                {
                    "provider": "open_library",
                    "provider_record_id": record_id,
                    "title": title,
                    "authors": item.get("author_name") or [],
                    "description": first_sentence,
                    "first_publication_year": item.get("first_publish_year"),
                    "cover_url": (
                        f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                        if cover_id
                        else None
                    ),
                    "source_url": f"https://openlibrary.org/{record_id}",
                    "provider_label": "Open Library",
                }
            )
        return results
