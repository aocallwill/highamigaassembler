# VS Code Extension - Quick Reference Card

## Installation (30 seconds)

```bash
# Option 1: Install from VSIX
code --install-extension vscode-highamigassembler-0.1.1.vsix

# Option 2: Development mode
code vscode-highamigassembler
# Press F5 to launch test instance
```

## The Three Main Shortcuts

| Shortcut | What It Does | Example |
|----------|-------------|---------|
| **Ctrl+Click** | Jump to procedure definition | Ctrl+Click on `helper` name |
| **F12** | Jump to procedure definition | Place cursor on `helper`, press F12 |
| **Shift+F12** | Scan references | Report raw count and open first match |

## What It Searches

```
✅ Current file      - proc definitions in same file
✅ .has files        - All HAS files in workspace
✅ .s files          - Assembly files in workspace
❌ External modules  - Not supported
```

## Real-World Usage

### Scenario 1: Same File
```has
proc helper() -> long { return 100; }

proc main() -> long {
    helper();  // Ctrl+Click → jumps to proc helper()
    return 0;
}
```

### Scenario 2: Different Files
```
main.has:   helper();      // Ctrl+Click
            ↓ jumps to ↓
lib.has:    proc helper()
```

### Scenario 3: Assembly Files
```
game.has:   TakeSystem();  // Ctrl+Click
            ↓ jumps to ↓
takeover.s: TakeSystem:
```

## Hover Features

```has
proc calculate(x: long, y: long) -> long { }

calculate();  // ← Hover mouse here
              // Shows: proc calculate(x: long, y: long) -> long
```

## Troubleshooting in 30 Seconds

| Problem | Solution |
|---------|----------|
| Ctrl+Click doesn't work | Try **F12** instead |
| Extension not loading | Open a `.has` file first |
| Definition not found | Check name matches exactly (case-sensitive) |
| Only finds same file | Ensure `.has` files are in workspace |

## Syntax Color Legend (HAS theme)

| Kind | Examples | Role |
|------|----------|------|
| Language commands | `if` `call` `return` `loop` | HAS control flow |
| Declarations | `proc` `func` `interrupt` `native` | Procedure forms |
| Sections | `code` `data` `bss` `*_chip` | Memory sections |
| Directives | `#include` `#warning` `#pragma` | Preprocessor |
| `#import` | `#import` + `bob`/`sprite`/`tileset`… | Asset import |
| m68k instructions | `move` `jsr` `rts` | Inside `asm { }` only |
| Pseudo-ops | `dc` `ds` `xdef` `section` | Inside `asm { }` only |

Select theme **High Amiga Assembler Colors** for the full palette.

## Files You Need to Know About

```
vscode-highamigassembler/
├── extension.js          ← Main code (register providers)
├── package.json          ← Config (commands, keybindings)
├── syntaxes/             ← TextMate grammar
├── themes/               ← Color theme
├── README.md             ← Overview
├── SETUP_GUIDE.md        ← Installation steps
└── FEATURES.md           ← Feature behavior and limitations
```

## Development Quick Start

```bash
# 1. Open extension folder
code vscode-highamigassembler

# 2. Press F5 (launches test VS Code instance)

# 3. Open any .has file in test instance

# 4. Try Ctrl+Click on procedure name

# 5. Edit extension.js to customize

# 6. Reload (Ctrl+R in test instance)
```

## Customize Keybindings

Edit `.vscode/keybindings.json`:

```json
{
    "key": "alt+g",           // Your shortcut
    "command": "highamigassembler.goToDefinition",
    "when": "editorTextFocus && editorLangId == highamigassembler"
}
```

## Package as Extension

```bash
# Install vsce (one-time)
npm install -g @vscode/vsce

# Create .vsix file
cd vscode-highamigassembler
vsce package

# Install it
code --install-extension vscode-highamigassembler-0.1.1.vsix
```

## What It Finds

### ✅ Finds These

```has
proc helper() -> long { }        ← Ctrl+Click works
func helper() -> long;           ← Hover works in the same file
extern func helper() -> long;    ← Call may resolve to proc or assembly label

helper();                        ← Shift+F12 finds this
```

### ❌ Doesn't Find These (Yet)

```has
struct MyStruct { }              ← No struct navigation
macro PUSH(d0, d1) { }          ← No macro navigation
const MAX_SIZE = 100;            ← No constant navigation
var global_var: long;            ← No variable navigation
```

## Pattern Matching Details

### What Works
```has
proc helper()      // Space before (
proc helper ( )    // Spaces are OK
prochelper( )      // NO - no space
```

### What Finds
```has
helper();          // YES - word boundary + (
my_helper();       // NO - different name
helper_func();     // NO - different name
```

## Search Limit

Definition and reference searches inspect at most 100 files for each workspace
glob used by the provider.

## Feature Matrix

| Feature | Status | Shortcut |
|---------|--------|----------|
| Go to Definition | ✅ | F12, Ctrl+Click |
| Reference scan, first-match jump | ✅ | Shift+F12 |
| Hover Info | ✅ | Mouse hover |
| Rename | 🔜 | Coming soon |
| Autocomplete | 🔜 | Coming soon |
| Linting | 🔜 | Coming soon |

## Integration Example

**project/main.has:**
```has
extern func init_graphics(mode: long) -> long;

code main:
    proc main() -> long {
        init_graphics(1);  // ← Ctrl+Click
        return 0;
    }
```

**project/graphics.has:**
```has
code graphics:
    proc init_graphics(mode: long) -> long {  // ← Jumps here
        return 0;
    }
```

## Status Bar Indicators

Look at VS Code status bar (bottom):

- **highamigassembler** ← Language detected (extension ready)
- **Line X, Col Y** ← Cursor position
- **UTF-8** ← Encoding

## Common Operations

### Jump to Definition
```
Position cursor on name → F12
              or
       Ctrl+Click on name
```

### Scan Uses
```
Position cursor on name → Shift+F12
```

The command reports a raw regex-match count and opens the first location. A
declaration may be counted twice, and no result picker is shown.

### Quick Signature
```
Hover mouse over name → Wait 500ms → See popup
```

### Go Back
```
Ctrl+Alt+Left (standard VS Code)
```

## Keybinding Reference

| VS Code | HAS Extension | Windows | Mac |
|---------|---------------|---------|-----|
| Go to Def | F12 | F12 | F12 |
| Go to Def | Ctrl+Click | Ctrl+Click | Cmd+Click |
| Find Refs | Shift+F12 | Shift+F12 | Shift+F12 |
| Go Back | Ctrl+Alt+← | Ctrl+Alt+Left | Cmd+Alt+← |

## Tips & Tricks

1. **Hold Ctrl and click** for quickest navigation
2. **Use F12** if your mouse is acting up
3. **Shift+F12** to scan matching calls and declarations
4. **Hover before clicking** to verify it's the right name
5. **Use Ctrl+T** (if enabled) to search symbols workspace-wide

## Debug Commands

View extension logs:
```
VS Code → View → Output → Select "HAS Language Extension"
```

Test a file:
```bash
# No fancy setup needed
# Just open .has file in VS Code with extension
# Use Ctrl+Click to test
```

## Limitations to Know

1. **Case Sensitive** - `Helper` ≠ `helper`
2. **Exact Match** - Must match definition name exactly
3. **Workspace Only** - Can't find external libraries
4. **Regex Based** - Simple pattern matching, not full AST
5. **Single Definition** - Jumps to first match, doesn't show choices

## Support

**Issue:** Something doesn't work  
**Solution:**
1. Check that file is `.has` or `.s`
2. Verify procedure name matches exactly
3. Try F12 instead of Ctrl+Click
4. Reload VS Code (Ctrl+R)
5. Check Output panel for errors

## Version Info

- **Extension:** v0.1.1
- **Requires:** VS Code 1.85+
- **License:** MIT

---

**TL;DR:** Ctrl+Click a procedure name to jump to its definition in the workspace.
