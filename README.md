# RiskyTextExpander

A simple text expander for Wayland. Monitors keyboard input and expands short text snippets into longer text or executes key commands.

**Why "risky"?** It's effectively a keylogger that auto-types without context awareness.

## Features
- Replace typed text, quickly by using wl-paste  
- Send commands as part of the replacement
- Type keys, do not use wl-paste
- Auto detect keyboard

## Setup

### Prerequisites
- `ydotoold`: if the user is a part of the "input" group, you should be okay.
- `wl-copy` for clipboard operations

### Configuration

Config files are stored in `~/.config/risky-text-expander/`  
Examples will automatically copy on first run of `start.sh`

**Text Expansions** (`config`):
Note: Backtick is protected, and must not be used for anything else.

```ini
zurl: https://github.com/emmertex/RiskyTextExpander
zbye: Kind Regards, Andrew Frahn
zhz: ❤️
```

**Text Expansion with Commands**:
Note: Backtick is protected, and must not be used for anything else.

```ini
midbold: Middle `bold`word`bold` bold.
zgoodbye: Kind Regards,`enter`Andrew Frahn`enter``bold`Emmertex`bold``send`
ztyped: `t``y``p``e``d` pasted.`enter`
```

**Key Commands** (`commands.config`):
Note: commands must be >2 characters

```ini
bold: ctrl+b
send: ctrl+enter
enter: enter
```

## Usage

Start the service:

```bash
./start.sh
```

### How it Works

- Monitors the last 10 lowercase characters typed
- On match: deletes the typed text and replaces it
- Text segments are pasted via clipboard
- Key commands (in backticks) execute keyboard shortcuts

### Example

Here are a few examples based on the sample configurations.

**Simple Expansion**:
- **Typing:** `zurl`
- **Result:** `https://github.com/emmertex/RiskyTextExpander` is pasted.

**Expansion with Commands**:
- **Typing:** `midbold`
- **Result:** "Middle **word** bold." is typed out. This assumes `bold` is mapped to `ctrl+b` which toggles bold formatting in your text editor.

**Complex Expansion with Commands**:
- **Typing:** `zgoodbye`
- **Result:**

```text
Kind Regards,
Andrew Frahn
**Emmertex**
```

This text is output, and then `ctrl+enter` is pressed, which would send the message in many chat and email applications.


