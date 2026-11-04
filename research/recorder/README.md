# Bitget public market-data recorder (issue #26, dependency of #7)

Forward-only recorder of **public** Bitget USDT-FUTURES data for `AAPLUSDT` and `BTCUSDT`
(configurable via `--symbols`). Sampled REST snapshots, **not** a continuous L2 feed and no
historical backfill. No API keys, public `GET` only, no redirects followed.

Per symbol and cycle: order book (top `--depth` levels, default 50, `/api/v3/market/orderbook`) and
ticker (`/api/v2/mix/market/ticker`). On cycle 1 and every `--slow-every` cycles (default 30):
funding rate (`current-fund-rate`) and contract/fee config (`contracts`: maker/taker fee rate,
size multiplier, precision, status).

## Record format (JSONL, one per request, schema_version 1)

`instrument` (venue/product/symbol/quote/settlement), `kind`, `event_ms` (**exchange** clock),
`available_ms` (**local** receive clock; maps to #7 `available_ms`), `request_started_ns`,
`received_ns`, `clock_skew_ms`, `fields` (normalized strings: `bid`, `ask`, `bid_quantity`,
`ask_quantity`, `maker_fee_rate`, `funding_rate`, ...), the verbatim `raw_response`,
`raw_response_sha256`, and `record_sha256` over the whole record. Names follow the Quote / Fee /
Funding rows of `research/execution_readiness.py` (decimal strings, integer UTC ms), so rows can be
mapped to the contract without guessing. Mapping notes: a #7 `Source` should cite the partition
file (sha256 of the file) plus a `path:line` locator; Bitget `sizeMultiplier` (e.g. `0.01` for
AAPLUSDT) is the exchange value and must be reconciled with the contract's `contract_multiplier`;
fees are the account-independent public contract rates, not an account's VIP tier.

## Storage

`<output-dir>/YYYY/MM/DD/HH/records.jsonl.gz` (UTC hour of `available_ms`). Each write appends one
complete gzip member with `O_APPEND` + `fsync`; existing bytes are never rewritten (concatenated
members are valid gzip). A crash can at worst leave a truncated final member, which the integrity
report flags. Data is never committed: point `--output-dir` outside the repo (e.g.
`/var/lib/bitget-recorder`).

**Estimate** (2 symbols, 5 s interval, 50 levels): ~1.5 KB raw book + ~0.6 KB ticker per symbol per
cycle, ~0.5–0.8 KB per gzip member (small members compress modestly) → roughly 40–60 MB/day,
~1.5 GB/month. Lower with a larger `--interval`, smaller `--depth`, or by recompressing closed hours
(`zcat` then `gzip -9`) offline. Verify on your device with `du -sh`.

## CLI (always finite)

```
python3 -m research.recorder.recorder --output-dir DIR --max-cycles 50 --interval 5 \
    --duration-seconds 280 [--symbols AAPLUSDT,BTCUSDT] [--depth 50] [--slow-every 30] \
    [--min-request-gap 0.25] [--retries 2]
```

Hard caps: `--max-cycles` (≤100000) and `--duration-seconds` (≤86400) stop the run, whichever comes
first. Requests are spaced by `--min-request-gap` (default 4 req/s max), retried at most
`--retries` times with exponential backoff, and time-limited. SIGTERM/SIGINT finish the current
write and exit cleanly (`stop_reason: SIGNAL`). Exit status 0 = all records written, 2 = partial
failures, 1 = nothing recorded. A JSON run summary is printed.

## Raspberry Pi setup

```
sudo apt install python3 git
git clone https://github.com/totosan/tokendashboard /home/pi/tokendashboard
cd /home/pi/tokendashboard && git checkout revert-4-copilot/epic-intraday-einstiege-krypto-tradfi
sudo install -d -o pi -g pi /var/lib/bitget-recorder
sudo cp research/recorder/systemd/bitget-recorder.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now bitget-recorder.timer
systemctl list-timers bitget-recorder.timer; journalctl -u bitget-recorder -n 30
```

The service is a bounded `Type=oneshot` run (≈280 s, `RuntimeMaxSec=300`); the timer starts one every
5 minutes, so the Pi never runs an unbounded daemon. Gaps of a few seconds between runs are
expected and show up in the gap report. Use an SD-card-friendly location (or USB SSD) and a
reliable clock (`timedatectl` shows NTP synchronized; `clock_skew_ms` records drift).
Python 3.9+ and only the standard library are required.

## Integrity and gap report

```
python3 -m research.recorder.integrity_report /var/lib/bitget-recorder --max-gap-seconds 60
```

Read-only. Verifies every gzip partition decompresses, `record_sha256` and `raw_response_sha256`
match, reports duplicates, backward exchange timestamps, per-stream counts, and gaps larger than
`--max-gap-seconds` between consecutive orderbook/ticker samples. Exit 1 on corruption.

## Tests

`python3 -m unittest research.recorder.test_recorder` (mocked HTTP only, no network).
