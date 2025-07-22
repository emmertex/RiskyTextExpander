'''Text parsing and replacement for RiskyTextExpander.'''

import re
import os # For ydotool
import time # For potential delays
import subprocess # For running external commands
import os
from pathlib import Path
from evdev import ecodes  # Convert KEY_* names to numeric codes
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading

BUFFER_SIZE = 10

# Mapping for human-readable modifier names to ydotool key names
MODIFIER_MAP = {
    "meta": "KEY_LEFTMETA",   # Or KEY_LEFTWINDOWS, depending on ydotool/system
    "alt": "KEY_LEFTALT",
    "ctrl": "KEY_LEFTCTRL",
    "shift": "KEY_LEFTSHIFT",
}

# Mapping for common non-alphanumeric keys, extend as needed
# Alphanumeric keys (a-z, 0-9) will be KEY_A, KEY_1 etc. by convention.
SPECIAL_KEY_MAP = {
    "space": "KEY_SPACE",
    "enter": "KEY_ENTER",
    "tab": "KEY_TAB",
    "backspace": "KEY_BACKSPACE",
    "delete": "KEY_DELETE",
    "esc": "KEY_ESC",
    # Add function keys F1-F12, arrow keys, etc. if needed
    # "f1": "KEY_F1", "up": "KEY_UP",
}

# Helper to translate KEY_* names to their numeric evdev codes (as strings).
def _key_name_to_code(key_name: str) -> str | None:
    """Return the numeric evdev code (str) for a given KEY_* constant name."""
    if not key_name.startswith("KEY_"):
        return None
    code = getattr(ecodes, key_name, None)
    if code is None:
        return None
    return str(code)

KEY_BACKSPACE = "14"
KEY_LEFTCTRL = "29"
KEY_V = "47"

def get_config_dir():
    """Get XDG-compliant configuration directory"""
    xdg_config = os.environ.get('XDG_CONFIG_HOME')
    if xdg_config:
        return Path(xdg_config) / 'risky-text-expander'
    return Path.home() / '.config' / 'risky-text-expander'

def get_config_file_path(filename):
    """Get full path to a config file in the XDG-compliant directory"""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
    return str(config_dir / filename)

class Parser:
    def __init__(self, monitor_ref=None): # Added monitor_ref
        self.buffer = ""
        self.config_path = get_config_file_path("config")
        self.commands_path = get_config_file_path("commands.config")
        self.config = self._load_config(self.config_path)
        self.key_commands = self._load_config(self.commands_path) # Load new commands config
        self.monitor_ref = monitor_ref # Store monitor reference
        self._observer = None
        self._watcher_thread = None
        self._stop_event = threading.Event()
        self.start_file_watcher()

    def start_file_watcher(self):
        class ConfigReloadHandler(FileSystemEventHandler):
            def __init__(self, parser):
                self.parser = parser
            def on_modified(self, event):
                if event.src_path == self.parser.config_path:
                    print("Config file changed, reloading...")
                    self.parser.config = self.parser._load_config(self.parser.config_path)
                elif event.src_path == self.parser.commands_path:
                    print("Commands config file changed, reloading...")
                    self.parser.key_commands = self.parser._load_config(self.parser.commands_path)
        
        def run_observer():
            event_handler = ConfigReloadHandler(self)
            observer = Observer()
            config_dir = str(Path(self.config_path).parent)
            observer.schedule(event_handler, path=config_dir, recursive=False)
            observer.start()
            self._observer = observer
            try:
                while not self._stop_event.is_set():
                    self._stop_event.wait(1)
            finally:
                observer.stop()
                observer.join()
        
        self._watcher_thread = threading.Thread(target=run_observer, daemon=True)
        self._watcher_thread.start()

    def stop_file_watcher(self):
        self._stop_event.set()
        if self._watcher_thread:
            self._watcher_thread.join()

    def _load_config(self, filename: str) -> dict:
        config = {}
        try:
            with open(filename, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = parts[1].strip()
                        if self._validate_config_entry(key, value):
                            config[key] = value
                    else:
                        print(f"Warning: Skipping malformed line in {filename}: {line}")
        except FileNotFoundError:
            pass # Silently allow a config file to be missing
        return config

    def _validate_config_entry(self, key: str, value: str) -> bool:
        """Validate a configuration entry"""
        if not key or not value:
            return False
        if len(key) > BUFFER_SIZE:
            print(f"Warning: Key '{key}' exceeds buffer size {BUFFER_SIZE}")
            return False
        return True

    def _clear_buffer(self):
        self.buffer = ""

    def _add_to_buffer(self, char):
        self.buffer += char
        if len(self.buffer) > BUFFER_SIZE:
            self.buffer = self.buffer[-BUFFER_SIZE:]

    def process_char(self, char: str):
        if not char or len(char) != 1:
            return

        if char == '\b': # Handle Backspace character
            if self.buffer:
                self.buffer = self.buffer[:-1]
            return # Don't clear buffer or process further for backspace

        if char.islower():
            self._add_to_buffer(char)
            if self.buffer in self.config:
                self._check_buffer_for_match()
        else:
            # For any other non-lowercase char (space, numbers, symbols, or the generic '*' from monitor)
            self._clear_buffer()

    def _check_buffer_for_match(self):
        if self.buffer in self.config:
            action_string = self.config[self.buffer]
            print(f"Parser: Match for {self.buffer!r} -> {action_string!r}")
            if self.monitor_ref: self.monitor_ref.pause_monitoring()
            self._execute_replacement_action(self.buffer, action_string)
            if self.monitor_ref:
                time.sleep(0.1) 
                self.monitor_ref.resume_monitoring()
            self._clear_buffer()

    def _parse_key_sequence(self, sequence_str: str) -> list[str]:
        """Parses a key sequence like 'meta+alt+a' into ydotool key names."""
        parts = sequence_str.lower().split('+')
        key_codes: list[str] = []

        for part in parts:
            part = part.strip()

            # Determine the KEY_* symbolic name first
            if part in MODIFIER_MAP:
                key_name = MODIFIER_MAP[part]
            elif part in SPECIAL_KEY_MAP:
                key_name = SPECIAL_KEY_MAP[part]
            elif len(part) == 1 and part.isalnum():  # Single alphanumeric character
                key_name = f"KEY_{part.upper()}"
            else:
                print(f"Warning: Unknown key or modifier '{part}' in sequence '{sequence_str}'")
                continue  # Skip unknown parts

            # Convert KEY_* symbolic name to its numeric evdev code
            key_code = _key_name_to_code(key_name)
            if key_code is None:
                print(f"Warning: Unable to map '{key_name}' to evdev code. Skipping.")
                continue

            key_codes.append(key_code)

        return key_codes

    def _send_key_command(self, command_name: str):
        if command_name not in self.key_commands:
            print(f"Parser Error: Key command '{command_name}' not found in commands.config.")
            return

        sequence_str = self.key_commands[command_name]
        ydotool_keys = self._parse_key_sequence(sequence_str)

        if not ydotool_keys:
            print(f"Parser Error: No valid keys found for command '{command_name}' ('{sequence_str}').")
            return

        # Construct ydotool command: press all keys, then release in reverse order
        press_keys_str = ' '.join([f"{key}:1" for key in ydotool_keys])
        release_keys_str = ' '.join([f"{key}:0" for key in reversed(ydotool_keys)])
        
        ydotool_command = ["ydotool", "key"] + press_keys_str.split() + release_keys_str.split()
        try:
            subprocess.run(ydotool_command, check=True)
            time.sleep(0.1)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Error executing ydotool key command for '{command_name}': {e}")
            
    def _type_string(self, text_to_type: str):
        """Types a string using ydotool."""
        if not text_to_type:
            return
        print(f"Parser Action: Typing text '{text_to_type}'.")
        try:
            ydotool_command = ["ydotool", "type", text_to_type]
            subprocess.run(ydotool_command, check=True, timeout=10)
            time.sleep(0.05)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Error executing ydotool type command for '{text_to_type}': {e}")
        except subprocess.TimeoutExpired:
            print(f"Error: ydotool type command for '{text_to_type}' timed out.")

    def _paste_text_segment_via_clipboard(self, text_segment: str):
        if not text_segment:
            return
        print(f"Parser Action: Pasting text \'{text_segment}\' via clipboard (systemd-run).")
        try: 
            #original_user = os.environ.get('SUDO_USER')
            #if not original_user:
            #    print("Error: SUDO_USER not set. Required for systemd-run --user.")
            #    raise Exception("SUDO_USER environment variable is not set.")
            escaped_text = text_segment.replace("'", "'\''")
            #user_shell_cmd = f"sudo -u {original_user} bash -c \"export XDG_RUNTIME_DIR=/run/user/$(id -u {original_user}) && export WAYLAND_DISPLAY=wayland-0 && echo -n '{escaped_text}' | wl-copy -n\""
            user_shell_cmd = f"echo -n '{escaped_text}' | wl-copy -n"
            #print(f"Executing for clipboard (as {original_user}): {user_shell_cmd}")
            os.system(user_shell_cmd)
            print("Successfully initiated copy to clipboard.")
            time.sleep(0.07) # Increased delay significantly to ensure clipboard is ready and focus might settle

            # Simulate Ctrl+V to paste with small delays between key actions
            # KEY_LEFTCTRL = 29, KEY_V = 47
            # ydotool sleep command takes milliseconds
            paste_cmd = f"ydotool key {KEY_LEFTCTRL}:1 sleep 20 {KEY_V}:1 sleep 20 {KEY_V}:0 sleep 20 {KEY_LEFTCTRL}:0"
            print(f"Executing paste: {paste_cmd}")
            os.system(paste_cmd)
            time.sleep(0.1) # Slightly longer sleep after paste too
        except subprocess.TimeoutExpired:
            print("Error: systemd-run command for wl-copy timed out.")
        except subprocess.CalledProcessError as e:
            print(f"Clipboard copy via systemd-run failed (details should have been printed before this).")
        except FileNotFoundError:
            print("Error: \'systemd-run\' or \'sh\' (as part of systemd-run) command not found.")
        except Exception as e:
            print(f"Unexpected error during clipboard paste: {e}")

    def _execute_replacement_action(self, matched_string: str, action_string: str):
        print(f"Parser Action: Executing replacement for \'{matched_string}\' -> \'{action_string}\'")
        
        # 1. Delete the matched string
        print(f"Parser Action: Deleting typed match \'{matched_string}\' (length: {len(matched_string)})")
        try:
            backspace_events = []
            for _ in range(len(matched_string)):
                backspace_events.append(f"{KEY_BACKSPACE}:1") # Backspace down
                backspace_events.append(f"{KEY_BACKSPACE}:0") # Backspace up
            if backspace_events:
                os.system(f"ydotool key {' '.join(backspace_events)}")
                time.sleep(0.05)
        except Exception as e: print(f"Error during backspacing: {e}")

        # 2. Parse and execute action string segments
        segments = re.split(r'(`[^`]+`)', action_string)
        for segment in segments:
            if not segment:
                continue

            if segment.startswith('`') and segment.endswith('`'):
                command = segment[1:-1]  # Strip backticks
                if command in self.key_commands:
                    self._send_key_command(command)
                else:
                    self._type_string(command)
            else:
                self._paste_text_segment_via_clipboard(segment)
        
        print(f"Parser: Actions for \'{matched_string}\' complete.")