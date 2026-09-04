#!/usr/bin/env python3
"""Kagni — a Redis-like data store (RESP over TCP / unix sockets, sqlite
snapshots).  Pick the event-loop backend with --loop asyncio|trio.

    ./kagni.py --help
    uv run kagni --loop trio --port 6380
"""

import os
import sys

# src-layout bootstrap: let the repo checkout run without installing
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from kagni.cli import main

if __name__ == "__main__":
    sys.exit(main())
