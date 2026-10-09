#!/usr/bin/env python3
"""Bear call spread scanner — wrapper for ``spread_scan.py --side call``.

For broken/downtrending names: short strike above resistance AND outside the
1-SD expected move; skipped when 25Δ skew is call-lean.

    python scripts/call_spread_scan.py BX --resistance 120 [--conviction half] [--submit]
"""

import sys

from spread_scan import main

if __name__ == "__main__":
    main(["--side", "call", *sys.argv[1:]])
