from __future__ import annotations

import json
import re
from typing import Any


_RHETORICAL_PATTERNS = (
    re.compile(r"\bit'?s time to\b"),
    re.compile(r"\bstart flipping tables\b"),
    re.compile(r"\bfights? for texas\b"),
    re.compile(r"\bchange mandate\b"),
    re.compile(r"\bjoin us\b"),
    re.compile(r"\bstand with\b"),
    re.compile(r"\bwe can\b"),
)

_FACTUAL_PATTERNS = (
    re.compile(r"\b\d[\d,]*(?:\.\d+)?\b"),
    re.compile(r"\$\s?\d"),
    re.compile(r"\b\d+(?:\.\d+)?%"),
    re.compile(r"\b(19|20)\d{2}\b"),
    re.compile(
        r"\b(voted|vote|introduced|sponsored|co-sponsored|filed|signed|passed|won|lost|raised|spent|"
        r"reported|increased|decreased|cut|expanded|closed|convicted|charged|sentenced|audited|"
        r"confirm|confirmed|blocked|approved|rejected|ordered|ruled|searched)\b"
    ),
)

_FACTUAL_KEYWORDS = (
    'court',
    'lawsuit',
    'fbi',
    'department',
    'agency',
    'supreme court',
    'justice',
    'judiciary',
    'budget',
    'tax',
    'inflation',
    'medicaid',
    'medicare',
    'border',
    'immigration',
    'jobs',
    'unemployment',
    'tariff',
    'veterans',
    'ballot',
    'audit',
    'crime',
)


class ClaimReviewabilityService:
    @staticmethod
    def classify_text(text: str) -> dict[str, Any]:
        normalized = ' '.join(text.split())
        lowered = normalized.lower()

        if len(normalized) < 25:
            return {
                'fact_checkable': False,
                'reviewability_reason': 'too_short_for_reliable_fact_check',
                'classifier': 'heuristic_v1',
            }

        for pattern in _RHETORICAL_PATTERNS:
            if pattern.search(lowered):
                return {
                    'fact_checkable': False,
                    'reviewability_reason': 'campaign_rhetoric_or_slogan',
                    'classifier': 'heuristic_v1',
                }

        has_factual_signal = any(pattern.search(normalized) for pattern in _FACTUAL_PATTERNS) or any(
            keyword in lowered for keyword in _FACTUAL_KEYWORDS
        )
        if not has_factual_signal:
            return {
                'fact_checkable': False,
                'reviewability_reason': 'missing_objective_verification_signal',
                'classifier': 'heuristic_v1',
            }

        return {
            'fact_checkable': True,
            'reviewability_reason': 'contains_objective_or_record_checkable_signal',
            'classifier': 'heuristic_v1',
        }

    @staticmethod
    def build_extraction_metadata(*, provider: str, text: str, existing_metadata: dict[str, Any] | None = None) -> str:
        metadata = dict(existing_metadata or {})
        metadata.update({'provider': provider})
        metadata.update(ClaimReviewabilityService.classify_text(text))
        return json.dumps(metadata, sort_keys=True)

    @staticmethod
    def parse_metadata(raw_metadata: str | None) -> dict[str, Any]:
        if not raw_metadata:
            return {}
        try:
            parsed = json.loads(raw_metadata)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
