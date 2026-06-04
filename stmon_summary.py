#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stmon_summary.py
stmon(L/S 페어) 의 Open 포지션 합산 Total Exposure / Open P&L 을 계산해
stmon-summary.json 으로 저장한다. (pair-report.html 의 renderTable 계산식 1:1 복제)

shmon index.html 에서 매매여력 계산에 사용:
  매매여력 = (현재담보/0.3 + shmon_pnl + shmon_exposure + stmon_pnl + stmon_exposure) / 3
"""
import json
import re
import math
from datetime import date, datetime
from pathlib import Path

STMON_DIR = Path("/home/ubuntu/stmon")
DATA_DIR = STMON_DIR / "data"
TRENDS_DIR = DATA_DIR / "trends"
OUT_PATH = Path("/home/ubuntu/shmon/web/stmon-summary.json")


def normalize_stock_name(name: str) -> str:
    """pair-report.html normalizeStockName 동일 구현"""
    if not name:
        return ""
    s = re.sub(r"<[^>]+>", "", name).strip()          # HTML 태그 제거
    s = re.sub(r"^[^\w\s가-힣]+", "", s).strip()       # 선두 이모지/기호 제거
    s = re.sub(r"-\d+(\.\d+)?$", "", s).strip()        # 말미 -숫자 제거
    return s


def calc_borrow_fee(entry, qty, borrow_fee_pct, days):
    if not entry or not qty or not borrow_fee_pct or not days:
        return 0
    return entry * qty * (borrow_fee_pct / 100) * (days / 365)


def load_json(p: Path):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def trend_close(common_code):
    """장 마감 후 fallback: trends/{code}.json 의 마지막 종가"""
    try:
        d = load_json(TRENDS_DIR / f"{common_code}.json")
        cc = d.get("common_prices") or []
        pp = d.get("preferred_prices") or []
        return (cc[-1] if cc else None, pp[-1] if pp else None)
    except Exception:
        return (None, None)


def main():
    trades = load_json(DATA_DIR / "pair-trades.json")
    try:
        sd = load_json(DATA_DIR / "stock_data.json")
        signals = sd.get("all_signals", [])
    except Exception:
        signals = []

    # 실시간 가격 매칭용 인덱스
    sig_idx = {}
    for s in signals:
        key = normalize_stock_name(s.get("stock_name", "")).lower()
        if key:
            sig_idx[key] = s

    today_str = date.today().isoformat()

    # 종목(baseName)별 집계
    agg = {}
    for t in trades:
        base = normalize_stock_name(t.get("pair_name", ""))
        a = agg.get(base)
        if a is None:
            a = {
                "status": t.get("status"),
                "common_invested": 0.0,
                "preferred_invested": 0.0,
                "shortPnl": 0.0,
                "longPnl": 0.0,
            }
            agg[base] = a

        if t.get("status") == "Open":
            a["status"] = "Open"

        is_closed = t.get("status") == "Closed"
        common_price = t.get("common_exit")
        preferred_price = t.get("preferred_exit")
        exit_date = t.get("exit_date")

        if not is_closed:
            m = sig_idx.get(normalize_stock_name(t.get("pair_name", "")).lower())
            if m and m.get("price_a") and m.get("price_b"):
                common_price = m["price_a"]
                preferred_price = m["price_b"]
            else:
                cc, pp = trend_close(t.get("common_code"))
                common_price = cc
                preferred_price = pp
            exit_date = today_str

        entry_date = t.get("entry_date")
        last_date = exit_date or today_str
        try:
            days = max(1, (datetime.fromisoformat(last_date) - datetime.fromisoformat(entry_date)).days)
        except Exception:
            days = 1
        borrow_fee_pct = t.get("common_borrow_fee_pct") or 0

        ce = t.get("common_entry") or 0
        cq = t.get("common_qty") or 0
        pe = t.get("preferred_entry") or 0
        pq = t.get("preferred_qty") or 0

        short_equity = ((common_price or ce) - ce) * cq
        long_equity = (pe - (preferred_price or pe)) * pq

        benchmark_rate = t.get("benchmark_rate_pct") or 0
        ss = t.get("common_floating_spread_bps")
        ss = (-202 if ss is None else ss) / 10000
        sl = t.get("preferred_floating_spread_bps")
        sl = (200 if sl is None else sl) / 10000

        short_floating = -round(ce * cq * ((benchmark_rate / 100) + ss) * (days / 365))
        long_floating = round(pe * pq * ((benchmark_rate / 100) + sl) * (days / 365))

        short_pnl = short_equity + short_floating - calc_borrow_fee(ce, cq, borrow_fee_pct, days)
        long_pnl = long_equity + long_floating

        a["common_invested"] += ce * cq
        a["preferred_invested"] += pe * pq
        a["shortPnl"] += short_pnl
        a["longPnl"] += long_pnl

    total_exposure = 0.0
    total_open_pnl = 0.0
    for base, a in agg.items():
        total_pnl = -(a["shortPnl"] + a["longPnl"])
        total_invested = a["common_invested"] + a["preferred_invested"]
        if a["status"] == "Open":
            total_exposure += total_invested
            total_open_pnl += total_pnl

    out = {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_exposure": round(total_exposure),
        "total_open_pnl": round(total_open_pnl),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
    