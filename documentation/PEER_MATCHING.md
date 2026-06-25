# Peer Matching Engine

The peer comparison tab uses a scored India-focused matcher in
`apps/funds/peers.py`. It is designed for the current AMFI-derived database,
where `scheme_category` is often empty, so fund names and basic scheme metadata
must carry most of the classification work.

## Entry Points

- `get_peer_matches(scheme, max_peers=5)` returns `PeerMatch` objects with the
  peer scheme, score, match reason, and match group.
- `find_peer_funds(scheme, max_peers=5)` remains available from
  `apps.funds.runtime` for older callers that only need scheme objects.
- `/api/funds/<amfi_code>/peers/` returns peer comparison data and includes
  API-only debug fields: `match_score`, `match_reason`, and `match_group`.

## Matching Rules

Hard filters always apply before scoring:

- same plan (`GROWTH` or `IDCW`)
- same Direct/Regular flag
- active schemes only
- exclude the base fund
- exclude the same fund house
- return at most one peer per fund house

Candidates are ranked by score first, then AUM, then scheme name. AUM never
overrides relevance.

## Fund Fingerprints

Each scheme is converted into a `FundFingerprint` using:

- `scheme_name`
- `scheme_category`
- `scheme_type`
- `plan`
- `is_direct`
- `fund_house`
- `aum_cr`

The fingerprint detects active equity, debt, hybrid, index funds, ETFs, FoFs,
commodity funds, solution-oriented funds, ELSS, sectors/themes, index groups,
FoF geography, and FoF asset type.

## Important Edge Cases

- Small cap, mid cap, flexi cap, and large & mid cap are separate groups.
- Banking & PSU Debt is treated as debt, not banking-sector equity.
- Nifty 50 and Nifty Next 50 are separate index groups.
- Nifty 50 Equal Weight is separate from plain Nifty 50.
- ELSS/tax-saver classification wins over passive index classification.
- Nasdaq equity FoFs do not fall back to US Treasury/Bond FoFs.
- Gilt and 10-year constant-duration gilt are separate debt groups.
- Gold and silver commodity exposures are matched separately.

## Validation

Run:

```powershell
$env:DEBUG='True'; python manage.py test apps.funds apps.analytics
```

The local `.env` must use a boolean value for `DEBUG`; `release` is not accepted
by `python-decouple`.
