#!/usr/bin/env python3
"""
Jev Model Element Decision CLI Entrypoint.

Usage:
  # Interactive mode:
  python jev_cli.py

  # Automated test mode:
  python jev_cli.py --task "在百度搜索框输入 python 并点击搜索" --url "https://www.baidu.com" --headless --auto-confirm --execute
"""

import sys
from pathlib import Path

# Ensure root directory is in sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv

env_file = ROOT_DIR / ".env"
if env_file.is_file():
    load_dotenv(env_file, override=True)

from src.jev.jev_demo import main

if __name__ == "__main__":
    main()
