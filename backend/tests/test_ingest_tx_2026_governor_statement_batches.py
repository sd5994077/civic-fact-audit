from __future__ import annotations

import pytest

from app.models.enums import RaceStage, StatementSourceType
from app.scripts.ingest_tx_2026_governor_statement_batch import (
    _DISALLOWED_GENERIC_SOURCE_PATHS,
    SEEDS as STARTER_SEEDS,
    _validate_source_url,
)
from app.scripts.ingest_tx_2026_governor_statement_batch_round2 import SEEDS as ROUND2_SEEDS


def test_governor_starter_seeds_target_general_race() -> None:
    assert STARTER_SEEDS
    assert all(seed.race_stage == RaceStage.general for seed in STARTER_SEEDS)
    assert all(seed.source_type == StatementSourceType.press_release for seed in STARTER_SEEDS)


def test_governor_round2_has_balanced_candidate_coverage() -> None:
    counts: dict[str, int] = {}
    for seed in ROUND2_SEEDS:
        counts[seed.candidate_name] = counts.get(seed.candidate_name, 0) + 1

    assert counts == {'Greg Abbott': 2, 'Gina Hinojosa': 2}


def test_governor_round2_claim_texts_include_objective_signals() -> None:
    assert all(any(ch.isdigit() for ch in seed.statement_text) for seed in ROUND2_SEEDS)


def test_source_url_validator_rejects_generic_landing_pages() -> None:
    for path in _DISALLOWED_GENERIC_SOURCE_PATHS:
        if not path:
            continue
        with pytest.raises(ValueError):
            _validate_source_url(f'https://example.com{path}')


def test_source_url_validator_accepts_claim_level_pages() -> None:
    _validate_source_url('https://example.com/2026/05/sample-press-release/')
    _validate_source_url('https://www.gregabbott.com/governor-abbott-raises-over-20-million-in-latest-reporting-period/')
