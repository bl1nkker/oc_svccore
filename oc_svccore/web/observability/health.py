from flask import Blueprint

from oc_svccore.metrics import Check, run_checks
from oc_svccore.web.auth.public import public


def health_blueprint(checks: dict[str, Check]) -> Blueprint:
    bp = Blueprint("oc_svccore_health", __name__)

    @bp.get("/health/liveness")
    @public
    def liveness():
        return {"status": "ok"}

    @bp.get("/health/readiness")
    @public
    def readiness():
        return {"status": "ok"}

    @bp.get("/health")
    @public
    def health():
        results = run_checks(checks)
        up = all(results.values())
        body = {"status": "ok" if up else "unavailable", "checks": {n: "ok" if ok else "fail" for n, ok in results.items()}}
        return body, 200 if up else 503

    return bp
