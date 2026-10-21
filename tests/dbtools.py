"""Test helper: give every test its own empty SQLite database.

Import this module BEFORE anything that imports app.services, so DATABASE_PATH points at a
temporary location instead of the real refund_guardian.db.
"""
import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="refund-guardian-tests-")
os.environ.setdefault("DATABASE_PATH", os.path.join(_TMP_DIR, "initial.db"))

from app import services  # noqa: E402  (must come after DATABASE_PATH is set)

_counter = 0


def use_fresh_db() -> str:
    """Point services at a brand-new database file and create the schema. Call from setup_function."""
    global _counter
    _counter += 1
    services.DB_PATH = os.path.join(_TMP_DIR, f"test-{_counter}.db")
    services.init_db()
    return services.DB_PATH
