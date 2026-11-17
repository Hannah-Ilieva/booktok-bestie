from __future__ import annotations

from typing import Any

from booktok.catalog import upsert_provider_record
from booktok.providers.base import ProviderError
from booktok.providers.google_books import GoogleBooksProvider
from booktok.providers.hardcover import HardcoverProvider
from booktok.providers.open_library import OpenLibraryProvider


PROVIDERS = {
    "open_library": OpenLibraryProvider(),
    "google_books": GoogleBooksProvider(),
    "hardcover": HardcoverProvider(),
}


def search_provider(provider_key: str, query: str, limit: int = 20) -> list[dict[str, Any]]:
    provider = PROVIDERS.get(provider_key)
    if provider is None:
        raise ProviderError("Choose a supported book metadata provider.")
    return provider.search(query, limit=limit)


def configured_providers() -> list[str]:
    return [
        key for key, provider in PROVIDERS.items()
        if not isinstance(provider, HardcoverProvider) or provider.configured
    ]


def save_provider_record(record: dict[str, Any]) -> dict[str, Any]:
    return upsert_provider_record(record)
