"""Install current stable HA and its test harness without resolver fallback."""

import json
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen


def main() -> None:
    """Resolve exact current versions before pip solves their dependencies."""
    latest = []
    for package in ("homeassistant", "pytest-homeassistant-custom-component", "ruff"):
        with urlopen(f"https://pypi.org/pypi/{package}/json", timeout=30) as response:
            version = json.load(response)["info"]["version"]
        latest.append(f"{package}=={version}")
    print("Testing current releases: " + ", ".join(latest), flush=True)
    requirements = Path(__file__).resolve().parents[1] / "requirements.test.txt"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "-r",
            str(requirements),
            *latest,
        ],
        check=True,
    )
    subprocess.run([sys.executable, "-m", "pip", "check"], check=True)


if __name__ == "__main__":
    main()
