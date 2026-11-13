#!/usr/bin/env python3
"""Polymarket "Next CEO of NVIDIA?" 4-hour-ahead quantile forecaster.

Entry for make.fun bounty polymarket-nvidia-ceo-forecast-01.

Reads every <id>.in case in $MAKEFUN_INPUT_DIR (default /input) and writes
<id>.out to $MAKEFUN_OUTPUT_DIR (default /output). A case holds, per market,
the Yes price at every minute of the 72 hours up to a checkpoint; the output
is, per market, five quantiles (5%, 25%, 50%, 75%, 95%) of the price at each
of the next 240 minutes.

Method (per market, fitted only on the case's own prices, no network):
  * Volatility: sigma is the 90th percentile of the absolute 1-minute price
    moves, rescaled to a normal sigma, averaged over two lookbacks (last
    24h and last 6h) so a fresh burst of moves widens the forecast fast
    while the longer window keeps it stable. Floored at 0.0003 and capped
    at 0.03 per sqrt-minute. Quiet markets get narrow bands, jumpy ones
    wide ones; the house baseline's one-size-fits-all 0.0025 does neither.
  * Shape: Student-t(5) quantiles, whose fatter tails (5%: -2.015 vs the
    normal -1.645) price in the jumps these markets actually make.
  * Horizon: spread grows as h**0.4, not sqrt(h): realised volatility of
    h-step changes grows slower than a random walk because the prices
    mean-revert (the 24 outcomes' Yes prices sum to about 1).
  * Median drift: the outcomes are mutually exclusive, so the sum of the
    24 Yes prices should be ~1. When it is not, each market's median is
    pulled toward its share of 1, linearly over the horizon:
    med(h) = x - (S-1) * (x/S) * (h/240), S = sum of last prices.

Standard library only, deterministic (no randomness, no time, no I/O
besides the case files), well inside 8 s / 1 CPU / 1024 MB per case.
"""

import json
import math
import os
import sys
from statistics import NormalDist

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]
# Student-t with 5 degrees of freedom, quantiles at the five levels.
Z_T5 = [-2.015048, -0.726687, 0.0, 0.726687, 2.015048]
Z90 = NormalDist().inv_cdf(0.95)  # 1.644854, for |N(0,1)| 90th percentile

WINDOW_LONG = 1440   # minutes (24h)
WINDOW_SHORT = 360   # minutes (6h)
SIGMA_FLOOR = 0.0003
SIGMA_CAP = 0.03
ALPHA = 0.4          # spread grows as h ** ALPHA


def clamp6(x):
    """Clamp to [0, 1] and round to 6 decimals (0, never -0)."""
    return round(min(1.0, max(0.0, x)) * 1e6) / 1e6 + 0.0


def q90_sigma(diffs):
    """90th percentile of |diffs|, rescaled to a normal sigma."""
    if not diffs:
        return 0.0
    a = sorted(abs(v) for v in diffs)
    return a[int(0.90 * (len(a) - 1))] / Z90


def market_sigma(prices):
    """Per-market 1-minute sigma: mean of the 24h and 6h q90 estimates."""
    n = len(prices)
    if n < 2:
        return SIGMA_FLOOR
    s_long = q90_sigma([prices[i + 1] - prices[i]
                        for i in range(max(0, n - WINDOW_LONG), n - 1)])
    s_short = q90_sigma([prices[i + 1] - prices[i]
                         for i in range(max(0, n - WINDOW_SHORT), n - 1)])
    sig = 0.5 * s_long + 0.5 * s_short
    return min(max(sig, SIGMA_FLOOR), SIGMA_CAP)


def forecast_market(prices, horizon, quantiles, zscores, sum_last):
    x = prices[-1] if prices else 0.5
    sigma = market_sigma(prices)
    # Share of 1 this market would hold if the 24 prices summed to 1.
    drift = 0.0
    if sum_last > 0.0:
        drift = -(sum_last - 1.0) * (x / sum_last)
    rows = []
    for h in range(1, horizon + 1):
        med = x + drift * (h / horizon)
        sd = sigma * (h ** ALPHA)
        row = [clamp6(med + z * sd) for z in zscores]
        for k in range(1, len(row)):
            if row[k] < row[k - 1]:
                row[k] = row[k - 1]
        rows.append(row)
    return rows


def main():
    input_dir = INPUT_DIR
    output_dir = OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    names = sorted(f for f in os.listdir(input_dir) if f.endswith(".in"))
    for name in names:
        case_id = name[:-len(".in")]
        with open(os.path.join(input_dir, name), "r", encoding="utf-8") as fh:
            case = json.load(fh)
        horizon = max(1, int(case.get("horizon_minutes", 240)))
        quantiles = case.get("quantiles", QUANTILES)
        if list(quantiles) == QUANTILES:
            zscores = Z_T5
        else:
            nd = NormalDist()
            zscores = [nd.inv_cdf(t) for t in quantiles]
        markets = case["markets"]
        sum_last = sum(m["prices"][-1] for m in markets if m.get("prices"))
        forecasts = [
            {
                "id": m["id"],
                "q": forecast_market(m.get("prices", []), horizon,
                                     quantiles, zscores, sum_last),
            }
            for m in markets
        ]
        out_path = os.path.join(output_dir, case_id + ".out")
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"forecasts": forecasts},
                                separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
