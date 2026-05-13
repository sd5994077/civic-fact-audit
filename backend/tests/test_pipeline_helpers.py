"""Unit tests for pipeline_helpers — RaceContext building and query parameterization."""

from __future__ import annotations

import dataclasses

import pytest
from sqlalchemy import Select

from app.core.intake_profiles import IntakeProfile
from app.models.enums import RaceStage
from app.scripts.pipeline_helpers import (
    RaceContext,
    build_candidate_filter,
    build_unextracted_statement_query,
    race_context_from_profile,
)


def _make_profile(**overrides: object) -> IntakeProfile:
    defaults: dict[str, object] = {
        'profile_id': 'test_2026_senate',
        'label': 'Test 2026 Senate',
        'state': 'TX',
        'office': 'US Senate',
        'election_cycle': 2026,
        'race_stage': 'primary',
        'roster_seed_module': 'app.scripts.ingest_test_2026_senate_roster',
        'statement_batch_modules': {'starter': 'app.scripts.ingest_test_2026_senate_statement_batch'},
        'admin_job_modules': {},
    }
    defaults.update(overrides)
    return IntakeProfile(**defaults)  # type: ignore[arg-type]


def test_race_context_from_profile_normalizes_state_and_office() -> None:
    profile = _make_profile(state='TX', office='US Senate')
    ctx = race_context_from_profile(profile)
    assert ctx.state == 'tx'
    assert ctx.office == 'us senate'


def test_race_context_from_profile_sets_all_fields() -> None:
    profile = _make_profile(
        profile_id='test_2026_ag_runoff',
        label='Test AG Runoff',
        state='TX',
        office='Attorney General',
        election_cycle=2026,
        race_stage='primary_runoff',
    )
    ctx = race_context_from_profile(profile)
    assert ctx.profile_id == 'test_2026_ag_runoff'
    assert ctx.label == 'Test AG Runoff'
    assert ctx.state == 'tx'
    assert ctx.office == 'attorney general'
    assert ctx.election_cycle == 2026
    assert ctx.race_stage == RaceStage.primary_runoff


def test_race_context_from_profile_strips_whitespace() -> None:
    profile = _make_profile(state='  TX  ', office='  US Senate  ')
    ctx = race_context_from_profile(profile)
    assert ctx.state == 'tx'
    assert ctx.office == 'us senate'


def test_race_context_from_profile_rejects_unknown_race_stage() -> None:
    profile = _make_profile(race_stage='not_a_real_stage')
    with pytest.raises(ValueError, match='unknown race_stage'):
        race_context_from_profile(profile)


def test_race_context_from_profile_accepts_all_valid_stages() -> None:
    for stage in RaceStage:
        profile = _make_profile(race_stage=stage.value)
        ctx = race_context_from_profile(profile)
        assert ctx.race_stage == stage


def test_build_candidate_filter_returns_four_conditions() -> None:
    ctx = RaceContext(
        profile_id='test',
        label='Test',
        state='tx',
        office='us senate',
        election_cycle=2026,
        race_stage=RaceStage.primary,
    )
    conditions = build_candidate_filter(ctx)
    assert len(conditions) == 4


def test_build_unextracted_statement_query_is_a_select() -> None:
    ctx = RaceContext(
        profile_id='test',
        label='Test',
        state='tx',
        office='us senate',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
    )
    query = build_unextracted_statement_query(ctx)
    assert isinstance(query, Select)


def test_race_context_is_frozen() -> None:
    ctx = RaceContext(
        profile_id='test',
        label='Test',
        state='tx',
        office='us senate',
        election_cycle=2026,
        race_stage=RaceStage.primary,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.state = 'ca'  # type: ignore[misc]


def test_race_context_equality() -> None:
    ctx_a = RaceContext('p1', 'L', 'tx', 'us senate', 2026, RaceStage.primary)
    ctx_b = RaceContext('p1', 'L', 'tx', 'us senate', 2026, RaceStage.primary)
    ctx_c = RaceContext('p1', 'L', 'tx', 'us senate', 2026, RaceStage.general)
    assert ctx_a == ctx_b
    assert ctx_a != ctx_c
