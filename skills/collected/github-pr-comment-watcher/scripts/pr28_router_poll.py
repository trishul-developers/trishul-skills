#!/usr/bin/env python3
"""Compatibility entry point for the existing PR #28 Windows task."""

import sys
from pathlib import Path

from pr_handoff_router_poll import main


if __name__ == "__main__":
    config = Path(r"E:\Projects\Ukrainian-Warfare\.agents\state\pr28_router_config.json")
    main(["--config", str(config), *sys.argv[1:]])
