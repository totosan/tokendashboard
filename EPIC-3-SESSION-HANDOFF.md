# Fresh-session handoff: Epic #3

> Continuation update, 2026-11-04: this handoff has been executed from verified
> base `8070d19`. Read `research/results/state-audit-2026-11-04.json` and the
> 04.11.2026 continuation section in `INTRADAY_RESEARCH.md` before reusing the
> historical queue below. G01/G02/G03 and a bounded two-hour G06 import/replay
> are delivered; G07 has a development-only frozen-arm evaluator. #11/#12's
> own research deliverables are accepted; #14 has an explicit parity/input
> gate. Future validation remains NOT_READY/NOT_RUN. The next bounded action
> is G04 under #13, not redoing these delivered tasks. The original mission
> and scope restrictions below remain applicable.

## Mission

Continue the existing **Epic #3, “Intraday-Einstiege für Krypto und TradFi recherchieren und evaluieren,”** from its issue-defined scope. Reconcile the main issue and every direct child against the live implementation, evidence, and acceptance criteria; maintain truthful issue states; then execute confirmed, in-scope unfinished work. The end goal is a coherent, reproducible repository and an honest issue tree with no stale, duplicate, or unexplained work—not a claim of market efficacy.

Work autonomously without interactive approval for ordinary implementation choices. Do not broaden the research question, add product features, or pursue attractive but unrelated subprojects. An explicit blocker is preferable to fabricated evidence or silently weakened acceptance criteria.

## Start from current truth

1. Inspect `git status`, current branch/remote HEAD, and PR #5 before editing. The handoff was prepared on the existing PR branch `revert-4-copilot/epic-intraday-einstiege-krypto-tradfi`; use its latest remote head as the starting point. Do not reset, discard, or overwrite concurrent changes.
2. Read the live issue #3 body and all direct native children #6–#14, their current labels/comments, and native child relationships. Also check the bounded descendants #15–#25 and the separate deferred #26. Remote issue state may have changed since this handoff.
3. Read the current `INTRADAY_RESEARCH.md`, `research/results/state-audit-2026-11-03.json`, and the three `.github/skills/*/SKILL.md` files. Treat the audit as a verified starting snapshot, not a substitute for rechecking live state.
4. Check current sessions, agents, and research processes before calling anything lost or stuck. An old unavailable handle, an issue labelled `review`, an unchecked closed-story box, or an incomplete summary is not by itself evidence of a lost task.
5. Re-run the existing research tests and fail-closed readiness audit when appropriate. Keep `NOT_READY`, `NOT_RUN`, `FAIL`, and `INCONCLUSIVE` distinct. Do not access or repurpose reserved future outcomes.

## Known baseline from the last verified audit

- Audit and reusable skills were committed to the PR branch through `e846e18`; the exact head may have advanced.
- PR #5 was open and draft, based on the ongoing Epic #3 work. It had no submitted GitHub reviews or reported CI checks at the audit; recheck.
- #3 remains the parent. #6 and bounded stories #15–#25 were closed for their own accepted scopes. #7/#8/#9/#10/#13 remained blocked at their broader acceptance gates. #11/#12/#14 were open in `state:review` for parent acceptance/synthesis, **not because an agent was still reviewing**. #26 is a separate deferred idea, not an Epic #3 child.
- The last full research suite passed 138 tests. The readiness audit correctly remained `NOT_READY` / `NOT_RUN`; the original dependence-calibration result remains `FAIL`, and the synthetic known-covariance candidate remains `INCONCLUSIVE`.
- The existing audit document records 16 candidate gaps G01–G16. Use these as leads, verify against live criteria and code, and do not create duplicate issues for work already owned by an open parent.

## Required working method

### A. Reconcile the epic before coding

Create an internal criterion-to-evidence map from the live #3 acceptance criteria and each child’s own criteria. For every criterion record:

- status: satisfied, partially satisfied, not started, blocked, or out of scope;
- direct source: code/tests/data/report/issue comment and commit;
- what is actually demonstrated versus what is inferred;
- smallest next action and any real prerequisite.

Inspect the repository artifacts, not just issue comments. Correct stale “not started,” “critic pending,” or status claims only after verifying the delivery. Keep bounded child acceptance separate from parent acceptance. Do not close a broad issue because a narrower descendant passed tests.

### B. Keep the storyline narrow

Every action must directly support a stated #3 criterion or a direct child’s acceptance criterion. Before adding work, ask: **Which exact issue criterion does this satisfy, and what evidence will prove it?** If there is no direct answer, do not implement it in this epic.

In particular:

- Do not build an integrated analytics UI, field-journal product, automatic trader, Raspberry Pi service, or continuous WebSocket recorder under #3. #26 remains deferred; these require separate activation/scope.
- Do not buy or introduce a paid data source merely to make the epic appear complete.
- Do not silently add exploratory signal arms to the frozen 11-arm/132-hypothesis protocol. Any protocol amendment must be versioned prospectively and must not inspect reserved outcomes first.
- Do not create a large fleet of agents or issues. Delegate only independent, bounded work that saves meaningful time; preserve one clear owner per gap.
- Keep commits and issue comments focused on the epic. Do not fold unrelated cleanup into research commits.

### C. Act on confirmed remaining work

Start with the cheapest relevant gaps, subject to the live criterion audit:

1. **G02 / parent acceptance:** resolve the stale #11/#12/#14 review queue by checking their actual parent criteria against accepted #17/#18 and the rest of the evidence. Close a parent only if its own criteria are truly satisfied; otherwise document the exact remaining items and state.
2. **G01 / #13:** investigate the twelve CHD trade-versus-official-5m candle open mismatches using unchanged sources, the precise candle/trade time conventions, and adjacent receive-hour objects for late event-time arrivals. Preserve discrepancies; add regression evidence only after the cause is supported.
3. **G03/G06 / #7:** where available from the current local CHD installation, make the bounded sample/acquisition/replay workflow reproducible and validate additional cross-hour/file behavior. Record missing or unavailable inputs honestly; do not treat local-only raw files as portable.
4. **G07 / #8:** the existing readiness checker is not a return evaluator. If it is within the live #8 criteria and safe to proceed, implement the frozen-protocol evaluator using synthetic or already-inspected fixtures only. Do not read reserved future observations.
5. Keep G08–G13 as explicit methodology/data/model gates until their needed estimator, effective-dated references, data, and assumptions are established. Do not manufacture a substitute.
6. G15–G16 remain deferred/separate product scope unless the user creates a separate request.

These are not unconditional instructions to implement every G-item. Recheck ownership, criteria, current evidence, and dependencies first. Prefer finishing or documenting a bounded item over starting many parallel partial tasks.

### D. Maintain truthful issue state

- Preserve the repository label invariant: one `topic:*` and exactly one `state:*` per applicable issue.
- Use `done` only for that issue’s own acceptance criteria. Keep a parent blocked when a real data/method prerequisite is missing; identify who/what can unblock it and the concrete next step.
- Keep #26 outside the Epic #3 dependency chain.
- Publish concise, human-readable progress in the owning issue, with links to reproducible artifacts and limitations. Update `INTRADAY_RESEARCH.md` and the machine-readable audit only when the status materially changes.
- Keep PR #5’s body, branch, issue state, repository docs, and results consistent. Read the live PR body before editing; preserve concurrent edits.

## Completion criteria for this session

Do not equate “clean repository” with deleting useful research artifacts. The repository is clean when:

- the live #3 and child criteria have all been mapped to real evidence or explicit blockers;
- confirmed, safely achievable, in-scope leftovers have been implemented and tested;
- each issue/label accurately reflects its own acceptance status, with stale claims corrected;
- accepted evidence and negative/inconclusive results remain reproducible and are not overwritten;
- no duplicate or tangential subtask has been added;
- the remaining list is short, owned, prioritized, and blocked for specific evidence/reasons where necessary;
- changes are committed and pushed to the intended PR branch, and remote status is checked.

Do not promise that historical validation, practical statistical calibration, point-in-time universes, stock-reference calendars, fills, portfolio/margin simulation, or future folds are complete unless the required evidence is actually obtained and validated. Never mark Epic #3 complete merely because the implementation test suite passes.

## Handoff result to report

At the end, give a concise status: issues reconciled; exactly what was implemented; test/readiness results; what remains and why; current PR/head; whether any real agent/process is stuck; and the single best next step. Link the authoritative audit/results rather than repeating the entire research narrative.
