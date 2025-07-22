#!/usr/bin/env bash

# Check for config files in home directory
CONFIG_DIR="$HOME/.config/risky-text-expander"
CONFIG_FILE="$CONFIG_DIR/config"
COMMANDS_CONFIG_FILE="$CONFIG_DIR/commands.config"

if [[ ! -f "$CONFIG_FILE" ]] || [[ ! -f "$COMMANDS_CONFIG_FILE" ]]; then
    echo "creating config files"
    mkdir -p "$CONFIG_DIR"
    
    if [[ ! -f "$CONFIG_FILE" ]]; then
        cp config.example "$CONFIG_FILE"
    fi
    
    if [[ ! -f "$COMMANDS_CONFIG_FILE" ]]; then
        cp commands.config.example "$COMMANDS_CONFIG_FILE"
    fi
fi

# Check if user is root or member of input group
if [[ $EUID -ne 0 && $(groups | grep -c 'input') -eq 0 ]]; then
    echo -e "\033[31mWarning: ydotoold must have input or root permissions.\033[0m"
fi

# Start ydotoold and the application
ydotoold &
sleep 2
if grep -q 'ID=nixos' /etc/os-release 2>/dev/null; then
    nix-shell -p python3Packages.evdev python3Packages.watchdog --run 'python -m risky_text_expander.launcher'
else
    python -m risky_text_expander.launcher
fi
