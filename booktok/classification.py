from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from booktok.db import connect
from booktok.embeddings import EmbeddingUnavailable, MODEL_NAME, encode_documents, model_version


MIN_DESCRIPTION_LENGTH = 120
MODEL_SIMILARITY_THRESHOLD = 0.42
MODEL_NAME_FOR_RULES = "booktok-explicit-spice-cues"
MODEL_VERSION_FOR_RULES = "1.0"

SPICE_CUES = (
    (5, re.compile(r"\b(?:very spicy|highly explicit|explicit sexual content|graphic sex|erotica)\b", re.I), 0.92),
    (4, re.compile(r"\b(?:steamy|spicy|high heat|high spice)\b", re.I), 0.82),
    (3, re.compile(r"\b(?:open[- ]door|on[- ]page intimacy|moderate spice)\b", re.I), 0.78),
    (2, re.compile(r"\b(?:mild spice|low heat|lightly steamy)\b", re.I), 0.72),
    (1, re.compile(r"\b(?:closed[- ]door|fade[- ]to[- ]black|no explicit scenes)\b", re.I), 0.9),
)
NEGATED_SPICE_CUE = re.compile(r"\b(?:not|no|without|never)\s+(?:(?:very|highly|really)\s+)?$", re.I)


def _normalized_score(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


@lru_cache(maxsize=4)
def _label_vectors(texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(vector) for vector in encode_documents(texts))


def predict_labels(
    description: str,
    taxonomy: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    text = " ".join((description or "").split())
    if len(text) < MIN_DESCRIPTION_LENGTH or len(text.split()) < 20:
        return []

    predictions: list[dict[str, Any]] = []
    for level, cue, confidence in SPICE_CUES:
        match = cue.search(text)
        if match and not NEGATED_SPICE_CUE.search(text[max(0, match.start() - 24) : match.start()]):
            spice_label = next(
                (
                    label for label in taxonomy
                    if label["label_type"] == "spice" and label["spice_level"] == level
                ),
                None,
            )
            if spice_label:
                predictions.append(
                    {
                        "label_id": spice_label["id"],
                        "label_type": "spice",
                        "confidence": confidence,
                        "model_name": MODEL_NAME_FOR_RULES,
                        "model_version": MODEL_VERSION_FOR_RULES,
                    }
                )
            break

    semantic_labels = [
        label for label in taxonomy
        if label["label_type"] in {"genre", "trope", "theme"} and label.get("description")
    ]
    if not semantic_labels:
        return predictions

    label_texts = tuple(
        f"{label['label_type']}: {label['display_name']}. {label['description']}"
        for label in semantic_labels
    )
    try:
        source_vector = encode_documents([text])[0]
        label_vectors = _label_vectors(label_texts)
        version = model_version()
    except EmbeddingUnavailable:
        return predictions

    scores_by_type: dict[str, list[tuple[float, dict[str, Any]]]] = {}
    for label, vector in zip(semantic_labels, label_vectors):
        score = sum(left * right for left, right in zip(source_vector, vector))
        scores_by_type.setdefault(label["label_type"], []).append((score, label))

    for label_type, scored in scores_by_type.items():
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = 0
        for score, label in scored:
            if score < MODEL_SIMILARITY_THRESHOLD or selected >= 3:
                break
            predictions.append(
                {
                    "label_id": label["id"],
                    "label_type": label_type,
                    "confidence": _normalized_score(score),
                    "model_name": MODEL_NAME,
                    "model_version": version,
                }
            )
            selected += 1
    return predictions


def save_predictions(work_id: int, predictions: list[dict[str, Any]]) -> int:
    with connect() as connection:
        connection.execute(
            """
            UPDATE work_labels
            SET is_current = FALSE
            WHERE work_id = %s AND human_verified = FALSE
            """,
            (work_id,),
        )
        for prediction in predictions:
            connection.execute(
                """
                INSERT INTO work_labels
                    (work_id, label_id, confidence, model_name, model_version,
                     human_verified, is_current)
                VALUES (%s, %s, %s, %s, %s, FALSE, TRUE)
                ON CONFLICT (work_id, label_id, model_name, model_version)
                DO UPDATE SET confidence = EXCLUDED.confidence,
                              is_current = TRUE,
                              created_at = NOW()
                """,
                (
                    work_id,
                    prediction["label_id"],
                    prediction["confidence"],
                    prediction["model_name"],
                    prediction["model_version"],
                ),
            )
        return len(predictions)


def classify_work(work_id: int) -> tuple[int, str]:
    with connect() as connection:
        work = connection.execute(
            "SELECT description FROM works WHERE id = %s", (work_id,)
        ).fetchone()
    if not work or not work["description"]:
        return 0, "unknown"
    with connect() as connection:
        taxonomy = connection.execute(
            """
            SELECT id, label_type, display_name, description, spice_level
            FROM label_taxonomy WHERE is_active = TRUE
            ORDER BY label_type, display_name
            """
        ).fetchall()
    predictions = predict_labels(work["description"], taxonomy)
    return save_predictions(work_id, predictions), "classified" if predictions else "unknown"
