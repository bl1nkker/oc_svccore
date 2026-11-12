import json
import logging
import sys

import click

from oc_svccore import config
from oc_svccore.config import ConfigError
from oc_svccore.errors import BaseError

LEVELS = (logging.WARNING, logging.INFO, logging.DEBUG)

log = logging.getLogger(__name__)


class _Commands(click.Group):
    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except (click.ClickException, click.exceptions.Exit, click.Abort):
            raise
        except BaseError as e:
            click.echo(f"error: {e.message} {json.dumps(e.data)}" if e.data else f"error: {e.message}", err=True)
        except ConfigError as e:
            click.echo(f"error: {e}", err=True)
        except Exception:
            log.exception("command failed")
        ctx.exit(1)


def create_app(service: str) -> click.Group:
    @click.group(name=service, cls=_Commands)
    @click.option("-v", "--verbose", count=True, help="Show INFO logs, -vv for DEBUG.")
    @click.pass_context
    def app(ctx: click.Context, verbose: int) -> None:
        # Logs go to stderr as plain text, so they never mix with what a command prints.
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root, level = logging.getLogger(), logging.getLogger().level
        root.addHandler(handler)
        root.setLevel(LEVELS[min(verbose, len(LEVELS) - 1)])
        ctx.call_on_close(lambda: (root.removeHandler(handler), root.setLevel(level)))
        config.setup(service)

    return app
