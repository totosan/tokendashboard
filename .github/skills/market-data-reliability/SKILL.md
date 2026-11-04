---
name: market-data-reliability
description: Prevent market-data research failures caused by API semantics, partitioning, replay state, time boundaries, local-only artifacts, interrupted tools, and misleading validation status. Use when acquiring, comparing, replaying, or documenting exchange/CHD data.
---

# Reliable Market-Data Workflows

Use this skill before downloading or interpreting market data, and whenever a
tool call, process, or artifact appears stuck, partial, or inconsistent.

## Before acquisition

1. Establish the exact venue, product/market, dataset, symbol spelling, UTC
   interval, and intended use. Distinguish discovery/catalog availability from
   observed data coverage.
2. Read current official provider documentation and inspect the installed
   client/SDK version and signatures. Do not infer request methods, endpoints,
   schemas, timestamp units, or supported semantics from a marketing page,
   enum, URL shape, or another provider's behavior.
3. Begin with a bounded sample. Record the request parameters, retrieval time,
   response status, byte count, schema, row count, timestamp ranges, source
   object path, and content hash. Preserve failed, missing, and empty objects
   as distinct outcomes. Never claim interval completeness from a successful
   response or symbol listing alone.
4. Bound request count, bytes, memory, row count, and wall time. Use documented
   retry limits and honor provider backoff. Do not retry an invalid or rejected
   request indefinitely, or send an undocumented write/POST merely to discover
   an endpoint contract.
5. Keep credentials out of source, logs, URLs, reports, and saved request
   headers. Use the user's existing supported authentication method; do not
   create or rotate credentials unless explicitly required and authorized.

## Preserve data and time semantics

- Keep exchange/event time and local/provider receive time as separate fields.
  State which clock controls each window, bar, availability timestamp, and
  ordering decision. Test late arrivals at hour/day boundaries using adjacent
  receive-time partitions where available.
- Treat provider file partitions as storage boundaries, not event-time
  boundaries. A file can contain late events, and an event-time window can
  require neighboring receive-time objects. Report what was queried and what
  was obtained.
- Preserve raw values. Parse prices, quantities, and integer timestamps without
  lossy floating-point conversions where precision matters. Document duplicate
  handling, ordering ties, half-open intervals, missing periods, and units.
- Do not silently fill missing observations with zero, mutate source data to
  force a comparison, or discard a mismatch. Explain the observed difference
  and test plausible conventions against source evidence.
- A candle open, last trade in a bucket, first trade by event time, and first
  received trade need not be equivalent. Compare exact window boundaries,
  timestamp basis, sorting, and late-arrival behavior before attributing an
  open mismatch.

## Order-book snapshots and replay

- Distinguish an initial snapshot from incremental updates. A delta-only file
  does not establish a starting book; do not initialize an apparently complete
  book from empty state or fabricate a checkpoint.
- Follow the specific wire format: group rows into provider messages before
  checking message sequence; apply snapshot replacement, update replacement or
  deletion, and no-op behavior exactly as documented. A gap or invalid chain
  invalidates state until a valid reset/snapshot according to provider rules.
- Validate predecessor/current sequence fields, monotonic receive time,
  duplicate/conflicting updates, crossed/invalid books, and any documented
  checksum. State explicitly when checksum or independent completeness
  certification is unavailable.
- A replay that is internally consistent within one file is not proof of
  complete levels, continuity with the prior hour, provider correctness, or
  executable fills. A separately dated recent book does not repair a historical
  start-state gap.
- Carry state across files only when sequence continuity, symbol/product,
  source provenance, clock ordering, and checkpoint compatibility are
  explicitly validated. If the tool can export but not validate/import a
  checkpoint, disclose that it cannot perform a chained replay.

## Artifacts and reproducibility

- Separate committed code/results from local raw data and user-level
  environments. A report that depends on a local path is not automatically
  portable. Record required package versions, commands, object identifiers,
  hashes, and missing local inputs; provide a bounded reacquisition procedure
  where permitted.
- Do not commit raw/private data or credentials just to make a local run
  portable. Use repository-approved small fixtures or public reproducible
  inputs.
- Check the repository status before editing; preserve unrelated user changes.
  After edits, run the smallest relevant test, then verify the exact output and
  diff. Keep temporary research output outside tracked paths unless the task
  requires durable artifacts.
- A readiness/audit command is not an evaluator. Interpret its documented
  status and exit behavior. A deliberate fail-closed exit (for example, exit
  code 2 with `NOT_READY` / `NOT_RUN`) is not a successful empirical
  validation; do not describe it as a product failure or passing result.

## Interrupted calls and process recovery

1. If a tool reports interruption or times out, do not immediately repeat a
   write, download, recording session, or broad batch: first inspect the
   worktree, remote state, active processes/shell sessions, and output
   manifests. A timed-out caller does not prove its child operation stopped.
2. Retry only the missing bounded step after confirming whether the first
   attempt had side effects. Use a unique output path and idempotent operation
   where possible.
3. Keep tool batches to independent, modest groups. If a large parallel batch
   itself is interrupted, resume with a few targeted calls rather than
   replaying the entire batch.
4. Inspect the specific PID/session handle before stopping anything. Never
   kill by process name or terminate a process that may belong to another
   task/user. Do not infer a live stuck process from an old terminal wait.
5. Report uncertainty plainly: say what was observed, what could not be
   verified, and which evidence supports the conclusion. Do not claim a
   process, download, test, or remote edit succeeded without checking its
   resulting state.
