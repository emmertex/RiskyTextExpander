'''Launcher for RiskyTextExpander.

Manages the Monitor and Parser components.
Provides a simple way to start and stop the service.
'''
import asyncio
import signal
import subprocess

from risky_text_expander.monitor import Monitor
from risky_text_expander.parser import Parser

class AppLauncher:
    def __init__(self):
        self.monitor_task = None
        self.monitor_instance = None
        self.parser_instance = None
        self._running = False

    def _is_ydotoold_running_as_root(self) -> bool:
        try:
            result = subprocess.run(["pgrep", "-x", "ydotoold"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                # print(f"Launcher: Found ydotoold process(es) running as root (PIDs: {result.stdout.strip().split('\n')}).") # Verbose
                return True
            # else: # Verbose
                # print("Launcher: ydotoold process not found running as root.")
            return False
        except FileNotFoundError:
            print("Launcher Error: pgrep command not found. Cannot check for ydotoold process.")
            return False 
        except Exception as e:
            print(f"Launcher Error: Error checking for ydotoold process: {e}")
            return False

    async def start_service(self):
        if self._running:
            print("Launcher: Service is already running.")
            return

        # print("Launcher: Checking for ydotoold daemon...") # A bit verbose for normal start
        if not self._is_ydotoold_running_as_root():
            print("-------------------------------------------------------------------------------------")
            print("IMPORTANT: The 'ydotoold' daemon is not running as root, or cannot be detected.")
            print("RiskyTextExpander requires 'ydotoold' to be running as root.")
            print("Please start it in another terminal using: sudo ydotoold")
            print("Then, re-run this launcher.")
            print("-------------------------------------------------------------------------------------")
            return

        print("Launcher: Initializing service...")
        self.parser_instance = Parser()
        self.monitor_instance = Monitor(parser_instance=self.parser_instance)
        self.parser_instance.monitor_ref = self.monitor_instance

        print("Launcher: Starting monitoring task...")
        self._running = True
        self.monitor_task = asyncio.create_task(self.monitor_instance.start_monitoring())

        try:
            await self.monitor_task
        except asyncio.CancelledError:
            print("Launcher: Monitor task was cancelled.")
        # except Exception as e: # Can be too noisy if monitor handles its own errors
            # print(f"Launcher: Monitor task exited with an error: {e}")
        finally:
            print("Launcher: Service has stopped.")
            self._running = False
            self.monitor_task = None
            self.monitor_instance = None
            self.parser_instance = None

    async def stop_service(self):
        if not self._running or not self.monitor_instance or not self.monitor_task:
            # print("Launcher: Service is not running or not fully initialized for stop.") # Verbose
            return

        print("Launcher: Attempting to stop service gracefully...")        
        if self.monitor_instance: self.monitor_instance.stop_monitoring()

        try:
            if self.monitor_task: await asyncio.wait_for(self.monitor_task, timeout=2.0) 
        except asyncio.TimeoutError:
            print("Launcher: Timeout waiting for monitor task to stop. Cancelling.")
            if self.monitor_task: self.monitor_task.cancel()
            try:
                if self.monitor_task: await self.monitor_task
            except asyncio.CancelledError:
                print("Launcher: Monitor task successfully cancelled after timeout.")
        # except Exception as e: # Can be noisy
            # print(f"Launcher: Error during service stop: {e}")
        finally:
            self._running = False
            # print("Launcher: Stop sequence complete.") # Verbose

launcher_instance = AppLauncher()

async def main_launcher():
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))
    
    print("RiskyTextExpander: Service starting. Press Ctrl+C to stop.")
    await launcher_instance.start_service()
    # print("Launcher: Service has concluded.") # Verbose

async def shutdown(sig):
    print(f"RiskyTextExpander: Received signal {sig.name}. Shutting down...")
    await launcher_instance.stop_service()
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if tasks:
        # print(f"Launcher: Cancelling {len(tasks)} outstanding tasks...") # Verbose
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    
if __name__ == "__main__":
    try:
        asyncio.run(main_launcher())
    except KeyboardInterrupt:
        print("RiskyTextExpander: Exiting via KeyboardInterrupt.")
    except PermissionError:
        print("RiskyTextExpander Error: Permission denied. This application usually needs elevated privileges (sudo).")
    except Exception as e:
        print(f"RiskyTextExpander Error: An unexpected critical error occurred: {e}")
    finally:
        print("RiskyTextExpander: Shutdown complete.") 
