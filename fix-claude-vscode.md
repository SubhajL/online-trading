# Fix Claude Code VS Code Connection

The "IDE disconnected" message appears when the Claude Code extension loses connection with the Claude CLI. Here's how to fix it:

## Option 1: Restart the Extension Connection (Recommended)
1. In VS Code, open Command Palette (Cmd+Shift+P)
2. Type "Claude Code: Restart Language Server"
3. If that doesn't work, try "Claude Code: Reset Extension State"

## Option 2: Reload VS Code Window
1. Open Command Palette (Cmd+Shift+P)
2. Type "Developer: Reload Window"
3. This will restart VS Code and re-establish connections

## Option 3: Manual Restart
1. Close the Claude Code terminal tab
2. Click the Claude Code icon in the Activity Bar (left sidebar)
3. Click "Open Claude Code" to start a new session

## Option 4: Full Reset
1. Close all VS Code windows
2. Kill all Claude processes:
   ```bash
   pkill -f claude
   ```
3. Restart VS Code
4. Open your project
5. Click the Claude Code extension icon to start fresh

## Verify Connection
Once reconnected, you should see:
- "IDE connected" in the bottom right
- The extension icon should be active (not grayed out)
- Command Palette should show Claude Code commands

The connection issue is usually temporary and one of these methods should fix it.