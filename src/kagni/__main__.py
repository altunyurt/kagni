"""Runnable-package entry point: ``python -m kagni``."""

import sys

from kagni.cli import main

if __name__ == "__main__":
    sys.exit(main())
