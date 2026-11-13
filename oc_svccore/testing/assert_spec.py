import re
from os import PathLike

from flask import Flask

METHODS = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}
_PARAM = re.compile(r"<[^>]+>|\{[^}]+\}")


def assert_spec(app: Flask, spec_path: str | PathLike[str]) -> None:
    # PyYAML comes with the testing extra, and the pytest plugin imports this package without it.
    import yaml

    with open(spec_path) as f:
        spec = yaml.safe_load(f)
    served = {
        _key(method, rule.rule): (rule.endpoint, f"{method} {rule.rule}")
        for rule in app.url_map.iter_rules()
        if rule.endpoint != "static"
        for method in rule.methods - {"HEAD", "OPTIONS"}
    }
    documented = {
        _key(method.upper(), path): f"{method.upper()} {path}"
        for path, item in (spec.get("paths") or {}).items()
        for method in item.keys() & METHODS
    }
    own = {key for key, (endpoint, _) in served.items() if not endpoint.startswith("oc_svccore")}
    problems = [f"not in the spec: {served[key][1]}" for key in sorted(own - documented.keys())]
    problems += [f"not served: {documented[key]}" for key in sorted(documented.keys() - served.keys())]
    assert not problems, f"routes and {spec_path} differ:\n" + "\n".join(problems)


def _key(method: str, path: str) -> tuple[str, str]:
    return method, _PARAM.sub("{}", path)
