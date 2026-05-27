"""Subprocess helper for mstarpy runtime fetches.

mstarpy uses signal-based timeout handling internally. Django request handlers
may run in worker threads, where Python signal APIs are unavailable, so runtime
views call this helper in a separate Python process.
"""
from __future__ import annotations

import json
import sys
from difflib import SequenceMatcher
from typing import Any


def main() -> int:
    request = json.loads(sys.argv[1])
    terms = request.get("terms") or []
    expected_isin = str(request.get("expected_isin") or "").upper()
    family = str(request.get("family") or "")

    import mstarpy

    last_error = None
    for term in terms:
        try:
            fund = mstarpy.Funds(term=term)
            meta = fund.metaData()
            if not valid_match(meta, expected_isin, family):
                continue
            payload = {
                "meta": clean(meta),
                "holdings": frame_records(fund.holdings()),
                "sector": clean(fund.sector()),
                "allocation": clean(fund.allocationMap()),
            }
            print(json.dumps({"ok": True, "term": term, "payload": payload}))
            return 0
        except Exception as exc:  # pragma: no cover - defensive helper boundary
            last_error = str(exc)
            continue

    print(json.dumps({"ok": False, "error": last_error or "No matching mstarpy fund"}))
    return 1


def valid_match(meta: dict, expected_isin: str, family: str) -> bool:
    country = str(meta.get("countryId") or meta.get("domicileCountryId") or "").upper()
    if country and country not in {"IND", "IN"}:
        return False
    isin = str(meta.get("isin") or "").upper()
    if expected_isin and isin == expected_isin:
        return True
    if not family:
        return False
    return SequenceMatcher(None, family, family_key(str(meta.get("name") or ""))).ratio() >= 0.62


def family_key(name: str) -> str:
    import re

    value = re.sub(r"\b(direct|regular)\s+plan\b", " ", name, flags=re.I)
    value = re.sub(r"\b(growth|idcw)\s+(plan|option)\b", " ", value, flags=re.I)
    value = re.sub(r"\b(growth|idcw|dividend|reinvestment|payout|fund|scheme|plan|option|dir|gr|reg)\b", " ", value, flags=re.I)
    value = re.sub(r"\s*-\s*", " ", value)
    return " ".join(value.lower().split())


def frame_records(value: Any) -> list[dict]:
    if value is None or not hasattr(value, "empty") or value.empty:
        return []
    return clean(value.head(80).to_dict("records"))


def clean(value: Any):
    try:
        import numpy as np
        import pandas as pd
    except Exception:  # pragma: no cover
        np = None
        pd = None

    if pd is not None:
        if value is pd.NaT:
            return None
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        try:
            if pd.isna(value) and not isinstance(value, (dict, list, tuple)):
                return None
        except Exception:
            pass
    if np is not None and isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
