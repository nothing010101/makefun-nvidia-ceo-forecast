# NVIDIA CEO Polymarket Forecaster

Entry for the [make.fun bounty](https://make.fun/bounty/polymarket-nvidia-ceo-forecast-01)
"Forecast Polymarket's next NVIDIA CEO prices minute by minute, 4 hours ahead".

`main.py` (Python 3.13, standard library only) reads every `<id>.in` case in
`$MAKEFUN_INPUT_DIR` (default `/input`) — per market, the Yes price at every
minute of the 72 hours up to a checkpoint — and writes `<id>.out` to
`$MAKEFUN_OUTPUT_DIR` (default `/output`): for each market and each of the
next 240 minutes, five quantiles (5%, 25%, 50%, 75%, 95%) of that minute's
price. It runs offline, is deterministic, and takes ~0.1 s per case.

## Method

Per market, fitted only on the case's own prices:

- **Volatility:** sigma is the 90th percentile of the absolute 1-minute
  price moves, rescaled to a normal sigma, averaged over two lookbacks
  (last 24h and last 6h). A fresh burst of moves widens the forecast fast
  while the longer window keeps it stable. Floored at 0.0003, capped at
  0.03 per sqrt-minute. Quiet markets get narrow bands, jumpy ones wide
  ones — the house baseline's one-size-fits-all 0.0025 does neither.
- **Shape:** Student-t(5) quantiles, whose fatter tails (5%: −2.015 vs the
  normal −1.645) price in the jumps these markets actually make.
- **Horizon:** spread grows as h**0.4, not sqrt(h): realised volatility of
  h-step changes grows slower than a random walk because the prices
  mean-revert (the 24 outcomes' Yes prices sum to about 1).
- **Median drift:** the outcomes are mutually exclusive, so the sum of the
  24 Yes prices should be ~1. When it is not, each market's median is
  pulled toward its share of 1, linearly over the horizon:
  `med(h) = x − (S−1)·(x/S)·(h/240)`, `S` = sum of last prices.

## Local practice score

Scored on the kit's six practice cases against the actual prices fetched
from Polymarket's public price history (same 1-minute grid rule as the
house), mean pinball loss in percentage points:

| forecaster | practice loss |
|---|---|
| house baseline (fixed sigma 0.0025) | 0.363589 |
| **this entry** | **0.269316** |

Per case: p00 0.427, p01 0.307, p02 0.378, p03 0.258, p04 0.202, p05 0.107.
(The practice pays nothing and is no guide to the final; it only shows the
entry beats the house baseline by a wide margin.)

## Run it

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

## License

MIT. See `LICENSE`.
