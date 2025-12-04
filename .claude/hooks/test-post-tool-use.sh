#!/bin/bash
echo "🎯 PostToolUse hook executed! Tool: $CLAUDE_TOOL_NAME"
echo "[$(date)] Tool: $CLAUDE_TOOL_NAME" >> /tmp/claude-posttooluse-test.log
