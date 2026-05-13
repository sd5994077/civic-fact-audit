import uuid
from unittest.mock import MagicMock

from app.services.search_service import SearchService


class TestSearchServiceBlankQuery:
    def test_blank_string_returns_empty_without_db_call(self) -> None:
        db = MagicMock()
        result = SearchService.search_claims(db, q='   ')
        assert result == []
        db.execute.assert_not_called()

    def test_empty_string_returns_empty_without_db_call(self) -> None:
        db = MagicMock()
        result = SearchService.search_claims(db, q='')
        assert result == []
        db.execute.assert_not_called()


class TestSearchServiceQueryBuilding:
    def _compile(self, q: str = 'test', **kwargs):
        """Return (sql_str, params_dict) for the compiled query."""
        from sqlalchemy.dialects import postgresql

        captured: list = []

        class _CapturingDB:
            def execute(self, stmt, *args, **kw):
                captured.append(stmt)
                mock_result = MagicMock()
                mock_result.mappings.return_value.all.return_value = []
                return mock_result

        SearchService.search_claims(_CapturingDB(), q=q, **kwargs)  # type: ignore[arg-type]
        assert captured, 'execute was not called'
        compiled = captured[0].compile(dialect=postgresql.dialect())
        return str(compiled), dict(compiled.params)

    def test_sql_contains_tsvector_match(self) -> None:
        sql, _ = self._compile(q='immigration')
        assert 'to_tsvector' in sql
        assert 'plainto_tsquery' in sql

    def test_sql_contains_ilike_on_candidate_name(self) -> None:
        sql, _ = self._compile(q='Smith')
        assert 'ILIKE' in sql.upper()

    def test_sql_applies_state_filter(self) -> None:
        _, params = self._compile(q='tax', state='TX')
        assert 'TX' in params.values()

    def test_sql_applies_office_filter(self) -> None:
        _, params = self._compile(q='tax', office='governor')
        assert 'governor' in params.values()

    def test_sql_applies_election_cycle_filter(self) -> None:
        _, params = self._compile(q='tax', election_cycle=2026)
        assert 2026 in params.values()

    def test_sql_contains_order_by_rank(self) -> None:
        sql, _ = self._compile(q='jobs')
        assert 'ts_rank' in sql
        assert 'ORDER BY' in sql.upper()

    def test_sql_applies_limit(self) -> None:
        _, params = self._compile(q='jobs', limit=25)
        assert 25 in params.values()

    def test_sql_applies_fact_checkable_filter(self) -> None:
        sql, _ = self._compile(q='tax', fact_checkable=True)
        assert 'fact_checkable' in sql

    def test_no_optional_filters_adds_single_where(self) -> None:
        sql, _ = self._compile(q='crime')
        assert sql.upper().count('WHERE') == 1


class TestSearchServiceEscaping:
    def _like_patterns(self, q: str) -> list[str]:
        _, params = TestSearchServiceQueryBuilding()._compile(q=q)
        return [v for v in params.values() if isinstance(v, str) and v.startswith('%')]

    def test_percent_in_query_is_escaped(self) -> None:
        patterns = self._like_patterns('50%')
        assert patterns, 'no ILIKE pattern params found'
        assert all(r'\%' in p for p in patterns)

    def test_underscore_in_query_is_escaped(self) -> None:
        patterns = self._like_patterns('te_t')
        assert patterns, 'no ILIKE pattern params found'
        assert all(r'\_' in p for p in patterns)

    def test_plain_query_unchanged_in_pattern(self) -> None:
        patterns = self._like_patterns('immigration')
        assert patterns, 'no ILIKE pattern params found'
        assert any('immigration' in p for p in patterns)


class TestSearchServiceResults:
    def test_returns_mapped_dicts(self) -> None:
        cid = uuid.uuid4()
        canid = uuid.uuid4()
        mock_row = {
            'claim_id': cid,
            'claim_text': 'Taxes went up',
            'issue_tag': 'economy',
            'status': 'draft',
            'fact_checkable': True,
            'is_published': False,
            'candidate_id': canid,
            'candidate_name': 'Jane Doe',
            'candidate_party': 'Independent',
            'candidate_office': 'governor',
            'candidate_state': 'TX',
            'election_cycle': 2026,
            'race_stage': 'general',
            'rank': 0.75,
        }

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [mock_row]
        db = MagicMock()
        db.execute.return_value = mock_result

        results = SearchService.search_claims(db, q='taxes')
        assert len(results) == 1
        assert results[0]['claim_id'] == cid
        assert results[0]['rank'] == 0.75
