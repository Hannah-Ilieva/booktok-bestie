from __future__ import annotations

import re
import unicodedata
from typing import Any

from psycopg.types.json import Jsonb

from booktok.db import connect


class CatalogConflict(ValueError):
    """Raised when exact identifiers point to incompatible catalog records."""


def normalize_title(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text.casefold()))


def normalize_isbn(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"[^0-9Xx]", "", value).upper()
    return normalized or None


def _nonempty(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _find_identifier_matches(connection, isbn_13: str | None, isbn_10: str | None):
    rows = connection.execute(
        """
        SELECT id, work_id, isbn_13, isbn_10
        FROM editions
        WHERE (%s IS NOT NULL AND isbn_13 = %s)
           OR (%s IS NOT NULL AND isbn_10 = %s)
        """,
        (isbn_13, isbn_13, isbn_10, isbn_10),
    ).fetchall()
    unique_rows = {row["id"]: row for row in rows}
    if len(unique_rows) > 1:
        works = {row["work_id"] for row in unique_rows.values()}
        if len(works) > 1:
            raise CatalogConflict(
                "This record's ISBN-10 and ISBN-13 point to different works. "
                "Nothing was merged; review the identifiers before adding it."
            )
        raise CatalogConflict(
            "This record's ISBNs point to two editions of the same work. "
            "Choose an edition during review before adding it."
        )
    return next(iter(unique_rows.values()), None)


def _upsert_edition(connection, work_id: int, record: dict[str, Any], known_edition_id=None):
    fields = {
        "isbn_13": normalize_isbn(record.get("isbn_13")),
        "isbn_10": normalize_isbn(record.get("isbn_10")),
        "publisher": _nonempty(record.get("publisher")),
        "publication_year": record.get("publication_year"),
        "publication_date": record.get("publication_date"),
        "format": _nonempty(record.get("format")),
        "language_code": _nonempty(record.get("language_code")),
        "page_count": record.get("page_count"),
        "cover_url": _nonempty(record.get("cover_url")),
    }
    if not any(fields.values()) and known_edition_id is None:
        return None

    matched = _find_identifier_matches(connection, fields["isbn_13"], fields["isbn_10"])
    if matched:
        if matched["work_id"] != work_id:
            return matched["id"], matched["work_id"]
        known_edition_id = matched["id"]

    if known_edition_id is None:
        row = connection.execute(
            """
            INSERT INTO editions
                (work_id, isbn_13, isbn_10, publisher, publication_year,
                 publication_date, format, language_code, page_count, cover_url)
            VALUES
                (%(work_id)s, %(isbn_13)s, %(isbn_10)s, %(publisher)s,
                 %(publication_year)s, %(publication_date)s, %(format)s,
                 %(language_code)s, %(page_count)s, %(cover_url)s)
            RETURNING id
            """,
            {"work_id": work_id, **fields},
        ).fetchone()
        return row["id"], work_id

    connection.execute(
        """
        UPDATE editions
        SET isbn_13 = COALESCE(isbn_13, %(isbn_13)s),
            isbn_10 = COALESCE(isbn_10, %(isbn_10)s),
            publisher = COALESCE(NULLIF(%(publisher)s, ''), publisher),
            publication_year = COALESCE(publication_year, %(publication_year)s),
            publication_date = COALESCE(publication_date, %(publication_date)s),
            format = COALESCE(NULLIF(%(format)s, ''), format),
            language_code = COALESCE(NULLIF(%(language_code)s, ''), language_code),
            page_count = COALESCE(page_count, %(page_count)s),
            cover_url = COALESCE(NULLIF(%(cover_url)s, ''), cover_url),
            updated_at = NOW()
        WHERE id = %(id)s
        """,
        {"id": known_edition_id, **fields},
    )
    return known_edition_id, work_id


def _queue_fuzzy_reviews(connection, work_id: int, title: str) -> None:
    normalized = normalize_title(title)
    if len(normalized) < 4:
        return
    candidates = connection.execute(
        """
        SELECT id, title, similarity(normalized_title, %s)::NUMERIC(4, 3) AS score
        FROM works
        WHERE id <> %s AND similarity(normalized_title, %s) >= 0.55
        ORDER BY similarity(normalized_title, %s) DESC
        LIMIT 8
        """,
        (normalized, work_id, normalized, normalized),
    ).fetchall()
    for candidate in candidates:
        connection.execute(
            """
            INSERT INTO catalog_match_reviews
                (incoming_work_id, candidate_work_id, incoming_title,
                 candidate_title, similarity_score)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (work_id, candidate["id"], title, candidate["title"], candidate["score"]),
        )


def upsert_provider_record(record: dict[str, Any]) -> dict[str, Any]:
    provider = record["provider"]
    provider_id = str(record["provider_record_id"]).strip()
    title = str(record.get("title") or "").strip()
    authors = record.get("authors") or []
    if not provider_id or not title:
        raise ValueError("A provider record needs both an identifier and a title.")
    if provider not in {"open_library", "google_books", "hardcover"}:
        raise ValueError(f"Unsupported provider: {provider}")

    normalized = normalize_title(title)
    author_text = ", ".join(str(author).strip() for author in authors if str(author).strip())
    description = _nonempty(record.get("description"))
    created = False

    with connect() as connection:
        source = connection.execute(
            """
            SELECT work_id, edition_id FROM source_records
            WHERE provider = %s AND provider_record_id = %s
            """,
            (provider, provider_id),
        ).fetchone()

        matched_edition = None
        if source:
            work_id = source["work_id"]
            edition_id = source["edition_id"]
            if work_id is None and edition_id is not None:
                linked_work = connection.execute(
                    "SELECT work_id FROM editions WHERE id = %s", (edition_id,)
                ).fetchone()
                work_id = linked_work["work_id"] if linked_work else None
            if work_id is None:
                raise CatalogConflict("This provider record is not linked to a catalog work.")
            exact_edition = _find_identifier_matches(
                connection,
                normalize_isbn(record.get("isbn_13")),
                normalize_isbn(record.get("isbn_10")),
            )
            if exact_edition and exact_edition["work_id"] != work_id:
                raise CatalogConflict(
                    "This provider identifier and ISBN point to different works. "
                    "Nothing was merged; review the record first."
                )
        else:
            matched_edition = _find_identifier_matches(
                connection,
                normalize_isbn(record.get("isbn_13")),
                normalize_isbn(record.get("isbn_10")),
            )
            if matched_edition:
                work_id = matched_edition["work_id"]
                edition_id = matched_edition["id"]
            else:
                work = connection.execute(
                    """
                    INSERT INTO works (title, normalized_title, authors, description,
                                       first_publication_year)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        title,
                        normalized,
                        author_text,
                        description,
                        record.get("first_publication_year"),
                    ),
                ).fetchone()
                work_id = work["id"]
                edition_id = None
                created = True

        connection.execute(
            """
            UPDATE works
            SET title = COALESCE(NULLIF(%s, ''), title),
                normalized_title = COALESCE(NULLIF(%s, ''), normalized_title),
                authors = COALESCE(NULLIF(%s, ''), authors),
                description = COALESCE(NULLIF(%s, ''), description),
                first_publication_year = COALESCE(first_publication_year, %s),
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                title,
                normalized,
                author_text,
                description,
                record.get("first_publication_year"),
                work_id,
            ),
        )

        edition_result = _upsert_edition(connection, work_id, record, edition_id)
        if edition_result:
            edition_id, edition_work_id = edition_result
            if edition_work_id != work_id:
                work_id = edition_work_id

        connection.execute(
            """
            INSERT INTO source_records
                (provider, provider_record_id, work_id, edition_id, source_url)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (provider, provider_record_id) DO UPDATE SET
                work_id = EXCLUDED.work_id,
                edition_id = COALESCE(EXCLUDED.edition_id, source_records.edition_id),
                source_url = COALESCE(EXCLUDED.source_url, source_records.source_url),
                last_seen_at = NOW()
            """,
            (provider, provider_id, work_id, edition_id, record.get("source_url")),
        )

        if created:
            _queue_fuzzy_reviews(connection, work_id, title)

        return {"work_id": work_id, "edition_id": edition_id, "created": created}


def list_taxonomy(label_type: str | None = None, active_only: bool = True) -> list[dict[str, Any]]:
    with connect() as connection:
        return connection.execute(
            """
            SELECT id, label_type, label_key, display_name, description,
                   spice_level, is_active
            FROM label_taxonomy
            WHERE (%s IS NULL OR label_type = %s)
              AND (%s = FALSE OR is_active = TRUE)
            ORDER BY label_type, spice_level NULLS FIRST, display_name
            """,
            (label_type, label_type, active_only),
        ).fetchall()


def add_or_update_taxonomy(
    label_type: str,
    display_name: str,
    description: str = "",
    spice_level: int | None = None,
    label_id: int | None = None,
) -> None:
    display_name = display_name.strip()
    if not display_name:
        raise ValueError("A label needs a display name.")
    if label_type not in {"genre", "trope", "theme", "spice"}:
        raise ValueError("Choose genre, trope, theme, or spice.")
    if label_type == "spice" and spice_level not in {1, 2, 3, 4, 5}:
        raise ValueError("Spice levels range from 1 to 5.")
    if label_type != "spice":
        spice_level = None

    key = re.sub(r"[^a-z0-9]+", "-", normalize_title(display_name)).strip("-")
    with connect() as connection:
        if label_id is None:
            connection.execute(
                """
                INSERT INTO label_taxonomy
                    (label_type, label_key, display_name, description, spice_level)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (label_type, label_key) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    description = EXCLUDED.description,
                    spice_level = EXCLUDED.spice_level,
                    is_active = TRUE,
                    updated_at = NOW()
                """,
                (label_type, key, display_name, description.strip(), spice_level),
            )
        else:
            connection.execute(
                """
                UPDATE label_taxonomy
                SET display_name = %s, description = %s,
                    spice_level = %s, updated_at = NOW()
                WHERE id = %s AND label_type = %s
                """,
                (display_name, description.strip(), spice_level, label_id, label_type),
            )


def set_taxonomy_active(label_id: int, active: bool) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE label_taxonomy SET is_active = %s, updated_at = NOW() WHERE id = %s",
            (active, label_id),
        )


def work_labels(work_id: int, current_only: bool = True) -> list[dict[str, Any]]:
    with connect() as connection:
        return connection.execute(
            """
            SELECT wl.id AS assignment_id, wl.label_id, lt.label_type,
                   lt.display_name, lt.description, lt.spice_level,
                   wl.confidence, wl.model_name, wl.model_version,
                   wl.human_verified, wl.is_current
            FROM work_labels AS wl
            JOIN label_taxonomy AS lt ON lt.id = wl.label_id
            WHERE wl.work_id = %s AND (%s = FALSE OR wl.is_current = TRUE)
            ORDER BY lt.label_type, lt.display_name
            """,
            (work_id, current_only),
        ).fetchall()


def classification_queue(limit: int = 100) -> list[dict[str, Any]]:
    with connect() as connection:
        return connection.execute(
            """
            SELECT w.id, w.title, w.authors, w.description,
                   COUNT(wl.id) FILTER (
                       WHERE wl.is_current = TRUE AND wl.human_verified = FALSE
                   ) AS unverified_labels,
                   COUNT(wl.id) FILTER (
                       WHERE wl.is_current = TRUE AND wl.human_verified = TRUE
                   ) AS verified_labels
            FROM works AS w
            LEFT JOIN work_labels AS wl ON wl.work_id = w.id
            GROUP BY w.id
            ORDER BY (w.description IS NOT NULL) DESC,
                     unverified_labels DESC, w.title
            LIMIT %s
            """,
            (min(max(limit, 1), 300),),
        ).fetchall()


def replace_work_label_type(
    work_id: int,
    label_type: str,
    selected_label_ids: list[int],
    note: str = "",
) -> None:
    if label_type not in {"genre", "trope", "theme", "spice"}:
        raise ValueError("Unknown label category.")
    selected = set(selected_label_ids)
    if label_type == "spice" and len(selected) > 1:
        raise ValueError("Choose at most one spice level for a book.")

    with connect() as connection:
        valid = connection.execute(
            """
            SELECT id FROM label_taxonomy
            WHERE id = ANY(%s::BIGINT[]) AND label_type = %s AND is_active = TRUE
            """,
            (list(selected), label_type),
        ).fetchall()
        if {row["id"] for row in valid} != selected:
            raise ValueError("One or more selected labels are no longer active.")

        current = connection.execute(
            """
            SELECT wl.id, wl.label_id, wl.confidence, wl.model_name,
                   wl.model_version, wl.human_verified
            FROM work_labels AS wl
            JOIN label_taxonomy AS lt ON lt.id = wl.label_id
            WHERE wl.work_id = %s AND lt.label_type = %s AND wl.is_current = TRUE
            FOR UPDATE OF wl
            """,
            (work_id, label_type),
        ).fetchall()
        current_by_label: dict[int, list[dict[str, Any]]] = {}
        for row in current:
            current_by_label.setdefault(row["label_id"], []).append(row)

        removed = sorted(label_id for label_id in current_by_label if label_id not in selected)
        added = sorted(label_id for label_id in selected if label_id not in current_by_label)
        changes = [(label_id, None) for label_id in removed]
        changes.extend((None, label_id) for label_id in added)

        for from_id, to_id in changes:
            from_assignment = current_by_label.get(from_id, [{}])[0] if from_id else {}
            connection.execute(
                """
                INSERT INTO work_label_corrections
                    (work_id, from_label_id, to_label_id, note,
                     from_confidence, from_model_name, from_model_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    work_id,
                    from_id,
                    to_id,
                    note.strip() or None,
                    from_assignment.get("confidence"),
                    from_assignment.get("model_name"),
                    from_assignment.get("model_version"),
                ),
            )

        for label_id in removed:
            connection.execute(
                """
                UPDATE work_labels SET is_current = FALSE
                WHERE work_id = %s AND label_id = %s AND is_current = TRUE
                """,
                (work_id, label_id),
            )

        for label_id in selected:
            existing = current_by_label.get(label_id, [])
            if existing:
                connection.execute(
                    """
                    UPDATE work_labels
                    SET human_verified = TRUE, is_current = TRUE
                    WHERE work_id = %s AND label_id = %s AND is_current = TRUE
                    """,
                    (work_id, label_id),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO work_labels
                        (work_id, label_id, model_name, model_version,
                         human_verified, is_current)
                    VALUES (%s, %s, 'human', 'manual', TRUE, TRUE)
                    ON CONFLICT (work_id, label_id, model_name, model_version)
                    DO UPDATE SET human_verified = TRUE, is_current = TRUE
                    """,
                    (work_id, label_id),
                )


def catalog_search(
    query: str = "",
    query_vector: list[float] | None = None,
    label_ids: list[int] | None = None,
    spice_min: int | None = None,
    spice_max: int | None = None,
    limit: int = 40,
    exclude_shelf: bool = False,
) -> list[dict[str, Any]]:
    vector_literal = None
    if query_vector is not None:
        if len(query_vector) != 384:
            raise ValueError("The query embedding must contain 384 values.")
        vector_literal = "[" + ",".join(f"{float(value):.8g}" for value in query_vector) + "]"
    pattern = f"%{query.strip()}%"
    selected_labels = label_ids or []
    if vector_literal:
        score_sql = "CASE WHEN we.embedding IS NULL THEN NULL::DOUBLE PRECISION ELSE 1 - (we.embedding <=> %s::VECTOR) END AS semantic_score"
        search_sql = """(we.embedding IS NOT NULL OR (
            %s = '' OR w.title ILIKE %s OR w.authors ILIKE %s
            OR COALESCE(w.description, '') ILIKE %s
            OR to_tsvector('simple', concat_ws(' ', w.title, w.authors, w.description))
               @@ websearch_to_tsquery('simple', %s)))"""
        order_sql = "we.embedding <=> %s::VECTOR NULLS LAST, w.title"
        params = [vector_literal, query.strip(), pattern, pattern, pattern, query.strip()]
    else:
        score_sql = "NULL::DOUBLE PRECISION AS semantic_score"
        search_sql = """(%s = '' OR w.title ILIKE %s OR w.authors ILIKE %s
            OR COALESCE(w.description, '') ILIKE %s
            OR to_tsvector('simple', concat_ws(' ', w.title, w.authors, w.description))
               @@ websearch_to_tsquery('simple', %s))"""
        order_sql = "w.title"
        params = [query.strip(), pattern, pattern, pattern, query.strip()]

    params.extend(
        [
            selected_labels,
            selected_labels,
            selected_labels,
            spice_min,
            spice_min,
            spice_max,
            exclude_shelf,
        ]
    )
    if vector_literal:
        params.append(vector_literal)
    params.append(min(max(limit, 1), 100))

    with connect() as connection:
        return connection.execute(
            f"""
            SELECT
                w.id, w.title, w.authors, w.description,
                w.first_publication_year,
                cover.cover_url,
                COALESCE(labels.items, '[]'::JSONB) AS labels,
                COALESCE(sources.items, '[]'::JSONB) AS sources,
                {score_sql}
            FROM works AS w
            LEFT JOIN work_embeddings AS we ON we.work_id = w.id
            LEFT JOIN LATERAL (
                SELECT e.cover_url
                FROM editions AS e
                WHERE e.work_id = w.id AND e.cover_url IS NOT NULL
                ORDER BY e.updated_at DESC
                LIMIT 1
            ) AS cover ON TRUE
            LEFT JOIN LATERAL (
                SELECT jsonb_agg(jsonb_build_object(
                    'id', lt.id, 'type', lt.label_type, 'name', lt.display_name,
                    'spice_level', lt.spice_level, 'confidence', wl.confidence,
                    'model_name', wl.model_name, 'model_version', wl.model_version,
                    'human_verified', wl.human_verified
                ) ORDER BY lt.label_type, lt.display_name) AS items
                FROM work_labels AS wl
                JOIN label_taxonomy AS lt ON lt.id = wl.label_id
                WHERE wl.work_id = w.id AND lt.is_active = TRUE AND wl.is_current = TRUE
            ) AS labels ON TRUE
            LEFT JOIN LATERAL (
                SELECT jsonb_agg(jsonb_build_object(
                    'provider', sr.provider, 'url', sr.source_url,
                    'record_id', sr.provider_record_id
                ) ORDER BY sr.provider) AS items
                FROM source_records AS sr
                WHERE sr.work_id = w.id
            ) AS sources ON TRUE
            WHERE {search_sql}
              AND (cardinality(%s::BIGINT[]) = 0 OR
                   (SELECT count(DISTINCT wl.label_id)
                    FROM work_labels AS wl
                    WHERE wl.work_id = w.id AND wl.is_current = TRUE
                      AND wl.label_id = ANY(%s::BIGINT[]))
                    = cardinality(%s::BIGINT[]))
              AND (%s::INTEGER IS NULL OR EXISTS (
                    SELECT 1 FROM work_labels AS wl
                    JOIN label_taxonomy AS lt ON lt.id = wl.label_id
                    WHERE wl.work_id = w.id AND wl.is_current = TRUE
                      AND lt.label_type = 'spice'
                      AND lt.spice_level BETWEEN %s AND %s))
              AND (%s = FALSE OR NOT EXISTS (
                    SELECT 1 FROM reading_shelf AS rs WHERE rs.work_id = w.id))
            ORDER BY {order_sql}
            LIMIT %s
            """,
            tuple(params),
        ).fetchall()


def shelf_books(search: str = "", status: str | None = None) -> list[dict[str, Any]]:
    pattern = f"%{search.strip()}%"
    with connect() as connection:
        return connection.execute(
            """
            SELECT s.id AS shelf_id, s.work_id, s.edition_id, s.genre, s.status,
                   s.total_pages, s.current_page, s.rating, s.review, s.mood,
                   s.tropes, s.added_at, w.title, w.authors, w.description,
                   cover.cover_url
            FROM reading_shelf AS s
            JOIN works AS w ON w.id = s.work_id
            LEFT JOIN LATERAL (
                SELECT e.cover_url FROM editions AS e
                WHERE e.work_id = w.id AND e.cover_url IS NOT NULL
                ORDER BY e.updated_at DESC LIMIT 1
            ) AS cover ON TRUE
            WHERE (%s = '' OR w.title ILIKE %s OR w.authors ILIKE %s)
              AND (%s IS NULL OR s.status = %s)
            ORDER BY s.added_at DESC, s.id DESC
            """,
            (search.strip(), pattern, pattern, status, status),
        ).fetchall()


def add_to_shelf(work_id: int, status: str = "Want to Read") -> bool:
    with connect() as connection:
        existing = connection.execute(
            "SELECT id FROM reading_shelf WHERE work_id = %s LIMIT 1", (work_id,)
        ).fetchone()
        if existing:
            return False
        row = connection.execute(
            """
            INSERT INTO reading_shelf (work_id, status)
            VALUES (%s, %s)
            RETURNING id
            """,
            (work_id, status),
        ).fetchone()
        if row:
            log_interaction(connection, work_id, "click", details={"source": "shelf_button"})
            log_interaction(connection, work_id, "shelf_add")
            return True
        return False


def create_manual_work(
    title: str,
    authors: str,
    description: str = "",
    genre: str = "",
    status: str = "Want to Read",
    total_pages: int | None = None,
) -> int:
    title = title.strip()
    authors = authors.strip()
    if not title:
        raise ValueError("Enter a book title.")
    with connect() as connection:
        work = connection.execute(
            """
            INSERT INTO works (title, normalized_title, authors, description)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (title, normalize_title(title), authors, description.strip() or None),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO reading_shelf (work_id, genre, status, total_pages)
            VALUES (%s, %s, %s, %s)
            """,
            (work["id"], genre.strip() or None, status, total_pages or None),
        )
        log_interaction(connection, work["id"], "shelf_add", details={"source": "manual"})
        return work["id"]


def update_shelf_entry(
    shelf_id: int,
    status: str,
    current_page: int,
    total_pages: int | None,
    rating: float | None,
    review: str,
) -> None:
    if status not in {"Want to Read", "Currently Reading", "Finished", "DNF"}:
        raise ValueError("Choose a valid reading status.")
    if current_page < 0 or (total_pages is not None and total_pages < 1):
        raise ValueError("Page counts must be positive, and progress cannot be negative.")
    if total_pages is not None and current_page > total_pages:
        raise ValueError("Current page cannot exceed the total page count.")
    if rating is not None and not 0 <= rating <= 5:
        raise ValueError("Ratings range from 0 to 5.")

    with connect() as connection:
        row = connection.execute(
            "SELECT work_id, rating FROM reading_shelf WHERE id = %s", (shelf_id,)
        ).fetchone()
        if not row:
            raise ValueError("That shelf entry no longer exists.")
        connection.execute(
            """
            UPDATE reading_shelf
            SET status = %s, current_page = %s, total_pages = %s,
                rating = %s, review = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (status, current_page, total_pages, rating, review, shelf_id),
        )
        if rating is not None and rating != row["rating"]:
            log_interaction(connection, row["work_id"], "rating", rating=float(rating))


def remove_from_shelf(shelf_id: int) -> None:
    with connect() as connection:
        connection.execute("DELETE FROM reading_shelf WHERE id = %s", (shelf_id,))


def reading_stats() -> dict[str, Any]:
    with connect() as connection:
        return connection.execute(
            """
            SELECT COUNT(*) AS total_books,
                COUNT(*) FILTER (WHERE status = 'Finished') AS finished_books,
                COUNT(*) FILTER (WHERE status = 'Currently Reading') AS currently_reading,
                COALESCE(SUM(CASE WHEN status = 'Finished' AND total_pages IS NOT NULL
                                  THEN total_pages ELSE current_page END), 0) AS pages_read,
                ROUND(AVG(rating), 1) AS average_rating
            FROM reading_shelf
            """
        ).fetchone()


def reading_stat_breakdowns() -> dict[str, list[dict[str, Any]]]:
    with connect() as connection:
        statuses = connection.execute(
            "SELECT status AS label, count(*) AS total FROM reading_shelf GROUP BY status ORDER BY status"
        ).fetchall()
        genres = connection.execute(
            """
            SELECT COALESCE(NULLIF(btrim(genre), ''), 'Not listed') AS label,
                   count(*) AS total
            FROM reading_shelf GROUP BY COALESCE(NULLIF(btrim(genre), ''), 'Not listed')
            ORDER BY total DESC, label LIMIT 12
            """
        ).fetchall()
        ratings = connection.execute(
            """
            SELECT rating::TEXT AS label, count(*) AS total
            FROM reading_shelf WHERE rating IS NOT NULL
            GROUP BY rating ORDER BY rating
            """
        ).fetchall()
    return {"statuses": statuses, "genres": genres, "ratings": ratings}


def catalog_activity_stats() -> dict[str, int]:
    with connect() as connection:
        return connection.execute(
            """
            SELECT
                (SELECT count(*) FROM works) AS catalog_works,
                (SELECT count(*) FROM work_embeddings) AS embedded_works,
                (SELECT count(*) FROM work_labels
                 WHERE is_current = TRUE AND human_verified = FALSE) AS unverified_labels,
                (SELECT count(*) FROM work_label_corrections) AS label_corrections,
                (SELECT count(*) FROM catalog_match_reviews
                 WHERE status = 'pending') AS pending_match_reviews,
                (SELECT count(*) FROM interaction_events) AS interactions
            """
        ).fetchone()


def log_interaction(
    connection,
    work_id: int,
    event_type: str,
    edition_id: int | None = None,
    rating: float | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO interaction_events
            (work_id, edition_id, event_type, rating, details)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (work_id, edition_id, event_type, rating, Jsonb(details or {})),
    )


def log_impressions(work_ids: list[int], query: str, source: str = "discover") -> None:
    if not work_ids:
        return
    with connect() as connection:
        for work_id in dict.fromkeys(work_ids):
            log_interaction(
                connection,
                work_id,
                "impression",
                details={"query": query[:500], "source": source},
            )


def list_pending_match_reviews(limit: int = 100) -> list[dict[str, Any]]:
    with connect() as connection:
        return connection.execute(
            """
            SELECT id, incoming_work_id, candidate_work_id, incoming_title,
                   candidate_title, similarity_score, created_at
            FROM catalog_match_reviews
            WHERE status = 'pending'
            ORDER BY similarity_score DESC, created_at
            LIMIT %s
            """,
            (min(max(limit, 1), 500),),
        ).fetchall()


def label_history_preferences() -> dict[int, float]:
    with connect() as connection:
        rows = connection.execute(
            """
            WITH eligible_labels AS (
                SELECT DISTINCT work_id, label_id
                FROM work_labels
                WHERE is_current = TRUE
                  AND (human_verified = TRUE OR model_name = 'human')
            ), shelf_signals AS (
                SELECT el.label_id,
                       SUM(CASE
                       WHEN s.rating >= 4.0 THEN 1.0
                       WHEN s.rating IS NOT NULL AND s.rating < 3.0 THEN -0.75
                       WHEN s.status = 'Finished' THEN 0.45
                       ELSE 0.0 END) AS signal
                FROM eligible_labels AS el
                JOIN reading_shelf AS s ON s.work_id = el.work_id
                GROUP BY el.label_id
            ), interaction_signals AS (
                SELECT el.label_id,
                       SUM(CASE
                       WHEN e.event_type IN ('save', 'shelf_add') THEN 0.6
                       WHEN e.event_type = 'click' THEN 0.2
                       WHEN e.event_type = 'skip' THEN -0.5
                       ELSE 0.0 END) AS signal
                FROM eligible_labels AS el
                JOIN interaction_events AS e ON e.work_id = el.work_id
                GROUP BY el.label_id
            ), all_labels AS (
                SELECT DISTINCT label_id FROM eligible_labels
            )
            SELECT all_labels.label_id,
                   COALESCE(shelf_signals.signal, 0) AS shelf_signal,
                   COALESCE(interaction_signals.signal, 0) AS interaction_signal
            FROM all_labels
            LEFT JOIN shelf_signals USING (label_id)
            LEFT JOIN interaction_signals USING (label_id)
            """
        ).fetchall()
    result = {}
    for row in rows:
        strength = float(row["shelf_signal"] or 0) + float(row["interaction_signal"] or 0)
        result[row["label_id"]] = max(-1.0, min(1.0, strength / 3.0))
    return result


def label_names(label_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not label_ids:
        return {}
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, display_name, label_type, spice_level
            FROM label_taxonomy WHERE id = ANY(%s::BIGINT[])
            """,
            (label_ids,),
        ).fetchall()
    return {row["id"]: row for row in rows}


def mark_match_review(review_id: int, status: str, note: str = "") -> None:
    if status not in {"kept_separate", "dismissed"}:
        raise ValueError("Choose whether to keep these records separate or dismiss the review.")
    with connect() as connection:
        connection.execute(
            """
            UPDATE catalog_match_reviews
            SET status = %s, decision_note = %s, resolved_at = NOW()
            WHERE id = %s AND status = 'pending'
            """,
            (status, note.strip() or None, review_id),
        )


def merge_review_candidate(review_id: int) -> None:
    with connect() as connection:
        review = connection.execute(
            """
            SELECT incoming_work_id, candidate_work_id
            FROM catalog_match_reviews WHERE id = %s AND status = 'pending'
            FOR UPDATE
            """,
            (review_id,),
        ).fetchone()
        if not review or not review["incoming_work_id"] or not review["candidate_work_id"]:
            raise ValueError("This review no longer has two catalog records to merge.")

        incoming_id = review["incoming_work_id"]
        target_id = review["candidate_work_id"]
        connection.execute(
            "UPDATE catalog_match_reviews SET status = 'merged', resolved_at = NOW() WHERE id = %s",
            (review_id,),
        )

        incoming_editions = connection.execute(
            "SELECT id, isbn_13, isbn_10 FROM editions WHERE work_id = %s",
            (incoming_id,),
        ).fetchall()
        for edition in incoming_editions:
            matches = connection.execute(
                """
                SELECT id FROM editions
                WHERE work_id = %s AND (
                    (%s IS NOT NULL AND isbn_13 = %s)
                    OR (%s IS NOT NULL AND isbn_10 = %s)
                )
                """,
                (
                    target_id,
                    edition["isbn_13"],
                    edition["isbn_13"],
                    edition["isbn_10"],
                    edition["isbn_10"],
                ),
            ).fetchall()
            if len({row["id"] for row in matches}) > 1:
                raise CatalogConflict(
                    "This merge would combine ISBNs attached to separate editions. "
                    "The merge was canceled; review the edition data first."
                )
            same = matches[0] if matches else None
            if same:
                connection.execute(
                    "UPDATE source_records SET edition_id = %s WHERE edition_id = %s",
                    (same["id"], edition["id"]),
                )
                connection.execute(
                    "UPDATE reading_shelf SET edition_id = %s WHERE edition_id = %s",
                    (same["id"], edition["id"]),
                )
                connection.execute(
                    "UPDATE interaction_events SET edition_id = %s WHERE edition_id = %s",
                    (same["id"], edition["id"]),
                )
                connection.execute("DELETE FROM editions WHERE id = %s", (edition["id"],))
            else:
                connection.execute(
                    "UPDATE editions SET work_id = %s WHERE id = %s",
                    (target_id, edition["id"]),
                )

        connection.execute("UPDATE source_records SET work_id = %s WHERE work_id = %s", (target_id, incoming_id))
        connection.execute("UPDATE interaction_events SET work_id = %s WHERE work_id = %s", (target_id, incoming_id))
        connection.execute("UPDATE reading_shelf SET work_id = %s WHERE work_id = %s", (target_id, incoming_id))
        connection.execute("UPDATE work_label_corrections SET work_id = %s WHERE work_id = %s", (target_id, incoming_id))
        connection.execute(
            """
            INSERT INTO work_labels
                (work_id, label_id, confidence, model_name, model_version, human_verified)
            SELECT %s, label_id, confidence, model_name, model_version, human_verified
            FROM work_labels WHERE work_id = %s
            ON CONFLICT DO NOTHING
            """,
            (target_id, incoming_id),
        )
        connection.execute("DELETE FROM work_labels WHERE work_id = %s", (incoming_id,))
        connection.execute(
            """
            INSERT INTO work_embeddings (work_id, embedding, model_name, model_version, content_hash)
            SELECT %s, embedding, model_name, model_version, content_hash
            FROM work_embeddings WHERE work_id = %s
            ON CONFLICT (work_id) DO NOTHING
            """,
            (target_id, incoming_id),
        )
        connection.execute("DELETE FROM work_embeddings WHERE work_id = %s", (incoming_id,))
        connection.execute("DELETE FROM works WHERE id = %s", (incoming_id,))
