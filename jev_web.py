#!/usr/bin/env python3
"""
Jev Web Dashboard Launcher.

Usage:
  # Launch web server on port 5050 and auto open browser:
  python jev_web.py

  # Custom host and port:
  python jev_web.py --port 8080 --host 0.0.0.0
"""

import argparse
import sys
import webbrowser
from pathlib import Path
import threading
import time

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.jev.web_app import app


def open_browser_later(url: str, delay: float = 1.0) -> None:
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser(description="Jev Model Web Dashboard & Timing Monitor")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host IP to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5050, help="Port to bind (default: 5050)")
    parser.add_argument("--no-open", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    print("=" * 70)
    print("  TypeSafe Jev 页面元素判断与耗时监控 Web 工作台已就绪")
    print(f"  访问地址: {url}")
    print("  按 Ctrl+C 可停止 Web 服务器")
    print("=" * 70)

    if not args.no_open and args.host in ("127.0.0.1", "localhost"):
        open_browser_later(url, delay=1.2)

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
