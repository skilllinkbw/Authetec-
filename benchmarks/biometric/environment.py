"""Run-environment provenance capture.

Every benchmark result must record the environment it ran in: timestamp,
Git commit, hardware and software versions.  This makes results
reproducible and comparable.
"""

from __future__ import annotations

import datetime
import os
import platform
import subprocess
import sys
from typing import Any, Dict


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], capture_output=True, text=True,
            timeout=5, check=False,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def _try_version(name: str, package_name: str) -> str:
    try:
        mod = __import__(package_name)
        v = getattr(mod, "__version__", "")
        return str(v) if v else "unknown"
    except Exception:
        return "not_installed"


def capture_environment() -> Dict[str, Any]:
    """Capture timestamp, Git state, hardware and software provenance."""
    env: Dict[str, Any] = {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="seconds"),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_branch": _git("branch", "--show-current"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "cpu_count": os.cpu_count() or 0,
        "ram_total_gb": _ram_gb(),
    }
    env["packages"] = {
        "numpy": _try_version("numpy", "numpy"),
        "opencv": _try_version("cv2", "cv2"),
        "onnxruntime": _try_version("onnxruntime", "onnxruntime"),
        "pillow": _try_version("PIL", "PIL"),
    }
    return env


def _ram_gb() -> float:
    try:
        if sys.platform == "win32":
            total = 0
            out = subprocess.run(
                ["wmic", "ComputerSystem", "get", "TotalPhysicalMemory"],
                capture_output=True, text=True, timeout=10, check=False,
            ).stdout
            for line in out.splitlines():
                if line.strip().isdigit():
                    total = int(line.strip())
            return round(total / (1024 ** 3), 1)
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
                     / (1024 ** 3), 1)
    except Exception:
        return 0.0