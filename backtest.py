#!/usr/bin/env python3
"""stmon v2 백테스트 실행: python3 backtest.py [--lag 1] [--slots 10] [--window 120 ...]"""
import argparse
from modules.engine import load_history, simulate, report
from modules.strategy import Params

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    for f, v in Params().to_dict().items():
        ap.add_argument(f'--{f}', type=type(v), default=v)
    ap.add_argument('--slots', type=int, default=10)
    ap.add_argument('--lag', type=int, default=0, help='0=당일 종가 판단·체결, 1=전일 판단·당일 체결')
    ap.add_argument('--out', default='')
    args = ap.parse_args()
    prm = Params(**{k: getattr(args, k) for k in Params().to_dict()})
    data = load_history()
    r, T, n = simulate(data, prm, slots=args.slots, exec_lag=args.lag)
    report(r, T, f'{prm} slots={args.slots} lag={args.lag}')
    print(f'평균 보유 쌍 수 {n.mean():.1f}, 최대 {n.max()}')
    if args.out:
        T.to_csv(args.out + '_trades.csv', index=False)
        r.to_csv(args.out + '_daily.csv')
