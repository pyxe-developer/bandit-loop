# Bandit Conveyor Preflight Proof

**Verdict: PASS (4/4 drills). The conveyor may run real tickets in this environment.**

## Environment / provider identity

- Codex code-mode host: `codex-code-mode-host` **0.144.0** (darwin-arm64), binary sha256
  `978740e6bcbd9af2f850823b723fb74f16d8d1e44de05f7dd6737ae631f72017`, at
  `~/.traycer/host/install/host-runtime/resources/providers/codex/darwin-arm64/`
- Scorekeeper model: Traycer harness `codex`, **`gpt-5.6-luna`**, reasoning effort **`max`**
- Protocol: `/Users/matthewflebbe/.traycer/bandit/protocol.md` sha256
  **`953472d9cd760154011414209c52f1a00bbe689618128f9241f6980688986d77`**

## Timestamp

2026-07-10T13:13:58-0400 (drills executed 13:00–13:13 EDT)

## Drill evidence

Full report: `/Users/matthewflebbe/.traycer/epics/58a18fe0-5136-4d4e-a4e6-1774ca6a2098/artifacts/tickets/preflight-drills/preflight-report/index.md`
Drill ledger (11 entries, final sha256 prefix `cfaf0c620acfe1d3`):
`/Users/matthewflebbe/.traycer/epics/58a18fe0-5136-4d4e-a4e6-1774ca6a2098/artifacts/tickets/preflight-drills/conveyor-ledger/index.md`
Scorekeepers: epoch 1 `7d20f7e3-dce0-48be-8c2e-19093eae5bf7`, epoch 2 `0c8daaa4-2644-4483-8253-869a3831b768`.

1. **Full handshake round-trip — PASS.** Ledger seq 1–2: bootstrap `enter_conveyor` proposal →
   ledger instantiated from template → decision `YES` → real action (worktree + snapshot in
   `/tmp/bandit-preflight-scratch`) → `result_close` succeeded, subject bound to pinned SHA
   `5612d68a93fabe34ac5d93852739ff364cd3c62a`.
2. **Scorekeeper replacement — PASS.** Ledger seq 3–5: outstanding action at takeover;
   `scorekeeper_replacement` (epoch 2, reason stalled-turn, `outstanding_at_takeover: 3`) then
   mandatory `reconciliation` (`supersedes_results_for: [3]`) before any new authorization.
   (Stall itself was declared by fiat — a healthy agent can't be made to organically time out.)
3. **Old-writer resurrection/fencing — PASS (strong branch).** Replaced epoch-1 agent, sent a
   late "succeeded" result with a fabricated artifact ref, replied
   `NO APPEND: epoch 1 fenced by scorekeeper_replacement sequence 4` and wrote zero bytes
   (ledger sha256 identical before/after: `57378adb…`). The correction fallback was not needed.
4. **Torn-ledger recovery — PASS.** Final entry truncated mid-write (byte 4985/5289); next-turn
   tail validation appended `correction` (seq 6, torn-tail — voided the torn entry AND
   conservatively re-opened the action it covered), fresh `reconciliation` (seq 7), then the
   pending decision (seq 8). Damaged region preserved verbatim; recovery entirely append-only.
   Unplanned bonus: seq 9 out-of-order append self-detected and voided via seq 10 `correction`,
   re-closed at seq 11.

## Validity

This proof covers exactly the environment identified above. **Invalidated by:** any
codex-code-mode-host or Traycer host-runtime update, a scorekeeper model/effort change, or any
edit to protocol.md (hash mismatch). On invalidation, re-run Drill 1 at minimum (comms regressed
once before — binary mismatch, 2026-07-10 morning); a protocol change re-runs all four.
