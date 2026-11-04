---
name: research-epic-orchestration
description: Coordinate research epics, child issues, specialist agents, recovery, reviews, and evidence without losing work or confusing bounded delivery with parent acceptance. Use for multi-issue repository research and status audits.
---

# Research Epic Orchestration

Use this skill when work spans issues, sessions, agents, commits, or research
gates. The goal is a current, traceable state—not merely a collection of
completed subtasks.

## Establish current truth before action

1. Inspect the live issue/PR/session/agent/process state before deciding what
   needs work. Historical comments, checkpoints, tool transcripts, and
   summaries are evidence but can be stale; do not treat them as current
   authorization or status.
2. Read each parent and child acceptance criterion, native parent-child
   relationship, current labels, latest comments, and the actual repository
   artifacts. Confirm the repository branch/worktree and remote PR head.
3. Track live agent and process state separately from issue state. An issue
   marked `review` is not proof that a reviewer is currently running. A
   completed idle agent is not stuck. An unavailable old runtime handle alone
   is not proof of lost work.
4. Call something lost only after checking the assigned task, delivery
   artifacts, messages/comments, current session state, and process state. Use
   retry/escalation labels only when the required attempts and nonresponse are
   actually evidenced; never create a “lost” state to explain missing history.
5. In autopilot, make ordinary bounded decisions without waiting for approval,
   but do not convert unresolved scientific, product, or data assumptions into
   facts. Keep unrelated worktree changes intact.

## Define ownership and dependency

- Keep one clear owner issue for each remaining task. Use the repository's
  native issue hierarchy when available; otherwise document the direct parent
  relationship explicitly. Avoid duplicate continuation issues where a
  specific existing parent already owns the work.
- Separate a bounded deliverable from the broader parent gate. A story may be
  accepted and closed for feasibility, code, tests, or a pilot while the
  parent remains blocked on coverage, model inputs, or validation. State the
  exact accepted scope and the remaining gate in both status updates.
- Record real prerequisites, not just queue order. Distinguish work that can
  proceed on existing/synthetic fixtures from work blocked on source access,
  model decisions, or future observations.
- Separate deferred ideas from active epics. Do not add hardware deployment,
  a new product UI, paid data, or production changes to the active scope by
  implication.
- Maintain the repository's label convention, including exactly one topic and
  one state label when that convention applies. Verify the invariant after
  editing.

## Delegate and review honestly

- Give each agent a bounded, self-contained task with inputs, output path,
  success criteria, evidence limits, and stop condition. Delegate only work
  that benefits from separate context; do not split a single continuous trace
  just to create parallelism.
- Record whether a reviewer was actually started, whether it completed, and
  what it inspected. A subagent critique is not automatically a submitted
  GitHub review or approval.
- Recover incomplete work by inspecting saved files, commits, test results,
  and issue comments before rerunning it. Preserve valid artifacts and
  accepted work; do not relabel or redo a completed task because its original
  agent handle disappeared.
- A review of a bounded component does not constitute final review/acceptance
  of the parent epic. List the remaining domains and prerequisites explicitly.

## Prevent stale tracking and publication gaps

- Reconcile issue comments and session todos with accepted commits/results.
  Replace stale “not started,” “review pending,” or “critic pending” statements
  when delivery is verified, while retaining open parent acceptance and
  empirical gates.
- A closed issue's unchecked body boxes are not, by themselves, proof of
  missing work; inspect its acceptance comment and repository delivery. Do not
  mark broad parent checklists complete merely because bounded children are
  closed.
- Keep the issue, repo synthesis, machine-readable artifact, PR body, and
  session task states consistent. If one update is interrupted, inspect which
  side effects succeeded before retrying to avoid duplicate comments or
  overwriting a concurrent PR edit.
- Before updating a PR body, read the current body and merge the new status
  with it. Use a concurrency guard where available, and re-read the remote
  head/body after publishing.
- Commit and push audit artifacts before stating that they are durable.
  Verify the target remote branch, clean/expected worktree, current PR head,
  issue comment URLs, labels, and required tests.
- Keep issue updates concise and link the detailed report or machine-readable
  backlog. Document unknowns as unknown rather than asserting no process or
  issue exists outside the visible scope.

## Make the backlog actionable

For each leftover, record:

- stable backlog ID and owning issue;
- relative effort (not an invented time estimate);
- exact next action and required evidence;
- status: ready, blocked, review queued, future-data-dependent, or deferred;
- true dependencies and what may proceed in parallel.

Prioritize cheap diagnostic work that resolves a concrete discrepancy, then
portable/reproducible data paths, then bounded evaluators and larger data or
methodology gates. Keep fresh data and statistical validity as explicit gates;
do not declare the epic complete just because all current code tests pass.

## Finish with a truthful handoff

Report whether any actual process/agent needs attention, what bounded work is
complete, what remains, the first recommended next step, test/readiness status,
and where the persistent backlog lives. Distinguish repository-persisted
changes from local session artifacts. Do not claim the entire epic is done if
its acceptance criteria, future observations, or model prerequisites remain
open.
