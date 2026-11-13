from pathlib import Path

from oc_svccore.testing import assert_spec

SPEC = Path(__file__).resolve().parent.parent / "spec" / "openapi.yaml"


def test_routes_match_the_spec(app):
    assert_spec(app, SPEC)
