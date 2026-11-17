import argparse

from booktok.classification import MIN_DESCRIPTION_LENGTH, classify_work
from booktok.db import connect


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Suggest catalog labels from sufficiently descriptive book metadata."
    )
    parser.add_argument("--limit", type=int, default=100, help="Maximum works to classify (default: 100).")
    parser.add_argument("--force", action="store_true", help="Reclassify works that already have current labels.")
    args = parser.parse_args()
    limit = min(max(args.limit, 1), 500)

    with connect() as connection:
        works = connection.execute(
            """
            SELECT w.id
            FROM works AS w
            WHERE length(btrim(COALESCE(w.description, ''))) >= %s
              AND (%s OR NOT EXISTS (
                    SELECT 1 FROM work_labels AS wl
                    WHERE wl.work_id = w.id
                      AND wl.is_current = TRUE
              ))
            ORDER BY w.id
            LIMIT %s
            """,
            (MIN_DESCRIPTION_LENGTH, args.force, limit),
        ).fetchall()

    if not works:
        print("No unclassified descriptions meet the minimum text length yet.")
        return

    suggestions = unknown = 0
    for work in works:
        count, result = classify_work(work["id"])
        suggestions += count
        if result == "unknown":
            unknown += 1
    print(f"Reviewed {len(works)} work(s); saved {suggestions} unverified suggestion(s).")
    if unknown:
        print(f"{unknown} work(s) had no strong label match and remain unknown.")


if __name__ == "__main__":
    main()
