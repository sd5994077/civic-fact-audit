import pytest

from app.core.source_quality_scoring import QUALITY_SCORING_VERSION, score_source_quality
from app.models.enums import SourceClass, SourceOrigin


def _score(
    url: str = 'https://example.com/report',
    source_class: SourceClass = SourceClass.primary,
    source_origin: SourceOrigin = SourceOrigin.verification,
    is_direct_candidate_quote: bool = False,
) -> float:
    return score_source_quality(
        url=url,
        source_class=source_class,
        source_origin=source_origin,
        is_direct_candidate_quote=is_direct_candidate_quote,
    )


def test_quality_scoring_version_is_set() -> None:
    assert QUALITY_SCORING_VERSION.startswith('quality_v1_')


def test_verification_primary_baseline() -> None:
    assert _score() == 0.90


def test_verification_secondary_baseline() -> None:
    assert _score(source_class=SourceClass.secondary) == 0.70


def test_candidate_primary_no_quote() -> None:
    assert _score(source_origin=SourceOrigin.candidate) == 0.75


def test_candidate_secondary_no_quote() -> None:
    assert _score(source_class=SourceClass.secondary, source_origin=SourceOrigin.candidate) == 0.60


def test_candidate_primary_direct_quote() -> None:
    assert _score(source_origin=SourceOrigin.candidate, is_direct_candidate_quote=True) == 0.80


def test_candidate_secondary_direct_quote() -> None:
    assert _score(
        source_class=SourceClass.secondary,
        source_origin=SourceOrigin.candidate,
        is_direct_candidate_quote=True,
    ) == 0.65


def test_gov_domain_boost_verification_primary() -> None:
    assert _score(url='https://cbo.gov/reports/fiscal-2024') == 1.00


def test_gov_domain_boost_verification_secondary() -> None:
    assert _score(url='https://congress.gov/bill/text', source_class=SourceClass.secondary) == 0.80


def test_edu_domain_boost_verification_primary() -> None:
    assert _score(url='https://research.mit.edu/study') == 0.95


def test_edu_domain_boost_verification_secondary() -> None:
    assert _score(url='https://law.stanford.edu/brief', source_class=SourceClass.secondary) == 0.75


def test_gov_subdomain_is_detected() -> None:
    assert _score(url='https://data.texas.gov/dataset/voters') == 1.00


def test_edu_subdomain_is_detected() -> None:
    assert _score(url='https://press.harvard.edu/report') == 0.95


def test_non_special_domain_no_boost() -> None:
    assert _score(url='https://reuters.com/article/123') == 0.90


def test_direct_quote_flag_ignored_for_verification_origin() -> None:
    assert _score(source_origin=SourceOrigin.verification, is_direct_candidate_quote=True) == 0.90


def test_score_clamped_to_one() -> None:
    result = _score(url='https://senate.gov/record', source_origin=SourceOrigin.verification, source_class=SourceClass.primary)
    assert result <= 1.0


def test_score_clamped_to_zero_at_minimum() -> None:
    result = _score(source_class=SourceClass.secondary, source_origin=SourceOrigin.candidate)
    assert result >= 0.0


def test_returns_float() -> None:
    result = _score()
    assert isinstance(result, float)


def test_score_rounded_to_two_decimal_places() -> None:
    result = _score()
    assert result == round(result, 2)


@pytest.mark.parametrize('url', [
    'https://example.com',
    'http://blog.example.net/post',
    'https://app.io/data',
    'https://cnn.com/article',
])
def test_no_domain_boost_for_generic_domains(url: str) -> None:
    result = _score(url=url, source_class=SourceClass.primary, source_origin=SourceOrigin.verification)
    assert result == 0.90
