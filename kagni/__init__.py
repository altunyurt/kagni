"""Repo-root shim so ``import kagni`` resolves to ``src/kagni`` even when
the checkout root is on sys.path (where the root ``kagni.py`` launcher
would otherwise shadow the package as a plain module).
"""
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
__path__ = [os.path.join(_ROOT, "src", "kagni")]
