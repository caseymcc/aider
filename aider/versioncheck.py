import time
from pathlib import Path

import packaging.version

import aider
from aider import utils
from aider.dump import dump  # noqa: F401


def check_version(just_check=False):
    fname = Path.home() / ".aider" / "caches" / "versioncheck"
    if not just_check and fname.exists():
        day = 60 * 60 * 24
        since = time.time() - fname.stat().st_mtime
        if since < day:
            return False, ""

    # To keep startup fast, avoid importing this unless needed
    import requests

    try:
        response = requests.get("https://pypi.org/pypi/aider-chat/json")
        data = response.json()
        latest_version = data["info"]["version"]
        current_version = aider.__version__

        if just_check:
            io.tool_output(f"Current version: {current_version}")
            io.tool_output(f"Latest version: {latest_version}")

        is_update_available = packaging.version.parse(latest_version) > packaging.version.parse(
            current_version
        )
    except Exception as err:
        return False, "Error checking pypi for new version: {err}"
    finally:
        fname.parent.mkdir(parents=True, exist_ok=True)
        fname.touch()

    if just_check:
        if is_update_available:
            io.tool_output("Update available")
        else:
            io.tool_output("No update available")
        return is_update_available

    if not is_update_available:
        return False, ""

    return True, latest_version

