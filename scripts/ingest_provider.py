import argparse

from booktok.discovery import search_provider
from booktok.catalog import upsert_provider_record
from booktok.providers.base import ProviderError


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one small, on-demand search and idempotently save its records."
    )
    parser.add_argument("--provider", choices=("open_library", "google_books", "hardcover"), required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    limit = min(max(args.limit, 1), 20)

    try:
        records = search_provider(args.provider, args.query, limit)
    except ProviderError as exc:
        raise SystemExit(str(exc)) from exc

    saved = conflicts = 0
    for record in records:
        try:
            upsert_provider_record(record)
            saved += 1
        except ValueError as exc:
            conflicts += 1
            print(f"Review needed for {record.get('title', 'untitled')!r}: {exc}")
    print(f"Fetched {len(records)} record(s); saved {saved}; flagged {conflicts} for review.")
    print("No bulk request was made. Exact provider IDs and ISBNs are deduplicated; fuzzy matches go to review.")


if __name__ == "__main__":
    main()
