from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CORE_SRC = ROOT / "packages" / "aether_core" / "src"

if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

