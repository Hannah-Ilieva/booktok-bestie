import argparse

from booktok.db import connect
from booktok.embeddings import MODEL_NAME, encode_documents, model_version, text_hash, vector_literal


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or refresh local pgvector embeddings for catalog descriptions."
    )
    parser.add_argument("--limit", type=int, default=250, help="Maximum descriptions to process (default: 250).")
    parser.add_argument("--force", action="store_true", help="Re-embed even unchanged descriptions.")
    args = parser.parse_args()
    limit = min(max(args.limit, 1), 1000)

    with connect() as connection:
        has_descriptions = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM works WHERE NULLIF(btrim(description), '') IS NOT NULL)"
        ).fetchone()["exists"]
    if not has_descriptions:
        print("No catalog descriptions are available to embed yet.")
        return

    version = model_version()
    with connect() as connection:
        works = connection.execute(
            """
            SELECT w.id, w.title, w.authors, w.description,
                   e.content_hash, e.model_name, e.model_version
            FROM works AS w
            LEFT JOIN work_embeddings AS e ON e.work_id = w.id
            WHERE NULLIF(btrim(w.description), '') IS NOT NULL
              AND (%s OR e.work_id IS NULL OR e.model_name <> %s
                   OR e.model_version <> %s OR e.embedded_at < w.updated_at)
            ORDER BY (e.work_id IS NULL) DESC, w.id
            LIMIT %s
            """,
            (args.force, MODEL_NAME, version, limit),
        ).fetchall()
    if not works:
        print("All catalog description embeddings are current.")
        return

    pending = []
    already_current = []
    for work in works:
        text = f"{work['title']}\n{work['authors']}\n\n{work['description']}".strip()
        digest = text_hash(text)
        if (
            not args.force
            and work["content_hash"] == digest
            and work["model_name"] == MODEL_NAME
            and work["model_version"] == version
        ):
            already_current.append(work["id"])
            continue
        pending.append((work, text, digest))

    if not pending:
        if already_current:
            with connect() as connection:
                connection.execute(
                    "UPDATE work_embeddings SET embedded_at = NOW() WHERE work_id = ANY(%s::BIGINT[])",
                    (already_current,),
                )
        print("Catalog embeddings are already current.")
        return

    vectors = encode_documents([text for _, text, _ in pending])
    with connect() as connection:
        if already_current:
            connection.execute(
                "UPDATE work_embeddings SET embedded_at = NOW() WHERE work_id = ANY(%s::BIGINT[])",
                (already_current,),
            )
        for (work, _, digest), vector in zip(pending, vectors):
            connection.execute(
                """
                INSERT INTO work_embeddings
                    (work_id, embedding, model_name, model_version, content_hash)
                VALUES (%s, %s::VECTOR, %s, %s, %s)
                ON CONFLICT (work_id) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    model_name = EXCLUDED.model_name,
                    model_version = EXCLUDED.model_version,
                    content_hash = EXCLUDED.content_hash,
                    embedded_at = NOW()
                """,
                (work["id"], vector_literal(vector), MODEL_NAME, version, digest),
            )

    print(f"Created or refreshed {len(pending)} local embedding(s) with {MODEL_NAME} ({version}).")


if __name__ == "__main__":
    main()
