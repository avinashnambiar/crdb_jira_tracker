"""
CRDB Tracker - Silent Launcher
Double-click this file to start the server silently and open the tracker.
(.pyw extension = runs with pythonw automatically, no console window)
"""

import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

PORT = 8091
URL = f"http://localhost:{PORT}/crdbtracker.html"


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def main():
    # Change to script's directory so server.py can find its files
    script_dir = Path(__file__).parent.resolve()

    if not is_port_in_use(PORT):
        # Start server.py detached and hidden
        subprocess.Popen(
            [sys.executable, "server.py"],
            cwd=str(script_dir),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        # Wait for server to be ready
        for _ in range(20):
            time.sleep(0.25)
            if is_port_in_use(PORT):
                break

    webbrowser.open(URL)


if __name__ == "__main__":
    main()
