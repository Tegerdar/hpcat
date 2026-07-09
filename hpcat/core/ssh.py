import subprocess
from typing import Dict, Tuple, Union

DEFAULT_SSH_TIMEOUT = 3

# How much extra wall-clock time we give subprocess.run() on top of the SSH
# ConnectTimeout, to allow for the remote command itself to run.
DEFAULT_EXTRA_TIMEOUT = 2


def ssh_run(
    node: str,
    command: str,
    timeout: int = DEFAULT_SSH_TIMEOUT,
    extra_timeout: int = DEFAULT_EXTRA_TIMEOUT,
) -> subprocess.CompletedProcess:
    """Run `command` on `node` with hpcat's standard batch SSH options.

    Raises subprocess.TimeoutExpired or OSError on failure - use ssh_poll()
    instead if you just want an {"error": ...} dict back.
    """
    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={timeout}",
        "-o", "StrictHostKeyChecking=no",
        "-o", "LogLevel=QUIET",
        node,
        command,
    ]
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout + extra_timeout
    )


def ssh_poll(
    node: str,
    command: str,
    timeout: int = DEFAULT_SSH_TIMEOUT,
    extra_timeout: int = DEFAULT_EXTRA_TIMEOUT,
    fail_label: str = "ssh_command_failed",
) -> Union[Tuple[subprocess.CompletedProcess, None], Tuple[None, Dict[str, str]]]:
    """Run `command` on `node`, collapsing every failure mode into the same
    {"error": ...} shape the command modules already return today.

    Returns (result, None) on success, or (None, error_dict) on failure -
    callers do `result, err = ssh_poll(...); if err: return node, err`.
    """
    try:
        result = ssh_run(node, command, timeout=timeout, extra_timeout=extra_timeout)
        if result.returncode != 0:
            return None, {"error": fail_label}
        return result, None
    except subprocess.TimeoutExpired:
        return None, {"error": "timeout"}
    except Exception as e:
        return None, {"error": str(e)}
