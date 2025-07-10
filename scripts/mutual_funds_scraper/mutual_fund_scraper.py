#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime as _dt, json, pathlib, sys
from typing import Dict, List, Optional

import pandas as _pd


def _parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("-l", "--tickers-file")
    p.add_argument("-o", "--output", default="mutual_funds.json")
    return p.parse_args()


def _drop_nones(d: Dict[str, Optional[object]]):
    return {k: v for k, v in d.items() if v is not None}


def _epoch_to_iso(e: Optional[int]):
    if e is None:
        return None
    try:
        return _dt.datetime.utcfromtimestamp(e).date().isoformat()
    except Exception:
        return None


TEST_FUNDS = [
    "FXAIX",
]


def _load_tickers(path: str | None):
    if path is None:
        return TEST_FUNDS
    lines = pathlib.Path(path).read_text().splitlines()
    # Remove duplicates and normalize case
    tickers = [ln.strip().upper() for ln in lines if ln.strip()]
    return list(sorted(set(tickers)))


def _find_price(df: _pd.DataFrame, target: _dt.date):
    if df.empty:
        return None
    s = df.loc[df.index.date <= target]
    if s.empty:
        return None
    return float(s.iloc[-1]["Close"])


def _calc_trailing(df: _pd.DataFrame, today: _dt.date):
    res: Dict[str, float] = {}
    now_price = float(df.iloc[-1]["Close"]) if not df.empty else None
    if not now_price:
        return res
    for yrs, key in [(1, "oneYear"), (3, "threeYear"), (5, "fiveYear"), (10, "tenYear")]:
        old_date = today - _dt.timedelta(days=365 * yrs)
        old_price = _find_price(df, old_date)
        if old_price:
            res[key] = (now_price / old_price) - 1.0
    return res


def _calc_calendar(df: _pd.DataFrame, today: _dt.date):
    cal: Dict[str, float] = {}
    this_year = today.year
    for yr in range(this_year - 1, this_year - 11, -1):
        year_data = df.loc[str(yr)] if not df.empty else _pd.DataFrame()
        if year_data.empty:
            continue
        first_close = float(year_data.iloc[0]["Close"])
        last_close = float(year_data.iloc[-1]["Close"])
        if first_close and last_close:
            cal[str(yr)] = (last_close / first_close) - 1.0
    if cal:
        return {y: cal[y] for y in sorted(cal.keys())}
    return None


def get_funds_data(tickers: List[str]):
    import yfinance as yf

    funds: List[Dict[str, object]] = []
    for idx, symbol in enumerate(tickers):
        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
            hist = t.history(period="max", actions=False)
            hist = hist[hist["Close"].notna()]
            today = hist.index[-1].date() if not hist.empty else _dt.date.today()
            trailing = _calc_trailing(hist, today)
            calendar = _calc_calendar(hist, today)
            overview = _drop_nones(
                {
                    "id": idx,
                    "symbol": symbol,
                    "name": info.get("longName") or info.get("shortName") or symbol,
                    "family": info.get("fundFamily"),
                    "category": info.get("category"),
                    "summary": info.get("longBusinessSummary"),
                }
            )
            address = _drop_nones(
                {
                    "line1": info.get("address2"),
                    "line2": info.get("address1"),
                    "line3": info.get("address3"),
                }
            )
            returns = _drop_nones({**trailing, "calendar": calendar})
            ratings = _drop_nones(
                {
                    "morningstarOverall": info.get("morningStarOverallRating"),
                    "morningstarRisk": info.get("morningStarRiskRating"),
                    "beta3Year": info.get("beta3Year"),
                }
            )
            price = _drop_nones(
                {
                    "nav": info.get("regularMarketPrice") or info.get("previousClose"),
                    "currency": info.get("currency"),
                    "fiftyTwoWeek": _drop_nones(
                        {
                            "low": info.get("fiftyTwoWeekLow"),
                            "high": info.get("fiftyTwoWeekHigh"),
                            "changePct": info.get("fiftyTwoWeekChangePercent"),
                        }
                    ),
                }
            )
            yields = _drop_nones(
                {
                    "distribution": info.get("yield"),
                    "dividendRate": info.get("dividendRate"),
                }
            )
            fund = {
                **overview,
                "address": address or None,
                "inceptionDate": _epoch_to_iso(info.get("fundInceptionDate")),
                "expenseRatio": info.get("annualReportExpenseRatio"),
                "assets": info.get("totalAssets"),
                "price": price or None,
                "yields": yields or None,
                "returns": returns or None,
                "ratings": ratings or None,
                "updated": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
            funds.append({k: v for k, v in fund.items() if v is not None})
        except Exception:
            sys.stderr.write(f"{symbol} failed\n")
    return funds


def main():
    args = _parse_args()
    tickers = _load_tickers(args.tickers_file)
    funds = get_funds_data(tickers)
    doc = {"generated": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z", "funds": funds}
    pathlib.Path(args.output).write_text(json.dumps(doc, indent=2))
    print(f"{len(funds)} funds → {args.output}")


if __name__ == "__main__":
    main()
