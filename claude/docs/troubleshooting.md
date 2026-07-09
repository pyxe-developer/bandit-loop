# Troubleshooting

## Route-Card Validation

Use `scripts/route-card` for create, status, and update operations. Route cards
must keep authority fields explicit; the scripts do not infer merge, deploy, or
enforced-mode authority from chat.

Common blockers:

| Code | Meaning | Next action |
| --- | --- | --- |
| `E_SCHEMA_INVALID` | The request or route card shape is invalid. | Fix the JSON field named in the error. |
| `E_ROUTE_CARD_STAGE_NOT_ENABLED` | Current stage is not in the enabled stage list. | Update the route card through `route-card update`. |
| `E_ROUTE_CARD_IMMUTABLE_FIELD` | An update tried to mutate protected authority/source fields. | Create a new route card or record a human decision instead. |
| `E_ENFORCED_MODE_NOT_VALIDATED` | An enforced route was requested without active validation evidence. | Use the default assisted mode; this Claude port does not install Codex TOML agents. |

## Evidence Status

Use `scripts/evidence-ledger status` and `scripts/verify-stage` to inspect the
active reducer result. Stale or inadmissible evidence is not silently ignored as
success.

Common blockers:

| Code | Meaning | Next action |
| --- | --- | --- |
| `E_STALE_SUBJECT` | Evidence does not bind to the current expected head or subject. | Rerun the stage against the current route-card subject. |
| `E_APPEND_AUTHORITY_INVALID` | Evidence was recorded by a role that is not allowed to record it. | Re-append through the orchestrator or the correct stage role. |
| `E_REVIEW_PACKAGE_DIGEST_MISMATCH` | Adversarial approval does not match the active review package digest. | Rebuild the review package and rerun adversarial review. |
| `E_STAGE_NOT_STARTED` | The requested stage has no active passing evidence. | Dispatch the required stage or inspect prior blockers. |

## Claude plugin loading

Load the plugin directly during development:

```sh
claude --plugin-dir ./claude
```

Use `/reload-plugins` after changing agents, hooks, or MCP configuration. The
bundled `SessionStart` hook is advisory and does not block tool calls.

## Delivery Blockers

Delivery requires operation-time remote state. Merge requires exact HITL
approval bound to the PR number and head SHA being merged.

Common blockers:

| Code | Meaning | Next action |
| --- | --- | --- |
| `E_OPERATION_TIME_REMOTE_HEAD_REQUIRED` | PR number or PR head SHA was not checked at operation time. | Fetch current remote PR state and retry. |
| `E_HITL_APPROVAL_REQUIRED` | No exact human approval is active. | Ask a human to approve the exact PR/head SHA. |
| `E_UNREVIEWED_MERGE_HEAD` | The head SHA was not adversarially reviewed. | Rerun review for the current head. |
| `E_CI_FAILED` / `E_CI_UNKNOWN` | Required CI failed or is unavailable. | Wait for or fix CI. |
| `E_DEPLOY_CONTRACT_MISSING` | Deploy was requested without any route-card deploy contract. | Add a route-card deploy contract before deploy. |
| `E_DEPLOY_FAILED` / `E_DEPLOY_HEALTH_FAILED` | Deploy or post-deploy health failed. | Investigate deploy/health tooling before retrying. |

Known v1 limit: deploy-contract validation is presence-only. The plugin does
not validate deploy command, health command, environment, timeout, or
provider-specific subfields.
