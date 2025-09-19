## Summary
<!-- Short description of what this branch delivers -->

## Linked Issue
Closes #<!-- issue number -->

## Prompt Details
- **Prompt #**: <!-- e.g., #5 -->
- **Wave**: <!-- A, B, or C -->
- **Branch**: <!-- e.g., svc/features -->

## Scope (allowed paths)
<!-- Copy the preface block for this prompt from PROJECT_PLAN.md -->

## Checks
### CI Jobs
- [ ] **CI Gate**: `<!-- job-name -->` is green
- [ ] Unit tests added/updated
- [ ] Golden/parity tests pass (if applicable)

### Integration Gates
- [ ] Manual smoke test completed (see steps below)
- [ ] Screenshots/logs attached (if applicable)

### Smoke Test Steps
<!-- List the manual steps to verify integration -->
1.
2.
3.

## Code Quality
- [ ] No breaking schema changes (or v2 introduced with consumers updated)
- [ ] Follows existing code conventions
- [ ] No hardcoded secrets or API keys
- [ ] Observability added (metrics/logs/traces)

## Risks & Rollback
**Risks**: <!-- Describe any risks -->

**Rollback Strategy**:
- Revert PR
- Feature flag: `<!-- flag-name -->` to disable
- <!-- Any additional rollback steps -->

## Screenshots/Logs
<!-- Add any relevant screenshots or log outputs -->

## Additional Notes
<!-- Any additional context, dependencies, or notes for reviewers -->