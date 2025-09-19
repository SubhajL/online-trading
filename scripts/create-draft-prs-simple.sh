#!/bin/bash
set -euo pipefail

# Simple script to create empty branches and draft PRs
# Useful when you want to start fresh without placeholder files

echo "Creating branches and draft PRs..."

# Array of branches with format: branch|issue|title
branches=(
    "feature/contracts-schema|2|#2 Contracts & Schema Pack"
    "feature/db-migrations|3|#3 DB Migrations & DAL"
    "svc/router|4|#9 Order Router (Go) + Testnet"
    "svc/ingestor|5|#4 WS Ingestor (Spot & Futures) + REST backfill"
    "svc/features|6|#5 Indicator Math & Feature Engine"
    "ui/bff|7|#10 BFF (NestJS) + Next.js UI + Alerts"
    "svc/smc|8|#6 SMC Engine (pivots, CHOCH/BOS, OB/FVG)"
    "svc/retest-guards|9|#7 Retest Analyzer + Regime/News/Funding Guards"
    "svc/decision|10|#8 Decision Engine & Risk (Spot + Futures-aware)"
    "svc/backtest-paper-wfo|11|Bonus: Backtester + Paper Broker + WFO"
)

# Start from main
git checkout main

for entry in "${branches[@]}"; do
    IFS='|' read -r branch issue title <<< "$entry"

    echo "Processing $branch..."

    # Create empty branch from main
    git checkout -b "$branch" main 2>/dev/null || git checkout "$branch"

    # Push empty branch
    git push -u origin "$branch" 2>/dev/null || true

    # Create draft PR
    gh pr create \
        --base main \
        --head "$branch" \
        --title "$title" \
        --body "Closes #$issue" \
        --draft 2>/dev/null || echo "PR already exists for $branch"
done

git checkout main
echo "✅ Done! Check your PRs at:"
gh pr list --draft