from app.scripts.extract_tx_2026_claims_batch import _query_unextracted_statement_ids


def test_query_unextracted_statement_ids_has_race_filters() -> None:
    query = _query_unextracted_statement_ids()
    compiled = str(query)

    assert 'lower(candidates.state)' in compiled
    assert 'lower(candidates.office)' in compiled
    assert 'candidates.election_cycle =' in compiled
    assert 'candidates.race_stage IN' in compiled
    assert 'coalesce' in compiled.lower()
