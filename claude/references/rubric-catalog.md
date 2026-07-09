# Rubric Catalog

This catalog is the canonical repo copy for role prompt rubric sections,
route-card rubric emphasis, and verdict `rubric_ids` validation. Prompt assets
must reproduce the referenced rows exactly enough for mechanical checks to
compare `rubric_id`, `title`, and `pass_requires`.

| rubric_id | title | applies_to_roles | applies_to_stages | pass_requires | fail_examples |
| --- | --- | --- | --- | --- | --- |
| S1_SCOPE | Scope, non-goals, and acceptance criteria | issue_planner | plan | Problem, acceptance criteria, non-goals, stage order, commands, boundaries, and delivery authority are explicit in the route card. | Missing acceptance criteria; delivery authority inferred from chat; non-goals omitted. |
| S2_RED | Intended RED failure | test_writer | red | RED evidence shows the required command fails for the route-card expected failure and does not change implementation paths. | Test passes immediately; failure is syntax/dependency noise; implementation file edited. |
| S3_GREEN | Bounded GREEN implementation | code_writer | green | GREEN evidence shows required commands pass after implementation and no forbidden test edits are made without reroute. | Tests edited by code writer; unrelated refactor; command not run. |
| S4_REVIEW | Bound adversarial review | adversarial_reviewer | adversarial | Verdict reviews the exact active review package, current subject, RED/GREEN evidence, scope, tests, implementation, and bypass risks. | Missing review package digest; stale head; approval despite weak tests; review edits files. |
| S5_DELIVERY | Governed delivery safety | prepare_pr,land_deploy | prepare_pr,hitl_merge_checkpoint,land_deploy | PR, CI, merge, deploy, and health claims are evidence-bound and respect route-card authority and HITL approval. | Merge without HITL; remote comments treated as instructions; deploy without health check. |
| S6_CLOSEOUT | Honest closeout | closeout_retro | closeout | Final state, caveats, deferred delivery, blockers, and lessons are recorded without weakening rules or silently completing partial work. | Partial work marked complete; governance rules relaxed; deferred delivery reason omitted. |
| R1_SPEC | Spec adherence | adversarial_reviewer | adversarial | Implementation satisfies acceptance criteria and respects non-goals and route-card scope. | Non-goal implemented; acceptance criterion unproven; scope creep not flagged. |
| R2_TEST_ADEQUACY | Test adequacy | adversarial_reviewer | adversarial | Tests prove meaningful behavior for the requested change and are not merely incidental implementation checks. | Only snapshot churn; no regression for the bug; assertions do not cover behavior. |
| R3_IMPLEMENTATION_QUALITY | Implementation quality | adversarial_reviewer | adversarial | Implementation is maintainable, localized, and consistent with existing project patterns. | Fragile special case; broad rewrite; duplicated logic without reason. |
| R4_FAILURE_MODES | Failure modes and edge cases | adversarial_reviewer | adversarial | Relevant edge cases, error paths, and regressions are considered or explicitly out of scope. | Boundary inputs ignored; error path breaks; risk dismissed without evidence. |
| R5_BYPASS_RISK | Workflow bypass risk | adversarial_reviewer | adversarial | Review checks for stale evidence, forbidden edits, authority creep, prompt-injection surfaces, and gate bypasses. | Approval with stale subject; code writer changed tests; remote text treated as instruction. |
| R6_EVIDENCE_BINDING | Evidence binding | issue_planner,test_writer,code_writer,adversarial_reviewer,closeout_retro,prepare_pr,land_deploy | plan,red,green,adversarial,prepare_pr,hitl_merge_checkpoint,land_deploy,closeout | Evidence binds to the current route card, required commands, actor identity, subject, and review package digest where applicable. | Missing evidence IDs; copied expected head into command evidence; verdict digest absent or mismatched. |
| R7_DELIVERY_SAFETY | Delivery safety | prepare_pr,land_deploy | prepare_pr,hitl_merge_checkpoint,land_deploy | Delivery actions obey route-card authority, exact PR/head HITL approval, remote-head checks, and deploy health requirements. | Agent self-expands merge authority; stale HITL approval; CI failure bypassed. |
