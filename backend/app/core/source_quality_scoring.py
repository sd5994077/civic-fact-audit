from __future__ import annotations

from urllib.parse import urlparse

from app.models.enums import SourceClass, SourceOrigin

QUALITY_SCORING_VERSION = 'quality_v1_2026_05_13'

_BASE_SCORE: dict[SourceClass, float] = {
    SourceClass.primary: 0.85,
    SourceClass.secondary: 0.70,
}


def _hostname(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.hostname or ''
    return host.strip().lower().rstrip('.')


def _domain_modifier(url: str) -> float:
    host = _hostname(url)
    if host == 'gov' or host.endswith('.gov'):
        return 0.10
    if host == 'edu' or host.endswith('.edu'):
        return 0.05
    return 0.0


def score_source_quality(
    url: str,
    source_class: SourceClass,
    source_origin: SourceOrigin,
    *,
    is_direct_candidate_quote: bool = False,
) -> float:
    score = _BASE_SCORE[source_class]

    if source_origin == SourceOrigin.verification:
        if source_class == SourceClass.primary:
            score += 0.05
    elif source_origin == SourceOrigin.candidate:
        score -= 0.10
        if is_direct_candidate_quote:
            score += 0.05

    score += _domain_modifier(url)

    return round(max(0.0, min(1.0, score)), 2)
