"""
health_check.py — AI model regression health check.

Runs 4 diagnostic scenarios against the production model stack and compares
results against a stored baseline.  Exits 0 on pass, 1 on regression detected.

Usage:
    python health_check.py                  # run check, print report
    python health_check.py --save-baseline  # save current results as new baseline
    python health_check.py --threshold 5    # allow up to 5% score drop before alerting (default: 0)

Designed to be run on a schedule (weekly) and piped to an alerting webhook.
Set CIVIC_AI_DEGRADED_MODE=true in .env when this exits 1.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Bootstrap: resolve project root and import shared infrastructure
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parents[3]
_BASELINE_PATH = _SCRIPT_DIR / 'health_check_baseline.json'

sys.path.insert(0, str(_SCRIPT_DIR.parent.parent.parent))
sys.path.insert(0, str(_SCRIPT_DIR))  # so stress_test_models is importable by filename

# Reuse env loading and model/schema constants from the stress test script.
# We import selectively to avoid pulling in the full scenario list.
from stress_test_models import (  # noqa: E402
    _load_env,
    MODELS,
    SCHEMA,
    GEMINI_SCHEMA,
    SYSTEM_PROMPT,
    build_payload,
    call_model,
    evaluate_pass_fail,
    _misleading_criteria,
    _false_criteria,
    _truthful_criteria,
)

_load_env()

OPENAI_API_KEY    = os.environ.get('OPENAI_API_KEY', '')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# ---------------------------------------------------------------------------
# Diagnostic scenario subset — chosen to maximally stress failure modes:
#   1. voting_record_false   — the worst gpt-4o-mini regression scenario
#   2. tcja_83pct            — hard misleading, projection/methodology complexity
#   3. inflation_june2022    — clear truthful, should never regress
#   4. medicare_bankrupt     — medium misleading, "bankruptcy" framing trap
# ---------------------------------------------------------------------------

_CANDIDATE = {
    'name': 'Health Check Candidate',
    'party': 'Independent',
    'office': 'Senate',
    'state': 'TX',
}

DIAGNOSTIC_SCENARIOS = [
    {
        'id': 'voting_record_false',
        'topic': 'Voting Record — False Claim',
        'claim_type': 'false',
        'difficulty': 'easy',
        'claim_text': (
            'Representative Sarah Chen voted against the Infrastructure Investment and Jobs Act, '
            'blocking over $400 million in critical infrastructure funding for our district.'
        ),
        'issue_tag': 'voting_record_infrastructure',
        'pass_criteria': _false_criteria(
            ['voted for', 'yea', 'aye', 'supported', 'contradicts', 'inaccurate', 'record']
        ),
        'sources': [
            {
                'source_id': 'src-vote-01',
                'url': 'https://clerk.house.gov/Votes/2021369',
                'source_class': 'primary', 'source_origin': 'verification',
                'publisher': 'Office of the Clerk, U.S. House of Representatives',
                'fetch_status': 'ok', 'content_type': 'text/html',
                'content_excerpt': (
                    'House Roll Call Vote 369, November 5, 2021 — H.R. 3684: Final passage. '
                    'Result: 228 Yeas, 206 Nays. Member: CHEN, Sarah (D-TX-7) — Vote: YEA. '
                    'The official vote record directly contradicts the claim she voted against it.'
                ),
            },
            {
                'source_id': 'src-vote-02',
                'url': 'https://www.congress.gov/bill/117th-congress/house-bill/3684',
                'source_class': 'secondary', 'source_origin': 'verification',
                'publisher': 'Congress.gov',
                'fetch_status': 'ok', 'content_type': 'text/html',
                'content_excerpt': (
                    'H.R. 3684 passed House 228-206 on November 5, 2021. '
                    "Rep. Chen's district (TX-7) received approximately $412 million in allocations. "
                    'Her Yea vote directly contradicts the claim she voted against it.'
                ),
            },
        ],
    },
    {
        'id': 'tcja_83pct',
        'topic': 'TCJA — "83 percent to the top 1 percent"',
        'claim_type': 'misleading',
        'difficulty': 'hard',
        'claim_text': (
            'The Trump tax cuts gave 83 percent of the benefits to the top 1 percent of Americans, '
            'leaving working families with nothing while billionaires got massive tax breaks.'
        ),
        'issue_tag': 'tax_policy_tcja',
        'pass_criteria': _misleading_criteria(
            ['projection', '2027', 'temporary', 'expiration', 'joint committee',
             'tpc', 'near-term', 'long-run', 'framing']
        ),
        'sources': [
            {
                'source_id': 'src-tcja-01',
                'url': 'https://www.taxpolicycenter.org/publications/distributional-analysis-conference-agreement-tax-cuts-and-jobs-act',
                'source_class': 'primary', 'source_origin': 'verification',
                'publisher': 'Tax Policy Center',
                'fetch_status': 'ok', 'content_type': 'text/html',
                'content_excerpt': (
                    'TPC analysis: In 2027, when most individual provisions expire, 82.8% of the '
                    'net benefit flows to the top 1%. In 2018 (year of enactment), the top 1% '
                    'receives about 20% of benefits while all income quintiles see tax cuts. '
                    'The 83% figure is a long-run projection contingent on temporary provisions '
                    'expiring — it does not describe current benefit distribution.'
                ),
            },
            {
                'source_id': 'src-tcja-02',
                'url': 'https://www.jct.gov/publications/2017/jcx-67-17/',
                'source_class': 'secondary', 'source_origin': 'verification',
                'publisher': 'Joint Committee on Taxation',
                'fetch_status': 'ok', 'content_type': 'text/html',
                'content_excerpt': (
                    'JCT distributional table: Taxpayers in all income brackets receive net tax '
                    'reductions in 2019. The working-families claim of "nothing" is not supported. '
                    'The 83% figure depends on the 2025 individual provision sunsets occurring '
                    'as scheduled. The claim presents a conditional 2027 scenario as the '
                    'definitive current distribution of benefits.'
                ),
            },
        ],
    },
    {
        'id': 'inflation_june2022',
        'topic': 'CPI — June 2022 9.1% Peak (Truthful)',
        'claim_type': 'truthful',
        'difficulty': 'easy',
        'claim_text': (
            'Consumer prices rose 9.1 percent in June 2022 compared to a year earlier, '
            'the highest annual inflation rate in over 40 years.'
        ),
        'issue_tag': 'inflation_cpi',
        'pass_criteria': _truthful_criteria(),
        'sources': [
            {
                'source_id': 'src-cpi-01',
                'url': 'https://www.bls.gov/news.release/cpi.nr0.htm',
                'source_class': 'primary', 'source_origin': 'verification',
                'publisher': 'Bureau of Labor Statistics',
                'fetch_status': 'ok', 'content_type': 'text/html',
                'content_excerpt': (
                    'BLS CPI-U, June 2022: All items index rose 9.1% over the prior 12 months, '
                    'the largest 12-month increase since November 1981 (40+ years). '
                    'The claim is factually accurate and well-supported by primary government data.'
                ),
            },
        ],
    },
    {
        'id': 'medicare_bankrupt',
        'topic': 'Medicare "Bankruptcy" by 2031',
        'claim_type': 'misleading',
        'difficulty': 'medium',
        'claim_text': (
            'Medicare will go bankrupt by 2031, eliminating hospital coverage for '
            '66 million seniors and disabled Americans.'
        ),
        'issue_tag': 'medicare_entitlements',
        'pass_criteria': _misleading_criteria(
            ['trust fund', 'depletion', 'hI', 'part a', 'bankruptcy',
             'payroll tax', 'reduced', 'not eliminated', 'beneficiary']
        ),
        'sources': [
            {
                'source_id': 'src-med-01',
                'url': 'https://www.cms.gov/oact/tr/2024',
                'source_class': 'primary', 'source_origin': 'verification',
                'publisher': 'CMS Medicare Trustees Report 2024',
                'fetch_status': 'ok', 'content_type': 'text/html',
                'content_excerpt': (
                    '2024 Trustees Report: The HI (Hospital Insurance) Trust Fund is projected '
                    'to be depleted in 2036 under intermediate assumptions. After depletion, '
                    'ongoing payroll tax revenues would cover approximately 89% of scheduled '
                    'benefits. Depletion does not mean program termination; Medicare continues '
                    'at reduced payment rates. The claim incorrectly characterizes depletion '
                    'as bankruptcy and elimination of coverage.'
                ),
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def run_diagnostics(models_to_check: list[dict] | None = None) -> list[dict]:
    """Run all 4 diagnostic scenarios against the specified models."""
    models = models_to_check or MODELS
    results = []

    for scenario in DIAGNOSTIC_SCENARIOS:
        payload = build_payload(scenario)
        # Patch candidate into payload
        payload['candidate'] = _CANDIDATE
        runs = []
        for model in models:
            t0 = time.time()
            result, error, tokens = call_model(model, payload)
            elapsed = time.time() - t0
            in_tok  = tokens['input_tokens']  if tokens else 0
            out_tok = tokens['output_tokens'] if tokens else 0
            cost    = in_tok * model['input_rate'] + out_tok * model['output_rate']
            pf      = evaluate_pass_fail(result, scenario['pass_criteria'])
            n_pass  = sum(1 for _, ok in pf if ok)
            n_total = len(scenario['pass_criteria'])
            runs.append({
                'model_label': model['label'],
                'model_id':    model['id'],
                'provider':    model['provider'],
                'elapsed':     round(elapsed, 2),
                'cost':        round(cost, 6),
                'n_pass':      n_pass,
                'n_total':     n_total,
                'score_pct':   round(n_pass / n_total * 100, 1),
                'result':      result,
                'error':       error,
                'pass_fail':   [(label, ok) for label, ok in pf],
            })
        results.append({'scenario': scenario, 'runs': runs})

    return results


def aggregate_scores(results: list[dict]) -> dict[str, float]:
    """Return {model_label: overall_score_pct} across all 4 scenarios."""
    totals: dict[str, list[int]] = {}
    for entry in results:
        for run in entry['runs']:
            ml = run['model_label']
            if ml not in totals:
                totals[ml] = [0, 0]
            totals[ml][0] += run['n_pass']
            totals[ml][1] += run['n_total']
    return {ml: round(v[0] / v[1] * 100, 1) for ml, v in totals.items()}


# ---------------------------------------------------------------------------
# Baseline management
# ---------------------------------------------------------------------------

def load_baseline() -> dict | None:
    if not _BASELINE_PATH.exists():
        return None
    with _BASELINE_PATH.open() as f:
        return json.load(f)


def save_baseline(results: list[dict], scores: dict[str, float]) -> None:
    baseline = {
        'saved_at': datetime.now().isoformat(),
        'scores': scores,
        'scenario_ids': [e['scenario']['id'] for e in results],
    }
    with _BASELINE_PATH.open('w') as f:
        json.dump(baseline, f, indent=2)
    print(f'Baseline saved to {_BASELINE_PATH}')


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(results: list[dict], scores: dict[str, float],
                 baseline: dict | None, threshold: float) -> bool:
    """Print a human-readable report. Returns True if all checks pass."""
    sep  = '-' * 72
    dsep = '=' * 72
    now  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print()
    print(dsep)
    print(f'  CIVIC FACT-CHECK AI HEALTH CHECK  —  {now}')
    print(dsep)
    print(f'  Scenarios: {len(DIAGNOSTIC_SCENARIOS)}   '
          f'Models: {len(MODELS)}   '
          f'Regression threshold: {threshold}%')
    print()

    # Per-scenario breakdown
    for entry in results:
        sc = entry['scenario']
        print(f'  [{sc["id"].upper()}]  {sc["claim_type"].upper()}  ({sc["difficulty"]})')
        print(f'  {sep}')
        for run in entry['runs']:
            pf_str = '  '.join(
                ('✓' if ok else '✗') + ' ' + label[:28]
                for label, ok in run['pass_fail']
            )
            status = 'OK' if run['n_pass'] == run['n_total'] else 'FAIL'
            r = run['result']
            if r:
                verdict = (r.get('suggested_verdict') or '?').upper()[:11]
                conf    = r.get('suggested_confidence', 0)
                warn    = len(r.get('warnings', []))
                green   = r.get('green_lane_ready', '?')
                detail  = f'verdict={verdict:<12} conf={conf:.2f}  warn={warn}  green={green}'
            else:
                detail = f'ERROR: {run["error"] or "unknown"}' [:55]
            print(
                f'  {run["model_label"]:<22}  [{status}]  {run["n_pass"]}/{run["n_total"]}  '
                f'{detail}  ({run["elapsed"]:.1f}s)'
            )
        print()

    # Overall scores
    print(f'  OVERALL SCORES')
    print(f'  {sep}')
    all_pass = True
    regression_models: list[str] = []

    for ml, score in scores.items():
        baseline_score = baseline['scores'].get(ml) if baseline else None
        if baseline_score is not None:
            delta = score - baseline_score
            delta_str = f'  Δ{delta:+.1f}%'
            regressed = delta < -threshold
        else:
            delta_str = '  (no baseline)'
            regressed = False

        if regressed:
            all_pass = False
            regression_models.append(ml)
            flag = '🚨 REGRESSION'
        elif score < 100:
            flag = '⚠  DEGRADED'
        else:
            flag = '✓  OK'

        print(f'  {ml:<22}  {score:5.1f}%{delta_str:<14}  {flag}')

    print()
    print(f'  {dsep}')
    if all_pass:
        print('  ✅  HEALTH CHECK PASSED — no regressions detected')
    else:
        print('  🚨  HEALTH CHECK FAILED — regression detected in:')
        for ml in regression_models:
            b = baseline['scores'].get(ml, 'N/A') if baseline else 'N/A'
            print(f'       {ml}: baseline={b}%  current={scores[ml]}%')
        print()
        print('  ACTION REQUIRED:')
        print('    1. Investigate model outputs above for the failure pattern')
        print('    2. Set CIVIC_AI_DEGRADED_MODE=true in .env to enable circuit breaker')
        print('    3. Restart the API server to apply the change')
        print('    4. Re-run this check after investigating to confirm recovery')
        print('    5. Set CIVIC_AI_DEGRADED_MODE=false and restart once resolved')
    print(f'  {dsep}')
    print()

    return all_pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description='Civic AI health check')
    parser.add_argument(
        '--save-baseline', action='store_true',
        help='Save current run as the new baseline (do this after a confirmed-good run)',
    )
    parser.add_argument(
        '--threshold', type=float, default=0.0,
        help='Allowed score drop %% before declaring regression (default: 0)',
    )
    parser.add_argument(
        '--primary-only', action='store_true',
        help='Only test the primary model (gpt-4o-mini) — faster for quick checks',
    )
    args = parser.parse_args()

    models_to_check = [m for m in MODELS if m['provider'] == 'openai' and 'mini' in m['id']] \
        if args.primary_only else None

    print(f'\nRunning {len(DIAGNOSTIC_SCENARIOS)} diagnostic scenarios…')
    results = run_diagnostics(models_to_check)
    scores  = aggregate_scores(results)
    baseline = load_baseline()

    passed = print_report(results, scores, baseline, threshold=args.threshold)

    if args.save_baseline:
        save_baseline(results, scores)

    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()
