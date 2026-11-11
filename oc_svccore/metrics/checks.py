import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

Check = Callable[[], None]

CHECK_TIMEOUT_SECONDS = 2.0

_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="oc-svccore-check")
_up: dict[str, bool] = {}
_up_lock = threading.Lock()


def run_checks(checks: dict[str, Check]) -> dict[str, bool]:
    futures = {name: _pool.submit(check) for name, check in checks.items()}
    deadline = time.monotonic() + CHECK_TIMEOUT_SECONDS
    results = {}
    for name, future in futures.items():
        reason = None
        try:
            future.result(timeout=max(0.0, deadline - time.monotonic()))
        except Exception as e:
            reason = str(e) or type(e).__name__
        results[name] = reason is None
        _log_change(name, reason)
    return results


# Checks run on every scrape and /health call, so only a change of state is logged, not every failure.
def _log_change(name: str, reason: str | None) -> None:
    up = reason is None
    with _up_lock:
        changed = _up.get(name, True) != up
        _up[name] = up
    if changed and up:
        log.info("dependency check recovered", extra={"dependency": name})
    elif changed:
        log.warning("dependency check failed", extra={"dependency": name, "reason": reason})
