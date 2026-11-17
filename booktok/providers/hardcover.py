from __future__ import annotations

import json
import os
from typing import Any

from booktok.providers.base import JsonProvider, ProviderError


class HardcoverProvider(JsonProvider):
    provider_name = "Hardcover"
    minimum_request_gap = 1.0
    endpoint = "https://api.hardcover.app/v1/graphql"

    def __init__(self, token: str | None = None) -> None:
        super().__init__()
        self._token = token or os.environ.get("HARDCOVER_API_TOKEN", "")

    @property
    def configured(self) -> bool:
        return bool(self._token.strip())

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        if not self.configured:
            raise ProviderError("Add HARDCOVER_API_TOKEN to .env to enable Hardcover search.")

        graphql_query = """
        query SearchBooks($query: String!, $perPage: Int!, $page: Int!) {
          search(query: $query, query_type: "book", per_page: $perPage, page: $page) {
            ids
            results
            error
          }
        }
        """
        payload = self.request_json(
            "POST",
            self.endpoint,
            json={
                "query": graphql_query,
                "variables": {
                    "query": query.strip(),
                    "perPage": min(max(limit, 1), 25),
                    "page": 1,
                },
            },
            headers={"Authorization": f"Bearer {self._token}"},
        )
        if payload.get("errors"):
            raise ProviderError("Hardcover rejected the search. Check the API token and try again.")
        search_data = (payload.get("data") or {}).get("search") or {}
        if search_data.get("error"):
            raise ProviderError("Hardcover could not complete this search.")
        raw_results = search_data.get("results") or []
        if isinstance(raw_results, str):
            try:
                raw_results = json.loads(raw_results)
            except json.JSONDecodeError:
                raw_results = []
        if isinstance(raw_results, dict):
            raw_results = raw_results.get("results") or raw_results.get("hits") or []
        if not isinstance(raw_results, list):
            raw_results = []

        ids = search_data.get("ids") or []
        results = []
        for index, item in enumerate(raw_results[:limit]):
            if not isinstance(item, dict):
                continue
            source = item.get("document") or item.get("document_data") or item
            record_id = source.get("id") or source.get("book_id")
            if not record_id and index < len(ids):
                record_id = ids[index]
            title = source.get("title")
            if not record_id or not title:
                continue
            authors = source.get("author_names") or source.get("authors") or []
            if isinstance(authors, str):
                authors = [authors]
            elif authors and isinstance(authors[0], dict):
                authors = [author.get("name", "") for author in authors]
            image = source.get("image") or source.get("cached_image") or {}
            if isinstance(image, str):
                cover_url = image
            elif isinstance(image, dict):
                cover_url = image.get("url")
            else:
                cover_url = None
            editions = source.get("editions") or []
            isbn13 = isbn10 = None
            if editions and isinstance(editions[0], dict):
                isbn13 = editions[0].get("isbn_13")
                isbn10 = editions[0].get("isbn_10")
            release_date = source.get("release_date") or source.get("publication_date") or ""
            year = int(release_date[:4]) if str(release_date)[:4].isdigit() else None
            slug = source.get("slug")
            results.append(
                {
                    "provider": "hardcover",
                    "provider_record_id": str(record_id),
                    "title": title,
                    "authors": authors,
                    "description": source.get("description"),
                    "first_publication_year": year,
                    "isbn_13": isbn13,
                    "isbn_10": isbn10,
                    "publication_year": year,
                    "page_count": source.get("pages"),
                    "cover_url": cover_url,
                    "source_url": (
                        f"https://hardcover.app/books/{slug}" if slug else "https://hardcover.app"
                    ),
                    "provider_label": "Hardcover",
                }
            )
        return results
