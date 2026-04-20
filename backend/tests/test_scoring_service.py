from app.services.scoring_service import calculate_score_metrics


def test_score_metrics_formula_matches_scoring_doc() -> None:
    metrics = calculate_score_metrics(
        denominator=10,
        supported=6,
        unsupported=2,
        with_min_evidence=8,
    )

    assert metrics.fsr == 0.6
    assert metrics.fcr == 0.2
    assert metrics.esr == 0.8
    assert metrics.composite == 0.5


def test_score_metrics_zero_denominator() -> None:
    metrics = calculate_score_metrics(
        denominator=0,
        supported=0,
        unsupported=0,
        with_min_evidence=0,
    )

    assert metrics.fsr == 0.0
    assert metrics.fcr == 0.0
    assert metrics.esr == 0.0
    assert metrics.composite is None


def test_denominator_excludes_insufficient_policy_behavior() -> None:
    total_latest_evaluated = 5
    insufficient_count = 2
    denominator = total_latest_evaluated - insufficient_count

    metrics = calculate_score_metrics(
        denominator=denominator,
        supported=2,
        unsupported=1,
        with_min_evidence=3,
    )

    assert metrics.denominator == 3
    assert metrics.fsr == 0.666667
    assert metrics.fcr == 0.333333
    assert metrics.esr == 1.0
