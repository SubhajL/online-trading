#!/bin/bash
set -euo pipefail

echo "🔄 Renaming feature/order-router to svc/router (with worktree)..."

# Get the worktree path
WORKTREE_PATH="/Users/subhajlimanond/dev/repo_order"

echo "📂 Found worktree at: $WORKTREE_PATH"

# Method 1: Rename from within the worktree
echo "📝 Switching to worktree to rename branch..."
cd "$WORKTREE_PATH"

# Rename the branch from within its worktree
git branch -m svc/router

# Update the remote
echo "🔄 Updating remote..."
git push origin --delete feature/order-router 2>/dev/null || echo "Old remote branch doesn't exist"
git push -u origin svc/router

echo "✅ Branch renamed successfully!"
echo "📍 Your worktree at $WORKTREE_PATH now uses branch: svc/router"

# Show the updated worktree list
echo -e "\n📋 Updated worktree list:"
git worktree list | grep -E "(router|order)"