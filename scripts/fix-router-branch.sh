#!/bin/bash
set -euo pipefail

echo "🔄 Renaming feature/order-router to svc/router..."

# Save current branch
CURRENT_BRANCH=$(git branch --show-current)

# Checkout the branch to rename
git checkout feature/order-router

# Rename locally
echo "📝 Renaming local branch..."
git branch -m svc/router

# Delete old remote branch
echo "🗑️  Deleting old remote branch..."
git push origin --delete feature/order-router || echo "Remote branch may not exist"

# Push with new name
echo "📤 Pushing new branch name..."
git push -u origin svc/router

# Update any PR if it exists
if gh pr list --head feature/order-router --state open | grep -q "feature/order-router"; then
    echo "📋 Note: You may need to update your PR to reference the new branch"
    gh pr list --head svc/router
fi

echo "✅ Done! Branch renamed from feature/order-router to svc/router"

# Return to original branch
if [ "$CURRENT_BRANCH" != "feature/order-router" ]; then
    git checkout "$CURRENT_BRANCH"
fi