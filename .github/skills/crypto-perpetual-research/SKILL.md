---
name: crypto-perpetual-research
description: Keep crypto and tokenized-stock perpetual research statistically, economically, and temporally honest. Use when studying candles, trades, order books, funding, open interest, profiles, execution, or market-regime signals.
---

# Crypto-Perpetual Research Guardrails

This skill governs interpretation and study design, not trading advice or
automatic execution. Treat every candidate as a hypothesis until the relevant
data, costs, and validation are independently established.

## Identify the instrument and what its data represent

- Record venue, product type, underlying/reference asset, quote/settlement
  currency, contract multiplier, symbol identity, and effective dates. Do not
  equate a stock-referenced perpetual with the underlying listed equity, its
  regular-session volume, or its primary-market price.
- Current issuer, ISIN, region, index-feed name, or instrument metadata does
  not establish historical reference-market identity, exchange/MIC, timezone,
  session, holiday, halt, or mapping continuity. Require effective-dated
  source evidence before session-specific comparisons.
- Treat current active symbols as a selected current universe. They do not
  reconstruct historical listings, delistings, renames, halts, survivorship,
  or point-in-time eligibility.
- Keep exchange event time, exchange publication time, and collector receive
  time distinct. Align bars, trades, funding, signals, and costs on explicitly
  defined UTC boundaries and availability times.

## Distinguish market concepts

- A public trade print is an observation, not proof of a complete trade ledger.
  A cursor/page sequence reaching an empty page is endpoint exhaustion under
  that request, not independent evidence of complete historical coverage.
- Candle OHLCV is aggregated data. A candle-volume profile that spreads volume
  across a price range is a modeling approximation, not a trade-at-price
  profile. A whole-window or whole-hour profile is descriptive/ex-post and
  cannot be used as if it were known earlier in that window.
- A book snapshot gives state at an instant; a delta stream requires a valid
  initial snapshot and documented sequence/reset rules. Polling independent
  REST snapshots is not a continuous sequenced order-book recorder.
- A visible order-book wall does not reveal participant intent, hidden
  liquidity, or where stops are located. Do not claim stops can be inferred
  from displayed depth.
- Open interest measures outstanding contracts, not net-long positioning or
  a directional imbalance by itself. Interpret changes alongside price,
  funding, contract rules, and the limitations of available coverage.
- A published funding rate is not an account funding payment. Payment
  attribution requires position direction/size, eligible settlement times,
  account ownership, and applicable historical contract terms.
- Message-weighted spread is not time-weighted liquidity or a realized fill.
  An order-book replay does not establish queue position, market impact, fill
  probability, latency, or an executable historical price.

## Define hypotheses and avoid hindsight

- Specify the rule, long/short direction, timeframe, market group, feature
  lookback, thresholds, entry availability, outcome horizon, and missing-data
  behavior before comparing outcomes.
- Only use information available at the signal time. Use completed bars for
  higher-timeframe context and an as-of join where the feature's close time is
  no later than the entry/signal availability time. Never use a final daily
  high/low, future profile, future outcome, or retrospective failure label as
  an input.
- Keep descriptive market context, predictive features, and retrospective
  outcome labels separate in code and reports.
- If adding exploratory rules after seeing prior results, label them as
  exploratory. Do not silently append them to a frozen family or claim
  preregistration. Version and freeze protocol changes before inspecting
  reserved outcomes.
- Compare against an explicit baseline with the same timestamps, eligibility,
  entry/exit assumptions, and cost treatment. Include zero-event/missing cells;
  do not omit failed symbols, periods, variants, or negative results.
- Separate BTC/ETH, other crypto, and stock-referenced perpetuals when their
  data-generating processes or reference sessions differ. Report coverage and
  sample selection alongside each result.
- Overlapping signals and shared symbol/time shocks are dependent observations.
  Event counts are not independent sample sizes. Select uncertainty methods
  that reflect the dependence and disclose sparse or invalid cells.

## Costs, leverage, and claims

- Distinguish observed fees/quotes/fills from assumed cost scenarios. State
  maker/taker side, entry and exit, spread/slippage, funding, latency,
  contract denomination, and historical applicability. Do not call a
  sensitivity scenario a measured execution cost.
- One-bar forward return, MFE, and MAE are event descriptors, not account P&L,
  a portfolio backtest, or drawdown. Portfolio claims require explicit sizing,
  overlap, cash, exposure, margin, liquidation, funding, and execution rules.
- Leverage scales exposure and loss risk; it is not evidence of signal edge.
  Do not produce personalized position sizing or promise a win rate/profit.
- Report the exact evidence tier: source feasibility, bounded sample,
  exploratory reuse, protocol readiness, empirical validation, or
  execution/portfolio simulation. Never promote one tier into another by
  implication.
- Failed calibration remains failed. A synthetic known-covariance oracle is
  not a practical estimator for unknown market dependence. More simulations,
  a zero count of adjusted rejections, or a passing unit-test suite cannot by
  themselves validate market inference.
- Reserved future folds are unavailable until they actually occur and are
  acquired. Do not shift their dates after seeing outcomes or relabel already
  inspected data as fresh holdout evidence.

## Report conclusions usefully

For every result, state the source and interval, requested versus observed
coverage, rule and baseline, costs, sample/empty cells, validation period,
uncertainty method, and limits. Use “not tested,” “not available,”
“inconclusive,” and “failed” precisely. End with the smallest falsifiable next
step; do not imply that a dashboard display or research result is a trading
recommendation.
