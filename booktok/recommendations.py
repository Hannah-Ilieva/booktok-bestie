from __future__ import annotations

from typing import Any

from booktok.catalog import (
    catalog_search,
    label_history_preferences,
    label_names,
)
from booktok.embeddings import EmbeddingUnavailable, encode_query


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(max(value, low), high)


def recommend(
    query: str = "",
    query_vector: list[float] | None = None,
    label_ids: list[int] | None = None,
    spice_min: int | None = None,
    spice_max: int | None = None,
    limit: int = 12,
) -> tuple[list[dict[str, Any]], bool]:
    if query.strip() and query_vector is None:
        try:
            query_vector = encode_query(query.strip())
        except EmbeddingUnavailable:
            pass

    candidates = catalog_search(
        query=query.strip(),
        query_vector=query_vector,
        label_ids=label_ids,
        spice_min=spice_min,
        spice_max=spice_max,
        limit=100,
        exclude_shelf=True,
    )
    history = label_history_preferences()
    names = label_names(list(set(history) | set(label_ids or [])))
    selected_ids = set(label_ids or [])
    use_history = any(history.values())
    available_weights = {
        "semantic": 0.50 if query_vector is not None else 0.0,
        "query_tags": 0.30 if selected_ids else 0.0,
        "reading_history": 0.20 if use_history else 0.0,
    }
    total_weight = sum(available_weights.values()) or 1.0
    recommendations = []

    for book in candidates:
        book_label_ids = {label["id"] for label in book["labels"]}
        semantic = book.get("semantic_score")
        semantic_score = _clamp(float(semantic)) if semantic is not None else 0.0
        query_score = len(book_label_ids & selected_ids) / len(selected_ids) if selected_ids else 0.0
        matched_preferences = [history[label_id] for label_id in book_label_ids if label_id in history]
        history_score = (
            _clamp(0.5 + sum(matched_preferences) / (2 * len(matched_preferences)))
            if matched_preferences else 0.5
        )
        score_parts = {
            "semantic": semantic_score,
            "query_tags": query_score,
            "reading_history": history_score,
        }
        score = sum(
            score_parts[key] * weight
            for key, weight in available_weights.items()
        ) / total_weight

        reasons = []
        if semantic is not None and semantic_score >= 0.3:
            reasons.append("matches the meaning of your search")
        matched_query_labels = [names[label_id]["display_name"] for label_id in book_label_ids & selected_ids if label_id in names]
        if matched_query_labels:
            reasons.append("matches " + ", ".join(matched_query_labels[:3]))
        positive_history = [
            label_id for label_id in book_label_ids
            if history.get(label_id, 0) > 0 and label_id in names
        ]
        if positive_history:
            preferred = [names[label_id]["display_name"] for label_id in positive_history[:2]]
            reasons.append("shares " + ", ".join(preferred) + " with books you enjoyed")
        if not reasons:
            reasons.append("a catalog match; metadata and labels are still growing")

        recommendations.append(
            {
                **book,
                "score": score,
                "score_parts": score_parts,
                "score_weights": available_weights,
                "reasons": reasons,
            }
        )

    recommendations.sort(key=lambda item: item["score"], reverse=True)
    return recommendations[: min(max(limit, 1), 50)], query_vector is not None
