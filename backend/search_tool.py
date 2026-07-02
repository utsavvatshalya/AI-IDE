from __future__ import annotations

import re
from typing import Iterable


def simple_search(instruction: str, file_history: Iterable[str]) -> list[str]:
    """Search recent file history for lines relevant to the current instruction."""
    if not instruction or not file_history:
        return []

    query_terms = [term.lower() for term in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", instruction) if len(term) > 2]
    matches: list[str] = []

    for content in reversed(list(file_history)):
        lowered = content.lower()
        if any(term in lowered for term in query_terms):
            matches.append(content)
            if len(matches) >= 3:
                break

    return matches
