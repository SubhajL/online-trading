#!/bin/bash

# Script to set up .env symlinks for git worktrees
# This ensures all worktrees can access environment variables for development

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Main repository directory
MAIN_DIR="/Users/subhajlimanond/dev/online trader"
ENV_FILE="$MAIN_DIR/.env"

# Check if main .env exists
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}❌ Error: .env file not found in main directory${NC}"
    echo "Please create $ENV_FILE first"
    exit 1
fi

echo -e "${GREEN}Setting up .env symlinks for all worktrees...${NC}"

# Get all worktrees (excluding the main one)
worktrees=$(git worktree list --porcelain | grep "worktree " | grep -v "$MAIN_DIR$" | cut -d' ' -f2-)

if [ -z "$worktrees" ]; then
    echo -e "${YELLOW}No worktrees found besides main${NC}"
    exit 0
fi

# Process each worktree
while IFS= read -r worktree; do
    if [ -n "$worktree" ]; then
        worktree_env="$worktree/.env"

        # Skip if it's the main directory
        if [ "$worktree" = "$MAIN_DIR" ]; then
            continue
        fi

        echo -e "\n${YELLOW}Processing: $(basename "$worktree")${NC}"

        # Check if .env already exists
        if [ -e "$worktree_env" ]; then
            if [ -L "$worktree_env" ]; then
                echo "  ✓ Symlink already exists"
            else
                echo "  ⚠️  .env file exists but is not a symlink"
                echo "  → Backing up to .env.backup"
                mv "$worktree_env" "$worktree_env.backup"
                ln -s "$ENV_FILE" "$worktree_env"
                echo "  ✓ Created symlink"
            fi
        else
            ln -s "$ENV_FILE" "$worktree_env"
            echo "  ✓ Created symlink"
        fi
    fi
done <<< "$worktrees"

echo -e "\n${GREEN}✅ All worktrees now have .env symlinks!${NC}"
echo -e "${GREEN}You can now run integration tests in any worktree.${NC}"

# Show summary
echo -e "\n${YELLOW}Summary:${NC}"
echo "Main .env location: $ENV_FILE"
echo "Symlinks created in:"
while IFS= read -r worktree; do
    if [ -n "$worktree" ] && [ "$worktree" != "$MAIN_DIR" ]; then
        echo "  - $(basename "$worktree")"
    fi
done <<< "$worktrees"