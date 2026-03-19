"""Global fixtures for custom integration."""

from pathlib import Path
import sys

import pytest

WORKSPACE_ROOT = str(Path(__file__).resolve().parents[1])

# Home Assistant's loader treats every sys.path entry as a directory to scan for
# custom components. Editable-install sentinel entries are not real paths, so we
# strip them for tests and prepend the workspace root explicitly.
sys.path = [path for path in sys.path if not path.startswith("__editable__.kohler_ha-")]
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations defined in the test dir."""
    yield
