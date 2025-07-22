'''Input monitoring for RiskyTextExpander.'''

import asyncio
import time
import contextlib
from evdev import InputDevice, categorize, ecodes, list_devices

KEY_MAP = {
    # Letters
    "A": ("a", "A"), "B": ("b", "B"), "C": ("c", "C"), "D": ("d", "D"),
    "E": ("e", "E"), "F": ("f", "F"), "G": ("g", "G"), "H": ("h", "H"),
    "I": ("i", "I"), "J": ("j", "J"), "K": ("k", "K"), "L": ("l", "L"),
    "M": ("m", "M"), "N": ("n", "N"), "O": ("o", "O"), "P": ("p", "P"),
    "Q": ("q", "Q"), "R": ("r", "R"), "S": ("s", "S"), "T": ("t", "T"),
    "U": ("u", "U"), "V": ("v", "V"), "W": ("w", "W"), "X": ("x", "X"),
    "Y": ("y", "Y"), "Z": ("z", "Z"),
    # Numbers
    "1": ("1", "!"), "2": ("2", "@"), "3": ("3", "#"), "4": ("4", "$"),
    "5": ("5", "%"), "6": ("6", "^"), "7": ("7", "&"), "8": ("8", "*"),
    "9": ("9", "("), "0": ("0", ")"),
    # Punctuation
    "MINUS": ("-", "_"), "EQUAL": ("=", "+"),
    "LEFTBRACE": ("[", "{"), "RIGHTBRACE": ("]", "}"),
    "BACKSLASH": ("\\", "|"),
    "SEMICOLON": (";", ":"), "APOSTROPHE": ("'", '"'),
    "GRAVE": ("`", "~"),
    "COMMA": (",", "<"), "DOT": (".", ">"), "SLASH": ("/", "?"),
    # Special
    "SPACE": (" ", " "),
}


class Monitor:
    def __init__(self, parser_instance):
        self.parser = parser_instance
        self.device_path = None
        self.device = None
        self.is_monitoring = False
        self.is_paused = False
        self.shift_pressed = False # Basic shift state tracking
        self.last_selected_device_path = None  # Track last selected device path

    async def _find_keyboard_device(self):
        devices = [InputDevice(path) for path in list_devices()]
        candidate_devices = []

        for device in devices:
            device_name_lower = device.name.lower()
            # Filter out known virtual devices or devices we don't want to monitor
            if "virtual" in device_name_lower or \
               "ydotool" in device_name_lower or \
               "dummy" in device_name_lower or \
               "mouse" in device_name_lower or \
               "touchpad" in device_name_lower or \
               "power button" in device_name_lower or \
               "sleep button" in device_name_lower or \
               "mx" in device_name_lower or \
               "webcam" in device_name_lower:
                continue

            capabilities = device.capabilities(verbose=False)
            if ecodes.EV_KEY in capabilities:
                has_common_keys = False
                try:
                    key_bits = capabilities[ecodes.EV_KEY]
                    required_keys = [
                        ecodes.KEY_A, ecodes.KEY_Q, ecodes.KEY_W, ecodes.KEY_E, ecodes.KEY_R, ecodes.KEY_T, ecodes.KEY_Y,
                        ecodes.KEY_SPACE, ecodes.KEY_ENTER, ecodes.KEY_LEFTSHIFT, ecodes.KEY_BACKSPACE
                    ]
                    if all(key_code in key_bits for key_code in required_keys):
                        has_common_keys = True
                except KeyError:
                    pass # Device might not have verbose key listings
                
                if has_common_keys:
                    candidate_devices.append(device)


        if not candidate_devices:
            print("Monitor Error: No suitable keyboard device found after filtering.")
            return None
        
        if len(candidate_devices) == 1:
            selected_device = candidate_devices[0]
            self.device_path = selected_device.path
            # Only print if device changed
            if self.last_selected_device_path != selected_device.path:
                print(f"Monitor: Auto-selected keyboard device: {selected_device.name}")
                self.last_selected_device_path = selected_device.path
            return selected_device
        else:
            # Multiple candidates found - use more specific criteria
            selected_device = self._select_best_keyboard(candidate_devices)
            if selected_device:
                # Only print if device changed
                if self.last_selected_device_path != selected_device.path:
                    print(f"Monitor: Auto-selected keyboard device: {selected_device.name}")
                    self.last_selected_device_path = selected_device.path
                self.device_path = selected_device.path
                return selected_device
            else:
                # Fall back to user selection
                selected_device = self._prompt_user_keyboard_selection(candidate_devices)
                if selected_device:
                    self.device_path = selected_device.path
                    self.last_selected_device_path = selected_device.path
                    return selected_device
                else:
                    print("Monitor Error: No keyboard device selected.")
                    return None

    def _select_best_keyboard(self, candidate_devices):
        """
        Apply heuristics to automatically select the best keyboard from multiple candidates.
        Returns the selected device or None if unable to auto-select.
        """
        # Priority keywords for automatic selection (higher priority first)
        priority_keywords = [
            # Enthusiast Keyboards
            ["zmk", "keyboard"],
            ["qmk", "keyboard"],
            ["sofle", "rgb"],
            ["zsa", "keyboard"],
            
            # Common keyboard brands
            ["asustek", "keyboard"],
            ["logitech", "keyboard"],
            ["microsoft", "keyboard"], 
            ["dell", "keyboard"],
            ["hp", "keyboard"],
            ["lenovo", "keyboard"],
            ["thinkpad", "keyboard"],
            
            # Generic keyboard indicators
            ["usb", "keyboard"],
            ["keyboard"]
        ]
        
        for priority_group in priority_keywords:
            for device in candidate_devices:
                device_name_lower = device.name.lower()
                if all(keyword in device_name_lower for keyword in priority_group):
                    # print(f"Monitor: Auto-selected based on priority: {device.name}")  # Suppress duplicate message; _find_keyboard_device will announce final selection
                    return device
        
        # If no priority match, check if there's a clear "main" keyboard
        # by looking for devices with more comprehensive key mappings
        best_device = None
        max_key_count = 0
        
        for device in candidate_devices:
            capabilities = device.capabilities(verbose=False)
            if ecodes.EV_KEY in capabilities:
                key_count = len(capabilities[ecodes.EV_KEY])
                if key_count > max_key_count:
                    max_key_count = key_count
                    best_device = device
        
        # Only auto-select if one device has significantly more keys
        if best_device and max_key_count > 0:
            # print(f"Monitor: Auto-selected device with most keys: {best_device.name}")  # Suppress duplicate message; final announcement handled elsewhere
            other_max = max(len(dev.capabilities(verbose=False).get(ecodes.EV_KEY, [])) 
                           for dev in candidate_devices if dev != best_device)
            if max_key_count > other_max * 1.5:  # 50% more keys
                return best_device
        
        return None  # Unable to auto-select
    
    def _prompt_user_keyboard_selection(self, candidate_devices):
        """
        Prompt the user to select from multiple keyboard candidates.
        Returns the selected device or None if cancelled.
        """
        print(f"\nMonitor: Found {len(candidate_devices)} keyboard candidates:")
        for i, device in enumerate(candidate_devices):
            capabilities = device.capabilities(verbose=False)
            key_count = len(capabilities.get(ecodes.EV_KEY, []))
            print(f"  {i + 1}: {device.name}")
            print(f"      Path: {device.path}")
            print(f"      Keys: {key_count}")
        
        while True:
            try:
                choice = input(f"\nSelect keyboard (1-{len(candidate_devices)}, or 'q' to quit): ").strip()
                
                if choice.lower() == 'q':
                    return None
                
                choice_num = int(choice)
                if 1 <= choice_num <= len(candidate_devices):
                    selected_device = candidate_devices[choice_num - 1]
                    print(f"Monitor: Selected keyboard device: {selected_device.name}")
                    return selected_device
                else:
                    print(f"Please enter a number between 1 and {len(candidate_devices)}")
                    
            except ValueError:
                print("Please enter a valid number or 'q' to quit")
            except (EOFError, KeyboardInterrupt):
                print("\nMonitor: Selection cancelled.")
                return None

    def pause_monitoring(self):
        if self.is_monitoring:
            # print("Monitor: Pausing monitoring.") # Verbose
            self.is_paused = True

    def resume_monitoring(self):
        if self.is_monitoring:
            # print("Monitor: Resuming monitoring.") # Verbose
            self.is_paused = False
            self.shift_pressed = False # Reset shift state on resume

    async def start_monitoring(self, rescan_interval: int = 3):
        """
        Start monitoring key events.

        The coroutine now handles hot-plugging:
          • If the active keyboard is unplugged, monitoring will automatically
            pause and re-scan until a suitable device is found.
          • When a new keyboard with higher priority is plugged in, the monitor
            will seamlessly switch over to it (keeping the same buffer/parser
            logic).

        The search frequency is controlled by `rescan_interval` (seconds).
        """

        self.is_monitoring = True

        while self.is_monitoring:
            # Attempt to (re)acquire the best keyboard available.
            self.device = await self._find_keyboard_device()
            if not self.device:
                # Nothing suitable found – wait a bit before trying again.
                await asyncio.sleep(2)
                continue

            self.device_path = self.device.path
            print(f"Monitor: Listening to {self.device.name}…")

            # Launch a background task that periodically rescans for better devices.
            rescan_task = asyncio.create_task(
                self._periodic_rescan(rescan_interval), name="keyboard_rescan"
            )

            last_rescan = time.monotonic()

            try:
                async for event in self.device.async_read_loop():
                    # Stop request from outside
                    if not self.is_monitoring:
                        break

                    # Handle pause state
                    while self.is_paused and self.is_monitoring:
                        await asyncio.sleep(0.05)
                    if not self.is_monitoring:
                        break

                    # Existing key-processing logic
                    if event.type == ecodes.EV_KEY:
                        key_event = categorize(event)

                        # Shift tracking
                        if key_event.keycode in ["KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"]:
                            if key_event.keystate == key_event.key_down:
                                self.shift_pressed = True
                            elif key_event.keystate == key_event.key_up:
                                self.shift_pressed = False
                            continue

                        if key_event.keystate == key_event.key_down:
                            if key_event.keycode == "KEY_BACKSPACE":
                                char_to_send = '\b'
                            else:
                                char_to_send = self._keycode_to_char(key_event.keycode, self.shift_pressed)

                            if char_to_send:
                                self.parser.process_char(char_to_send)

                    # Periodically re-scan for better or replacement devices
                    now = time.monotonic()
                    if now - last_rescan >= rescan_interval:
                        last_rescan = now

                        candidate = await self._find_keyboard_device()
                        if candidate and candidate.path != self.device_path:
                            print(f"Monitor: Switching to new keyboard device: {candidate.name}")
                            # Close both the current device and the temporary candidate instance –
                            # the outer loop will immediately reopen the best device.
                            try:
                                self.device.close()
                            except Exception:
                                pass
                            try:
                                candidate.close()
                            except Exception:
                                pass
                            break  # Exit async_read_loop and restart outer while-loop

            except (OSError, IOError) as e:
                # Device likely disconnected
                print(f"Monitor: Device {self.device_path} disconnected ({e}). Re-scanning…")
            except KeyboardInterrupt:
                print("Monitor: Stopped by user (Ctrl+C).")
                self.is_monitoring = False
            except Exception as e:
                print(f"Monitor Error during event loop: {e}")
            finally:
                # Cancel background rescan task gracefully.
                if rescan_task and not rescan_task.done():
                    rescan_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await rescan_task

                if self.device:
                    try:
                        self.device.close()
                    except Exception:
                        pass
                    self.device = None

        # Clean-up after monitoring finishes
        self.is_paused = False

    async def _periodic_rescan(self, interval: int):
        """Background coroutine that checks for a better keyboard every *interval* seconds.

        Runs in parallel with the main event loop so we don't have to wait for key
        activity on the current device.  If a preferable new keyboard is found
        it closes the current device file-descriptor which causes the main
        async_read_loop to terminate cleanly, letting `start_monitoring` restart
        with the new device in the outer loop.
        """
        try:
            while self.is_monitoring and self.device:
                await asyncio.sleep(interval)

                # Double-check state: we might have been stopped during sleep.
                if not (self.is_monitoring and self.device):
                    break

                candidate = await self._find_keyboard_device()
                if candidate and candidate.path != self.device_path:
                    print(f"Monitor: Detected new preferred keyboard: {candidate.name}. Switching…")

                    # Close the temporary candidate to avoid FD leaks – we only
                    # used it to inspect properties.
                    with contextlib.suppress(Exception):
                        candidate.close()

                    # Closing the active device will raise inside the event
                    # loop, triggering a restart with the best keyboard.
                    with contextlib.suppress(Exception):
                        self.device.close()

                    break  # Exit the rescan loop – outer logic will relaunch
        except asyncio.CancelledError:
            # Normal shutdown path.
            pass

    def _keycode_to_char(self, keycode, shift_pressed):
        # This is a basic US QWERTY layout mapping using a unified key map.
        
        if isinstance(keycode, list): # e.g. ['KEY_LEFTSHIFT', 'KEY_A'] - evdev can sometimes do this
            keycode = keycode[-1] # Take the primary key

        if not isinstance(keycode, str):
            return None

        key_name = keycode.replace("KEY_", "")

        # Look up the key in our map
        if key_name in KEY_MAP:
            normal_char, shifted_char = KEY_MAP[key_name]
            return shifted_char if shift_pressed else normal_char

        # For unmapped keys, determine if we should clear the buffer.
        # We clear for special keys that aren't modifiers.
        if len(key_name) > 1 and key_name not in [
            "LEFTSHIFT", "RIGHTSHIFT", "LEFTCTRL", "RIGHTCTRL", 
            "LEFTALT", "RIGHTALT", "LEFTMETA", "RIGHTMETA"
        ]:
            # print(f"Monitor: Key {key_name} is a special key, sending generic clear.") # Verbose
            return "*" # Generic non-lowercase/non-backspace character to clear buffer
        
        return None

    def stop_monitoring(self):
        # print("Monitor: Received stop signal.") # Verbose
        print("Monitor: Received stop signal. Attempting to stop monitoring loop...")
        self.is_monitoring = False
        # If in read_loop, it will break. If paused, it will break when unpaused or on next check.
        # If device is not yet open (e.g. in _find_keyboard_device), this flag prevents loop from starting.
