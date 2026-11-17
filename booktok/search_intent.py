from __future__ import annotations

import re
from typing import Any


SPICE_PHRASES = (
    (5, ("very spicy", "extremely spicy", "explicit")),
    (4, ("spicy", "steamy", "high heat")),
    (3, ("moderate spice", "open door")),
    (2, ("mild spice", "low heat")),
    (1, ("closed door", "fade to black")),
)


def _words(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def parse_search_intent(query: str, taxonomy: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = _words(query)
    selected_labels = []
    matched_phrases = []
    remaining = normalized

    for label in sorted(taxonomy, key=lambda item: len(_words(item["display_name"])), reverse=True):
        if label["label_type"] == "spice":
            continue
        phrase = _words(label["display_name"])
        if phrase and re.search(rf"\b{re.escape(phrase)}\b", remaining):
            selected_labels.append(label["id"])
            matched_phrases.append(label["display_name"])
            remaining = re.sub(rf"\b{re.escape(phrase)}\b", " ", remaining)

    spice_range = (None, None)
    for level, phrases in SPICE_PHRASES:
        phrase = next((item for item in phrases if _words(item) in normalized), None)
        if phrase:
            spice_range = (level, level)
            matched_phrases.append(phrase)
            remaining = remaining.replace(_words(phrase), " ")
            break

    return {
        "label_ids": list(dict.fromkeys(selected_labels)),
        "spice_min": spice_range[0],
        "spice_max": spice_range[1],
        "free_text": " ".join(remaining.split()),
        "matched_phrases": matched_phrases,
    }
