from app.scripts.generate_tx_2026_adjudication_packet import _select_balanced_batch


def test_select_balanced_batch_limits_per_candidate() -> None:
    rows = [
        {'candidate_id': 'a', 'claim_id': '1'},
        {'candidate_id': 'a', 'claim_id': '2'},
        {'candidate_id': 'b', 'claim_id': '3'},
        {'candidate_id': 'b', 'claim_id': '4'},
        {'candidate_id': 'c', 'claim_id': '5'},
    ]

    selected = _select_balanced_batch(rows, per_candidate_limit=1)
    ids = [row['claim_id'] for row in selected]
    assert ids == ['1', '3', '5']
