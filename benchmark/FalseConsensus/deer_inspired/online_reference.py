"""CLI compatibility wrapper for the online DEER reference."""

from __future__ import annotations

import sys

from .online_controller import main


if __name__ == "__main__":
    main(["--method", "deer_online_reference", *sys.argv[1:]])
