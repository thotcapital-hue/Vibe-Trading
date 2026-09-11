#!/usr/bin/env python3
"""Bull put spread scanner — wrapper for ``spread_scan.py --side put``.

    python scripts/put_spread_scan.py AAPL --support 300 [--conviction half] [--submit]
"""

import sys

from spread_scan import main

if __name__ == "__main__":
    main(["--side", "put", *sys.argv[1:]])
