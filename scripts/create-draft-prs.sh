#!/bin/bash
set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Creating draft PRs for all development branches...${NC}"

# Ensure we're on main branch and up to date
echo -e "${YELLOW}Ensuring main branch is up to date...${NC}"
git checkout main
git pull origin main

# Define all branches with their details
declare -A branches=(
    ["feature/contracts-schema"]="2|#2 Contracts & Schema Pack|Wave A"
    ["feature/db-migrations"]="3|#3 DB Migrations & DAL|Wave A"
    ["svc/router"]="4|#9 Order Router (Go) + Testnet|Wave A"
    ["svc/ingestor"]="5|#4 WS Ingestor (Spot & Futures) + REST backfill|Wave B"
    ["svc/features"]="6|#5 Indicator Math & Feature Engine|Wave B"
    ["ui/bff"]="7|#10 BFF (NestJS) + Next.js UI + Alerts|Wave B"
    ["svc/smc"]="8|#6 SMC Engine (pivots, CHOCH/BOS, OB/FVG)|Wave C"
    ["svc/retest-guards"]="9|#7 Retest Analyzer + Regime/News/Funding Guards|Wave C"
    ["svc/decision"]="10|#8 Decision Engine & Risk (Spot + Futures-aware)|Wave C"
    ["svc/backtest-paper-wfo"]="11|Bonus: Backtester + Paper Broker + WFO|Bonus"
)

# Create branches and draft PRs
for branch in "${!branches[@]}"; do
    IFS='|' read -r issue_num title wave <<< "${branches[$branch]}"

    echo -e "\n${YELLOW}Processing ${branch}...${NC}"

    # Check if branch already exists locally
    if git show-ref --verify --quiet "refs/heads/${branch}"; then
        echo "Branch ${branch} already exists locally, checking out..."
        git checkout "${branch}"
        git pull origin "${branch}" 2>/dev/null || echo "No remote branch yet"
    else
        echo "Creating branch ${branch}..."
        git checkout -b "${branch}"
    fi

    # Create a placeholder file if branch is empty
    if [ -z "$(git ls-tree HEAD 2>/dev/null)" ] || [ ! -f ".gitkeep" ]; then
        echo "# ${title}" > README_BRANCH.md
        echo "" >> README_BRANCH.md
        echo "This branch implements issue #${issue_num}" >> README_BRANCH.md
        echo "Wave: ${wave}" >> README_BRANCH.md
        git add README_BRANCH.md
        git commit -m "chore: initial commit for ${title}" || echo "Nothing to commit"
    fi

    # Push branch to origin
    echo "Pushing ${branch} to origin..."
    git push -u origin "${branch}" || echo "Branch already pushed"

    # Create draft PR using gh CLI
    echo "Creating draft PR for ${branch}..."

    # Create PR body with issue link and template
    cat > /tmp/pr_body_${issue_num}.md <<EOF
Closes #${issue_num}

## Summary
Implementation of ${title}

## Checks
- [ ] CI gate passes
- [ ] Unit tests added
- [ ] Integration tested
- [ ] No breaking changes

See issue #${issue_num} for detailed requirements.
EOF

    # Create the draft PR (skip if already exists)
    if gh pr list --head "${branch}" --state all | grep -q "${branch}"; then
        echo "PR already exists for ${branch}, skipping..."
    else
        gh pr create \
            --base main \
            --head "${branch}" \
            --title "${title}" \
            --body-file "/tmp/pr_body_${issue_num}.md" \
            --draft \
            --label "${wave}" || echo "Failed to create PR for ${branch}"
    fi

    # Clean up temp file
    rm -f "/tmp/pr_body_${issue_num}.md"
done

# Return to main branch
git checkout main

echo -e "\n${GREEN}✅ Draft PRs creation complete!${NC}"
echo -e "${GREEN}Next steps:${NC}"
echo "1. Visit https://github.com/$(gh repo view --json owner,name --jq '.owner.login + "/" + .name')/pulls"
echo "2. Add PRs to the project board"
echo "3. Configure branch protection rules if not already done"