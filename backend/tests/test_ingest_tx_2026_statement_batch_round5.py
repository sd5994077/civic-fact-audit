from app.models.enums import RaceStage, StatementSourceType
from app.scripts.ingest_tx_2026_statement_batch_round5 import SEEDS


def test_round5_targets_runoff_candidates_only() -> None:
    candidate_names = {seed.candidate_name for seed in SEEDS}
    assert candidate_names == {'John Cornyn', 'Ken Paxton'}
    assert all(seed.race_stage == RaceStage.primary_runoff for seed in SEEDS)


def test_round5_has_minimum_five_statements_per_candidate() -> None:
    counts: dict[str, int] = {}
    for seed in SEEDS:
        counts[seed.candidate_name] = counts.get(seed.candidate_name, 0) + 1

    assert counts['John Cornyn'] >= 3
    assert counts['Ken Paxton'] >= 3


def test_round5_uses_candidate_origin_capture_channels() -> None:
    assert all(seed.source_type in {StatementSourceType.press_release, StatementSourceType.social} for seed in SEEDS)
