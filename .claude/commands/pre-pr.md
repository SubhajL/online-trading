Run all pre-PR quality checks before submitting a pull request.

## Quality Gates

### 1. Formatting
```bash
make format
```

### 2. Linting
```bash
make lint
```
If errors, fix with:
```bash
make lint-fix
```

### 3. Type Checking
```bash
make typecheck
```

### 4. Unit Tests
```bash
make test
```

### 5. Security Scan (if time permits)
```bash
make security-check
```

## Summary Command
Run all checks in sequence:
```bash
make format && make lint && make typecheck && make test
```

## Pre-Commit Verification
Ensure pre-commit hooks are installed and passing:
```bash
pre-commit run --all-files
```

## Final Checklist

Before creating PR, verify:
- [ ] All checks pass
- [ ] Changes are committed
- [ ] Commit messages follow Conventional Commits
- [ ] No debug code left in
- [ ] No TODO comments without issue references
- [ ] CLAUDE.md guidelines followed

## Create PR
When ready:
```bash
gh pr create --title "type(scope): description" --body "## Summary
- What changed
- Why

## Test Plan
- How to test

## Checklist
- [x] Tests pass
- [x] Linting passes
- [x] Type checks pass"
```
