from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.models.enums import SourceClass


@dataclass(frozen=True)
class SourceRecommendationTemplate:
    template_id: str
    source_class: SourceClass
    publisher: str
    url_template: str
    rationale: str
    priority: int
    state: str | None = None
    office: str | None = None
    race_stage: str | None = None
    issue_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceRecommendationPolicy:
    version: str
    default_limit: int
    templates: tuple[SourceRecommendationTemplate, ...]


DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / 'config' / 'source_recommendation_policy_v1.json'


@lru_cache(maxsize=1)
def get_source_recommendation_policy(path: str | None = None) -> SourceRecommendationPolicy:
    policy_path = Path(path) if path is not None else DEFAULT_POLICY_PATH
    payload = json.loads(policy_path.read_text(encoding='utf-8'))
    templates: list[SourceRecommendationTemplate] = []
    for raw in payload.get('templates', []):
        template_id = str(raw.get('id', '')).strip()
        if not template_id:
            raise ValueError('Source recommendation template missing id.')
        source_class_raw = str(raw.get('source_class', '')).strip().lower()
        if source_class_raw not in {'primary', 'secondary'}:
            raise ValueError(f'Unsupported source_class for template {template_id}: {source_class_raw}')
        issue_tags = tuple(str(tag).strip().lower() for tag in raw.get('issue_tags', []) if str(tag).strip())
        templates.append(
            SourceRecommendationTemplate(
                template_id=template_id,
                source_class=SourceClass(source_class_raw),
                publisher=str(raw.get('publisher', '')).strip() or 'Unknown publisher',
                url_template=str(raw.get('url_template', '')).strip(),
                rationale=str(raw.get('rationale', '')).strip(),
                priority=int(raw.get('priority', 100)),
                state=(str(raw.get('state', '')).strip().upper() or None),
                office=(str(raw.get('office', '')).strip().lower() or None),
                race_stage=(str(raw.get('race_stage', '')).strip().lower() or None),
                issue_tags=issue_tags,
            )
        )
    return SourceRecommendationPolicy(
        version=str(payload.get('version', 'source_recommendation_unversioned')).strip() or 'source_recommendation_unversioned',
        default_limit=max(1, int(payload.get('default_limit', 6))),
        templates=tuple(templates),
    )
