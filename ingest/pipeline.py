"""Entry point: python -m ingest.pipeline [--force]

--force also runs consolidation even if fewer than CONSOLIDATE_AFTER notes
are pending (used by the daily scheduled Action run, so nothing sits
unconsolidated for long)."""
from __future__ import annotations

import sys

from . import consolidate, sync


def run(force: bool = False) -> None:
    diff = sync.sync()
    print(f"sync: {diff}")
    result = consolidate.run(force=force)
    print(f"consolidate: {result}")


if __name__ == "__main__":
    run(force="--force" in sys.argv)
