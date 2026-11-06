# Bitget public market-data recorder (issue #26, dependency of #7)

Forward-only recorder of **public** Bitget USDT-FUTURES data for `AAPLUSDT` and `BTCUSDT`
(configurable via `--symbols`). Sampled REST snapshots, **not** a continuous L2 feed and no
historical backfill. No API keys, public `GET` only, no redirects followed.

Per symbol and cycle: order book (top `--depth` levels, default 50, `/api/v3/market/orderbook`) and
ticker (`/api/v2/mix/market/ticker`). On cycle 1 and every `--slow-every` cycles (default 30):
funding rate (`current-fund-rate`) and contract/fee config (`contracts`: maker/taker fee rate,
size multiplier, precision, status).

## Daily contract inventory (point-in-time universe)

Bitget offers no historical contract catalogue (support answer 2026-11-05, see
`research/data/bitget-support-bot-answer-2026-11-05.json`), so the recorder snapshots the full
`GET /api/v2/mix/market/contracts?productType=USDT-FUTURES` (all symbols) at the first cycle of a
run and then at most once per UTC day, as a record with `kind: "inventory"` (symbol `ALL`) in the
normal hashed hourly gzip-JSONL partitions (raw response + `raw_response_sha256` +
`record_sha256`; `fields` hold `symbol_count`, `status_counts`). `_meta/inventory_state.json`
stores the last UTC date so restarts do not repeat it; a failed snapshot is reported in the run
summary and retried on the next run. One extra request per day.

Compare consecutive snapshots (added/removed symbols, changes of `symbolStatus`, `offTime`,
`limitOpenTime`, `launchTime`, `deliveryTime`):

```
python3 -m research.recorder.inventory_diff DIR
```

Tests: `python -m unittest research.recorder.test_recorder research.recorder.test_inventory`.

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

## Sentiment / open-interest kinds (slow schedule)

Recorded every `--slow-every` cycles (default 30, always cycle 1) next to `funding`/`contract`,
public GET only: `open_interest` (`open-interest`), `long_short`, `account_long_short`,
`position_long_short`, `taker_buy_sell` (`/api/v2/mix/market/...`, `period=5m`). Normalized
`fields`: `open_interest`; `long_ratio`/`short_ratio`/`long_short_ratio` (and the `*_account_*`,
`*_position_*` variants); `buy_volume`/`sell_volume`; plus `period` and `points`. For series kinds
`event_ms` is the latest 5m bucket; the full series stays in `raw_response` (sha256 as usual).

Bitget answers HTTP 400 + code `40054` ("data is empty") for symbols without this data (e.g.
AAPLUSDT long/short). That is an expected outcome, not a failure: one compact record with
`fields.no_data = "true"` is stored per run and symbol/kind, the pair is not requested again in
that run, there are no retries, and the exit status is unaffected (`summary.no_data` lists them).

**Caveats:** these are exchange-reported aggregates at 5m granularity, sampled every few minutes,
not tick data; the exchange's population and method are not documented. Narrative rules such as
"long/short > 70% => squeeze" are **UNTESTED** and must be evaluated under a pre-registered
protocol before any use.

## Storage

`<output-dir>/YYYY/MM/DD/HH/records.jsonl.gz` (UTC hour of `available_ms`). Each write appends one
complete gzip member with `O_APPEND` + `fsync`; existing bytes are never rewritten (concatenated
members are valid gzip). A crash can at worst leave a truncated final member, which is quarantined and truncated on the
next start (see power-loss behaviour) and otherwise flagged by the integrity report. Data is never committed: point `--output-dir` outside the repo (e.g.
`/var/lib/bitget-recorder`).

**Estimate** (2 symbols, 5 s interval, 50 levels): ~1.5 KB raw book + ~0.6 KB ticker per symbol per
cycle, ~0.5–0.8 KB per gzip member (small members compress modestly) → roughly 40–60 MB/day,
~1.5 GB/month. Lower with a larger `--interval`, smaller `--depth`, or by recompressing closed hours
(`zcat` then `gzip -9`) offline. Verify on your device with `du -sh`.

## Storage and memory guard (stable under low capacity)

At the start of a run and every 30 s the recorder checks free disk on the output volume and
`MemAvailable`, and logs every level change to `_meta/events.jsonl` (also `_meta/storage_status.json`).
Level = worst of disk and memory (`--disk-free-mb`, `--mem-available-mb`, each `WARN,DEGRADED,CRITICAL`):

| Level | Default disk free / mem avail | Behaviour |
|---|---|---|
| ok | >= 2048 MB / >= 96 MB | collect everything |
| warn | < 2048 / < 96 | collect everything, event logged |
| degraded | < 1024 / < 48 | shed lowest-priority data: sentiment kinds dropped, order-book depth capped at 10; order book, ticker, funding, contract/fee and inventory kept |
| critical | < 256 / < 24 | stop writing (`stop_reason=STORAGE_CRITICAL`, clean marker written); the next timer run re-checks and resumes automatically once space is freed |

Shed data is simply absent (a gap), never interpolated; the coverage report excludes it. Existing
data is never deleted automatically — free space by archiving closed hours off the device. Unknown
readings are treated as ok. Thresholds must satisfy WARN >= DEGRADED >= CRITICAL.

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
sudo apt install python3 python3-venv git
git clone https://github.com/totosan/tokendashboard && cd tokendashboard
git checkout revert-4-copilot/epic-intraday-einstiege-krypto-tradfi
sudo bash research/recorder/install_pi.sh
```

`install_pi.sh` is idempotent (safe to re-run to update code). It creates the non-root system user
`bitget-recorder`, copies the code root-owned to `/opt/bitget-recorder/app`, builds a venv (stdlib
only, nothing to download), installs the service + timer, runs a bounded smoke test
(`timeout 60`, 1 cycle, scratch dir that is deleted afterwards) and only then enables the timer. It
uses no secrets and opens no listening sockets (outbound public HTTPS only). Data goes to
`/var/lib/bitget-recorder`.

The service is a bounded `Type=oneshot` run (≈280 s, `RuntimeMaxSec=300`); the timer starts one every
5 minutes, so the Pi never runs an unbounded daemon. Gaps of ~20 s between runs are expected; they
stay below the default 60 s gap limit and do not reduce coverage.

## Hardware and operations

- **SSD vs SD card:** the recorder fsyncs every write (~0.5 writes/s per stream). SD cards wear out
  and corrupt under sustained small writes; use a USB SSD (mount it at `/var/lib/bitget-recorder`)
  for anything beyond a trial. On SD, expect a shorter life and keep backups.
- **UPS:** a small UPS/HAT lets the Pi shut down cleanly. Without one, power loss is survivable
  but costs data (see below).
- **NTP:** `available_ms` is the Pi clock. Keep `timedatectl` at `NTP synchronized: yes`; the Pi has
  no RTC, so after boot the clock is wrong until NTP syncs. Every record stores `clock_sync`
  (`ntp_synchronized` true/false/null from `timedatectl`, null = unknown) and `clock_skew_ms`.
  The report counts records written while unsynchronized (`ntp_unsynchronized_records`); treat
  those windows with suspicion or exclude them.
- **Power-loss behaviour:** each record is one gzip member written with `O_APPEND` and `fsync`
  (plus directory fsync on file creation), so at most the in-flight record is lost. A crash can
  leave a torn trailing member. On the next start the recorder: looks for the clean-shutdown marker
  (`_meta/clean_shutdown.json`, written **only** on normal finish or graceful SIGTERM/SIGINT stop;
  deleted at start), and if it is missing treats the previous run as unclean, scans the newest two
  partitions, copies the torn tail to `_meta/quarantine/` and truncates the partition to the last
  valid member, logs everything, and records a `startup` event (`previous_shutdown`:
  `clean`/`unclean`/`first_run`, `recovered_partitions`, `clock_sync`) in `_meta/events.jsonl`.
  The unfinished window is a gap, not repaired data. SIGKILL and power loss are "unclean".

## How to verify

```
systemctl list-timers bitget-recorder.timer; journalctl -u bitget-recorder -n 30 --no-pager
timedatectl show -p NTPSynchronized --value
cd /opt/bitget-recorder/app && /opt/bitget-recorder/venv/bin/python -m research.recorder.integrity_report /var/lib/bitget-recorder
tail -n 5 /var/lib/bitget-recorder/_meta/events.jsonl
```

## Integrity and gap report

```
python3 -m research.recorder.integrity_report /var/lib/bitget-recorder --max-gap-seconds 60
```

Read-only. Verifies every gzip partition decompresses, `record_sha256` and `raw_response_sha256`
match, reports duplicates, backward exchange timestamps, per-stream counts, and gaps larger than
`--max-gap-seconds` between consecutive orderbook/ticker samples. Exit 1 on corruption.

### Coverage and gaps

For each stream the report computes `coverage_pct` per UTC hour and per UTC day: time between
consecutive samples counts as covered only if the gap is `<= --max-gap-seconds`; the denominator is
the stream's observed span within the bucket (partial first/last buckets are not penalised).
Buckets below `--min-coverage-pct` (default 95) land in `low_coverage_buckets`; gaps are listed with
`action: EXCLUDE`. Exit codes: 0 ok, 1 corruption, 3 coverage below threshold. It also reports
unclean startups and recovered partitions from `_meta/events.jsonl`.

**Gap windows (and low-coverage buckets) must be excluded from analysis, not interpolated or
forward-filled.** Missing market data stays missing.

## Tests

`python3 -m unittest research.recorder.test_recorder` (mocked HTTP only, no network; includes torn-file recovery, marker and coverage tests).
