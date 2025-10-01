# BeautifyAI Codebase Review Guidelines (AI-Assisted)

## Purpose & Scope
- Provide a single reference for AI-assisted reviewers to protect long-term system health while keeping velocity high.
- Marry the philosophical foundations of modern review culture with actionable "what" and "how" checklists for every phase of an AI-powered review session.
- Apply to all code touching BeautifyAI services, shared libraries, infrastructure, tests, documentation, and configuration.

## AI-Assisted Review Operating Model
- **Primary goal**: ensure each change is a net improvement. Per Google guidance, favor merging when code clearly improves overall health, even if small nits remain.
- **AI reviewer roles**:
  - **Context loader**: gather PR summary, linked tickets, screenshots, test evidence.
  - **Checklist executor**: walk each section below, citing concrete code references.
  - **Risk profiler**: highlight severity (blocking, high, medium, nit) with explicit rationale.
  - **Culture steward**: keep tone professional, collaborative, and curiosity-driven.
- **Comment convention**: prefix remarks with `Blocking:`, `High:`, `Medium:`, `Nit:` or `Question:`. For suggestions, offer actionable fixes or code snippets.
- **Speed & iteration**:
  - Target <24h turnaround for first response.
  - Encourage small, scoped PRs; flag oversized changes and suggest splitting.
  - Escalate unresolved debates synchronously, then summarize outcomes in the review thread.

## Preparation Checklist (Before Line-by-Line Review)
| What to Confirm | How to Check |
| --- | --- |
| Purpose and scope are clear | Read PR description, linked tickets, design docs. Ask for missing context or screenshots (desktop + mobile) before deep dive. |
| Change is appropriately scoped | Ensure PR contains a single logical change. Recommend separate PRs for unrelated refactors/formatting. |
| Artifacts ready | Verify test evidence, profiling data (if performance-sensitive), migration plans, updated docs, feature flag rollout notes. |
| Owners & stakeholders notified | Confirm CODEOWNERS or cross-team reviewers are added when shared contracts/services touched. |

## Strategic Review: Intent, Architecture, Domain Integrity
| What | How |
| --- | --- |
| Requirements fit | Trace code to acceptance criteria; confirm all user stories satisfied without scope creep (YAGNI). |
| Domain rules upheld | Check business logic against domain invariants. Ask for unit/integration tests covering edge cases (e.g., payment before shipment). |
| Architectural placement | Ensure new logic lives in correct layer/service and respects separation of concerns. Flag tight coupling or boundary leaks. |
| Dependency strategy | Challenge new third-party libraries: justify necessity, maintenance status, licence, transitive risks. |
| Microservice contracts | Require consumer-team approval for shared API/schema changes. Confirm versioning strategy, backward compatibility plan, and migration timeline. |

## Correctness & Behavior
| Area | What to Inspect | How |
| --- | --- | --- |
| Logic | Algorithm correctness, guard clauses, null handling | Walk through control flow; simulate edge cases; ensure allow-list validation for external input. |
| State | Lifecycle, resource cleanup, idempotency | Verify init and teardown paths; ensure retries are safe; check transactions cover multi-step operations. |
| Errors | Classification, secure failure, alerts | Confirm transient vs permanent error handling, fallbacks, logging/metrics integration, DLQ usage. |
| Concurrency | Locks, async flows, shared resources | Inspect for race conditions, deadlocks, missing awaits, shared mutable state protections. |

## Data, Contracts, and Security Posture
| What | How |
| --- | --- |
| Schema changes | Review migrations for backward compatibility, reversibility, performance (run `EXPLAIN` where needed), and data backfill plans. |
| Type safety | Ensure strong typing, nullability handling, branded IDs, consistent serialization formats (camelCase, ISO-8601). |
| API stability | Check versioning discipline, contract tests, pagination/filtering consistency, error envelope uniformity. |
| Security basics | Validate AuthN/AuthZ checks at entry points, principle of least privilege, prepared statements, output encoding. |
| Secrets handling | Confirm secrets sourced from vault/env, never hardcoded, and masked in logs/config. |

## Performance, Scalability, Resilience
| Domain | What | How |
| --- | --- | --- |
| Complexity | Algorithmic cost, data structures | Evaluate asymptotic complexity; request benchmarks for hot paths. |
| Memory & I/O | Footprint, streaming, pooling | Spot unnecessary loads, missing pooling configs, potential leaks. |
| Database | Query efficiency | Inspect generated SQL, index usage, N+1 patterns, transaction scope, connection pool sizing. |
| Resilience | Timeouts, retries, backpressure, circuit breakers | Map failure scenarios to resilience patterns; verify configuration is externalized and monitored. |
| Degradation | Fallback behavior | Ensure cached/default responses maintain UX during partial outages. |

## Testing Strategy & Quality
| What | How |
| --- | --- |
| Test coverage depth | Confirm tests exist at appropriate pyramid levels (unit, integration, e2e). Challenge missing negative/edge cases. |
| Assertion strength | Require meaningful expectations (whole-structure assertions, not just non-null). |
| Determinism | Spot flaky patterns (random seeds, shared state). Ensure isolation via mocks/stubs. |
| CI integration | Verify CI run is green, tests run within acceptable budget, flakiness addressed immediately. |
| Feature flags | Ensure tests cover both enabled/disabled states when toggles introduced. |

## Maintainability, Readability, Documentation
| What | How |
| --- | --- |
| Cohesion & SRP | Flag classes/functions doing too much; suggest decomposition only when it truly improves clarity/testability. |
| Naming & clarity | Enforce descriptive, domain-aligned names; challenge abbreviations or overloaded terminology. |
| Complexity (KISS) | Prefer simple, explicit implementations over clever abstractions. |
| Duplication vs abstraction | Balance DRY with readability; note premature abstractions that harm clarity. |
| Docs & comments | Require README/ADR updates for workflow changes; ensure comments explain "why" not "what"; keep code self-explanatory. |

## Observability & Operational Readiness
| What | How |
| --- | --- |
| Metrics & logs | Confirm RED signals instrumented; logs structured, privacy-safe, include correlation IDs. |
| Tracing | Ensure trace context propagation, span creation with useful attributes. |
| Alerts & runbooks | Check new failure modes map to actionable alerts and documented runbook steps. |
| Feature management | Require feature flags/kill switches for risky releases; expect rollout/rollback plan. |
| Config | Verify configuration is externalized, version-controlled, and rolled out safely. |

## Advanced Security & Compliance
| What | How |
| --- | --- |
| Threat modeling alignment | Request evidence mitigations from STRIDE (or equivalent) design review are implemented; add missing controls. |
| Data privacy | Enforce data minimization, encryption in transit/at rest, support for GDPR/CCPA rights (access, rectification, erasure). |
| Supply chain | Vet new dependencies; ensure SCA/SBOM tooling runs clean; check for signatures/checksums in build pipeline; block PRs introducing known CVEs. |

## Process & Workflow Excellence
| What | How |
| --- | --- |
| Automation first | Confirm linting, formatting, SAST run pre-review; bounce PRs failing automated gates. |
| Git hygiene | Require atomic commits, clean history, informative PR descriptions. Suggest `git rebase -i` for cleanup. |
| Reviewer rotation | Encourage spreading knowledge; flag repeated single-reviewer bottlenecks. |
| Comment management | Use severity prefixes; resolve threads only when addressed; summarize sync decisions back into PR. |
| Merge criteria | Ensure approvals, green CI, and resolved blocking items before merge; enforce branch protection rules. |

## Future-Proofing & Knowledge Transfer
| What | How |
| --- | --- |
| Extensibility | Evaluate use of patterns, extension points, configuration-driven behavior for future evolution. |
| Technical debt logging | For intentional shortcuts, demand TODO + tracked ticket; avoid silent debt. |
| Documentation via review | Convert recurring Q&A into improved code comments, docs, or ADR updates. |
| Mentorship | Highlight positive patterns; suggest follow-up pairing or knowledge-sharing sessions when gaps observed. |

## Cross-Team Coordination & Migrations
| What | How |
| --- | --- |
| Consumer impact | Ensure downstream teams sign off; check contract tests updated. |
| Integration safety | Validate resilience to upstream changes/failures; confirm integration tests or mocks align with contracts. |
| Migration plan | Review data backfills, dual-write/read strategies, staged rollout timelines, rollback procedures. |

## Communication & Culture Guardrails
- **Tone**: professional, empathetic, assume positive intent. Separate critique of code from author.
- **Questions over commands**: prefer "What do you think about..." to invite dialogue.
- **Praise good work**: note well-crafted tests, clean designs, or thoughtful refactors.
- **Conflict resolution**: escalate to synchronous chat when stuck; document outcomes in PR.
- **Velocity awareness**: highlight blockers quickly; avoid delays over nits.

## Quick Reference: Severity Tag Examples
- `Blocking:` Security vulnerability, broken domain rule, failing invariants, incompatible API change.
- `High:` Significant maintainability/performance risk; must address but can be resolved within PR.
- `Medium:` Important improvement or clarification; request fix or documented follow-up.
- `Nit:` Minor polish (naming, comment style) — optional.
- `Question:` Clarify intent; if unresolved, escalate severity.

## Session Template for AI Reviewer Output
1. **Summary**: One paragraph describing change scope and overall assessment (net improvement?, outstanding risks?).
2. **Blocking Findings**: Bullet list with file:line references, severity, rationale, and concrete fix suggestions.
3. **High/Medium Findings**: Same format, grouped by severity.
4. **Positive Notes**: Highlight strong aspects (tests, design decisions) for morale/mentorship.
5. **Follow-ups**: List tickets/docs to create/update, additional testing recommended, rollout considerations.
6. **Review SLA Reminder**: Note if author needs additional data/screenshots/tests for completion.

## Continuous Improvement Practices
- Retrospect review metrics quarterly (turnaround time, rework %, bug escape rate).
- Maintain living checklist: update this guide when new incident postmortems reveal gaps.
- Encourage reviewers to log "Couldn’t review" reasons (missing context, flaky CI) to drive process fixes.
- Pair new reviewers with experienced mentors to share tacit knowledge and cultural expectations.

---
_This guide distills the Engineering Playbook for Effective Codebase Review into actionable, AI-ready instructions. Always adapt judgment to the specific context while upholding BeautifyAI’s standards of quality, security, and user trust._
