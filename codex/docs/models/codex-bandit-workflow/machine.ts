/**
 * Codex Bandit work-item workflow — deterministic transition function.
 *
 * This is the state-machine spine of the hybrid model (see MODEL.md). It is
 * PURE: no I/O, no LLM calls, no clock. It does NOT recompute the evidence
 * reducer — the reducer (decision-table.md) runs as `verify-stage` and its
 * derived status is carried on the event payload. The machine only decides the
 * next state + the side-effect commands to enact. Effects are descriptions, not
 * executions (12-factor: deterministic workflow code decides; the caller runs
 * the effect). Unknown (state,event) pairs are rejected by default.
 *
 * IDs (STATE-*, EVT-*, T-*, GUARD-*, FX-*) trace to transitions.md / invariants.md.
 */

// ---------- States (STATE-000..011) ----------
export type StageId =
  | "plan" | "red" | "green" | "adversarial"
  | "prepare_pr" | "hitl_merge_checkpoint" | "land_deploy" | "closeout";

export type Lifecycle =
  | "planned" | "active" | "blocked" | "repairing"
  | "ready_for_review" | "approved" | "changes_requested"
  | "deferred" | "abandoned" | "complete";

export type DeliveryState =
  | "not_started" | "pr_prepared" | "awaiting_hitl_merge_approval"
  | "merge_approved" | "merged" | "deployed"
  | "delivery_deferred" | "delivery_blocked";

export type State =
  | { kind: "NotCreated" }
  | { kind: "Stage"; stage: StageId; lifecycle: Lifecycle; delivery: DeliveryState;
      budget: { maxTotal: number; usedTotal: number } }
  | { kind: "Complete" }
  | { kind: "ManualContinuation"; nextAction: string }
  | { kind: "Abandoned" };

// Reducer status handed in by verify-stage (decision-table.md).
export type ReducerStatus =
  | "not_started" | "pass" | "fail" | "changes_requested"
  | "cannot_judge" | "blocked" | "stale" | "deferred";

// ---------- Events (EVT-*) ----------
export type Event =
  | { type: "create_work_item"; routeCardValid: boolean } // EVT-001
  | { type: "route_card_validated"; enforcedValidated: boolean } // EVT-002 (GUARD-012)
  | { type: "red_result"; reducer: ReducerStatus } // EVT-004 (GUARD-002 folded into reducer)
  | { type: "green_result"; reducer: ReducerStatus; forbiddenTestEdit: boolean } // EVT-005
  | { type: "verdict_result"; verdict: "approve" | "changes_requested" | "cannot_judge";
      reducer: ReducerStatus; budgetLeft: boolean; missingWorkProduct: boolean } // EVT-006/015
  | { type: "provider_failure" } // EVT-016
  | { type: "prepare_pr_result"; reducer: ReducerStatus; prAuthorized: boolean } // EVT-008 (GUARD-008)
  | { type: "hitl_merge_approval"; headMatches: boolean; reviewedHeadMatches: boolean } // EVT-009 (GUARD-009/016)
  | { type: "land_deploy_result"; merged: boolean; deployBlocked: boolean } // EVT-010
  | { type: "closeout_result" } // EVT-011
  | { type: "reroute_to_test_writer"; budgetLeft: boolean } // EVT-013
  | { type: "manual_patch_authorized"; authorized: boolean } // EVT-018 (GUARD-015)
  | { type: "user_waiver"; scopedAndLegal: boolean } // EVT-019
  | { type: "defer_delivery" } // EVT-017
  | { type: "exit_orchestration"; mode: "abandon" | "manual" }; // EVT-020

// ---------- Effects (FX-*) as commands ----------
export type Effect =
  | { fx: "append_evidence"; note: string }        // FX-001
  | { fx: "run_verify_stage"; stage: StageId }      // FX-002
  | { fx: "update_route_card"; note: string }       // FX-003
  | { fx: "build_review_package" }                  // FX-005
  | { fx: "dispatch_role"; role: string }           // FX-006
  | { fx: "consume_budget" }                         // FX-007
  | { fx: "record_blocker"; code: string; ownerRole: string } // FX-008
  | { fx: "github_op"; op: "push" | "create_pr" | "merge" } // FX-009
  | { fx: "deploy_and_health" }                     // FX-010
  | { fx: "supersede_stale_review" }                // FX-011
  | { fx: "stop_with_next_action"; nextAction: string } // FX-012
  | { fx: "warn"; code: string }                    // FX-013
  | { fx: "fail_closed"; code: string }             // FX-014
  | { fx: "reject"; code: "E_UNSUPPORTED_TRANSITION" };

export type TransitionResult = { state: State; effects: Effect[] };

const stage = (
  s: StageId, lifecycle: Lifecycle, delivery: DeliveryState,
  budget: { maxTotal: number; usedTotal: number },
): State => ({ kind: "Stage", stage: s, lifecycle, delivery, budget });

const reject = (state: State): TransitionResult => ({
  state,
  effects: [{ fx: "reject", code: "E_UNSUPPORTED_TRANSITION" }],
});

export function transition(state: State, event: Event): TransitionResult {
  // T-001
  if (state.kind === "NotCreated") {
    if (event.type === "create_work_item") {
      if (!event.routeCardValid) return reject(state); // GUARD-001 -> FM-001
      return {
        state: stage("plan", "planned", "not_started", { maxTotal: 3, usedTotal: 0 }),
        effects: [{ fx: "append_evidence", note: "plan" }, { fx: "update_route_card", note: "create" }],
      };
    }
    return reject(state);
  }

  if (state.kind !== "Stage") return reject(state); // Complete/Abandoned/Manual are terminal

  const b = state.budget;

  // Escapes available from any active stage (T-018/T-019)
  if (event.type === "exit_orchestration") {
    return event.mode === "manual"
      ? { state: { kind: "ManualContinuation", nextAction: "user-directed" },
          effects: [{ fx: "stop_with_next_action", nextAction: "user-directed" }] }
      : { state: { kind: "Abandoned" }, effects: [{ fx: "append_evidence", note: "abandoned" }] };
  }

  switch (state.stage) {
    case "plan":
      if (event.type === "route_card_validated") {
        if (!event.enforcedValidated) // GUARD-012
          return { state: stage("plan", "blocked", "not_started", b),
            effects: [{ fx: "fail_closed", code: "E_ENFORCED_MODE_NOT_VALIDATED" }] };
        return { state: stage("red", "active", "not_started", b),
          effects: [{ fx: "dispatch_role", role: "test_writer" }] }; // T-002
      }
      return reject(state);

    case "red":
      if (event.type === "red_result") {
        if (event.reducer === "pass") // T-003
          return { state: stage("green", "active", "not_started", b),
            effects: [{ fx: "update_route_card", note: "->green" }, { fx: "dispatch_role", role: "code_writer" }] };
        // T-004 / FM-002 / role blocks
        return { state: stage("red", "blocked", "not_started", b),
          effects: [{ fx: "record_blocker", code: "E_RED_UNEXPECTED_FAILURE", ownerRole: "test_writer" }] };
      }
      return reject(state);

    case "green":
      if (event.type === "green_result") {
        if (event.forbiddenTestEdit || event.reducer === "blocked") // T-006 / X-007
          return { state: stage("red", "repairing", "not_started",
            { ...b, usedTotal: b.usedTotal + 1 }),
            effects: [{ fx: "consume_budget" },
              { fx: "record_blocker", code: "E_FORBIDDEN_PATH_CHANGED", ownerRole: "code_writer" },
              { fx: "dispatch_role", role: "test_writer" }] };
        if (event.reducer === "stale") // GUARD-011
          return { state: stage("green", "blocked", "not_started", b),
            effects: [{ fx: "record_blocker", code: "E_STALE_SUBJECT", ownerRole: "code_writer" }] };
        if (event.reducer === "pass") // T-005
          return { state: stage("adversarial", "active", "not_started", b),
            effects: [{ fx: "build_review_package" }, { fx: "dispatch_role", role: "adversarial_reviewer" }] };
        return reject(state);
      }
      if (event.type === "manual_patch_authorized") { // T-020 / GUARD-015
        if (!event.authorized) return reject(state);
        return { state: stage("adversarial", "active", "not_started", b),
          effects: [{ fx: "append_evidence", note: "manual_patch" },
            { fx: "dispatch_role", role: "adversarial_reviewer" }] };
      }
      return reject(state);

    case "adversarial":
      if (event.type === "verdict_result") {
        if (event.verdict === "approve" && event.reducer === "pass") // T-007
          return { state: stage("prepare_pr", "approved", "not_started", b),
            effects: [{ fx: "update_route_card", note: "->prepare_pr" }] };
        if (event.verdict === "changes_requested") { // T-008
          if (!event.budgetLeft) // T-023 / GUARD-007
            return { state: stage("adversarial", "blocked", "not_started", b),
              effects: [{ fx: "record_blocker", code: "E_REPAIR_BUDGET_EXHAUSTED", ownerRole: "human" }] };
          return { state: stage("green", "repairing", "not_started",
            { ...b, usedTotal: b.usedTotal + 1 }),
            effects: [{ fx: "consume_budget" }, { fx: "dispatch_role", role: "code_writer" }] };
        }
        if (event.verdict === "cannot_judge") { // T-009
          const consume = event.missingWorkProduct;
          return { state: stage("adversarial", "blocked", "not_started",
            consume ? { ...b, usedTotal: b.usedTotal + 1 } : b),
            effects: consume
              ? [{ fx: "consume_budget" }, { fx: "record_blocker", code: "E_MISSING_REVIEW_PACKAGE", ownerRole: "orchestrator" }]
              : [{ fx: "record_blocker", code: "E_CANNOT_JUDGE", ownerRole: "orchestrator" }] };
        }
        // approve but reducer != pass (X-003 invalid approval)
        return { state: stage("adversarial", "blocked", "not_started", b),
          effects: [{ fx: "record_blocker", code: "E_INVALID_APPROVAL", ownerRole: "adversarial_reviewer" }] };
      }
      if (event.type === "provider_failure") // T-010 / GUARD-006b
        return { state: stage("adversarial", "blocked", "not_started", b),
          effects: [{ fx: "record_blocker", code: "E_PROVIDER_FAILURE", ownerRole: "orchestrator" }] };
      if (event.type === "reroute_to_test_writer") { // T-011
        if (!event.budgetLeft) return reject(state);
        return { state: stage("red", "repairing", "not_started", { ...b, usedTotal: b.usedTotal + 1 }),
          effects: [{ fx: "consume_budget" }, { fx: "dispatch_role", role: "test_writer" }] };
      }
      if (event.type === "user_waiver") { // T-021
        if (!event.scopedAndLegal) return reject(state); // cannot waive merge/RED/GREEN/stale
        return { state: stage("prepare_pr", "approved", "not_started", b),
          effects: [{ fx: "append_evidence", note: "user_waiver" }] };
      }
      return reject(state);

    case "prepare_pr":
      if (event.type === "prepare_pr_result") {
        if (event.reducer !== "pass" || !event.prAuthorized) // GUARD-008
          return { state: stage("prepare_pr", "blocked", "not_started", b),
            effects: [{ fx: "record_blocker", code: "E_PR_CREATE_UNAUTHORIZED", ownerRole: "prepare_pr" }] };
        return { state: stage("hitl_merge_checkpoint", "active", "awaiting_hitl_merge_approval", b), // T-012
          effects: [{ fx: "github_op", op: "push" }, { fx: "github_op", op: "create_pr" }] };
      }
      if (event.type === "defer_delivery") // T-016
        return { state: stage("closeout", "active", "delivery_deferred", b), effects: [{ fx: "update_route_card", note: "deferred" }] };
      return reject(state);

    case "hitl_merge_checkpoint":
      if (event.type === "hitl_merge_approval") { // T-013 / GUARD-009 (+GUARD-016 Q-002)
        if (!event.headMatches || !event.reviewedHeadMatches) // X-005 / Q-002
          return { state: stage("hitl_merge_checkpoint", "blocked", "awaiting_hitl_merge_approval", b),
            effects: [{ fx: "record_blocker", code: "E_HITL_HEAD_MISMATCH", ownerRole: "human" }] };
        return { state: stage("land_deploy", "active", "merge_approved", b),
          effects: [{ fx: "append_evidence", note: "hitl_merge_approval" }, { fx: "update_route_card", note: "merge_approved" }] };
      }
      if (event.type === "defer_delivery")
        return { state: stage("closeout", "active", "delivery_deferred", b), effects: [{ fx: "update_route_card", note: "deferred" }] };
      return reject(state);

    case "land_deploy":
      if (event.type === "land_deploy_result") {
        if (event.deployBlocked) // T-015 / X-006
          return { state: stage("land_deploy", "blocked", "delivery_blocked", b),
            effects: [{ fx: "record_blocker", code: "E_CI_OR_HEALTH_FAILED", ownerRole: "land_deploy" }] };
        if (event.merged) // T-014
          return { state: stage("closeout", "active", "deployed", b),
            effects: [{ fx: "github_op", op: "merge" }, { fx: "deploy_and_health" }, { fx: "update_route_card", note: "merged" }] };
        return reject(state);
      }
      if (event.type === "defer_delivery")
        return { state: stage("closeout", "active", "delivery_deferred", b), effects: [{ fx: "update_route_card", note: "deferred" }] };
      return reject(state);

    case "closeout":
      if (event.type === "closeout_result") // T-017
        return { state: { kind: "Complete" }, effects: [{ fx: "append_evidence", note: "closeout" }, { fx: "update_route_card", note: "complete" }] };
      return reject(state);

    default:
      return reject(state);
  }
}

// ---- Runnable self-check (assert-based; no framework) ----
// Run: `node --experimental-strip-types machine.ts`
const isMain =
  typeof process !== "undefined" &&
  !!process.argv[1] &&
  import.meta.url === new URL("file://" + process.argv[1]).href;
if (isMain) {
  const assert = (c: boolean, m: string) => { if (!c) throw new Error("FAIL: " + m); };
  let s: State = { kind: "NotCreated" };
  s = transition(s, { type: "create_work_item", routeCardValid: true }).state;
  assert(s.kind === "Stage" && s.stage === "plan", "T-001 -> plan");
  s = transition(s, { type: "route_card_validated", enforcedValidated: true }).state;
  assert(s.kind === "Stage" && s.stage === "red", "T-002 -> red");
  // TEST-012: RED wrong failure blocks, stays in red
  const blocked = transition(s, { type: "red_result", reducer: "blocked" });
  assert(blocked.state.kind === "Stage" && blocked.state.stage === "red" && blocked.state.lifecycle === "blocked", "TEST-012 red blocked");
  s = transition(s, { type: "red_result", reducer: "pass" }).state;
  assert(s.kind === "Stage" && s.stage === "green", "T-003 -> green");
  // TEST-011: forbidden test edit reroutes to red and consumes budget
  const reroute = transition(s, { type: "green_result", reducer: "pass", forbiddenTestEdit: true });
  assert(reroute.state.kind === "Stage" && reroute.state.stage === "red" && reroute.state.budget.usedTotal === 1, "TEST-011 reroute+budget");
  s = transition(s, { type: "green_result", reducer: "pass", forbiddenTestEdit: false }).state;
  assert(s.kind === "Stage" && s.stage === "adversarial", "T-005 -> adversarial");
  // TEST-015: approve with reducer!=pass is rejected as invalid approval
  const badApprove = transition(s, { type: "verdict_result", verdict: "approve", reducer: "blocked", budgetLeft: true, missingWorkProduct: false });
  assert(badApprove.state.kind === "Stage" && badApprove.state.lifecycle === "blocked", "TEST-015 invalid approval");
  s = transition(s, { type: "verdict_result", verdict: "approve", reducer: "pass", budgetLeft: true, missingWorkProduct: false }).state;
  assert(s.kind === "Stage" && s.stage === "prepare_pr", "T-007 -> prepare_pr");
  s = transition(s, { type: "prepare_pr_result", reducer: "pass", prAuthorized: true }).state;
  assert(s.kind === "Stage" && s.stage === "hitl_merge_checkpoint", "T-012 -> hitl");
  // TEST-021/060: wrong or unreviewed head blocks merge
  const badMerge = transition(s, { type: "hitl_merge_approval", headMatches: false, reviewedHeadMatches: true });
  assert(badMerge.state.kind === "Stage" && badMerge.state.stage === "hitl_merge_checkpoint" && badMerge.state.lifecycle === "blocked", "TEST-021 merge head mismatch blocks");
  s = transition(s, { type: "hitl_merge_approval", headMatches: true, reviewedHeadMatches: true }).state;
  assert(s.kind === "Stage" && s.stage === "land_deploy", "T-013 -> land_deploy");
  // TEST-022: CI/health fail blocks delivery, no merge
  const blockedDeploy = transition(s, { type: "land_deploy_result", merged: false, deployBlocked: true });
  assert(blockedDeploy.state.kind === "Stage" && blockedDeploy.state.delivery === "delivery_blocked", "TEST-022 delivery blocked");
  s = transition(s, { type: "land_deploy_result", merged: true, deployBlocked: false }).state;
  assert(s.kind === "Stage" && s.stage === "closeout", "T-014 -> closeout");
  s = transition(s, { type: "closeout_result" }).state;
  assert(s.kind === "Complete", "T-017 -> Complete");
  // TEST-020: merge event isn't even reachable without HITL; unknown pair rejected
  const bad = transition({ kind: "Stage", stage: "land_deploy", lifecycle: "active", delivery: "awaiting_hitl_merge_approval", budget: { maxTotal: 3, usedTotal: 0 } },
    { type: "closeout_result" });
  assert(bad.effects.some(e => e.fx === "reject"), "default rejection");
  console.log("machine.ts self-check passed");
}
