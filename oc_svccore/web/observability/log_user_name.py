import logging

from oc_svccore.web.auth.current_principal import principal_in_request

_installed = False


def log_user_name() -> None:
    global _installed
    if _installed:
        return
    make_record = logging.getLogRecordFactory()

    # A record factory, not a handler filter: dictConfig replaces the handlers and would drop a filter.
    def record_with_user_name(*args, **kwargs) -> logging.LogRecord:
        record = make_record(*args, **kwargs)
        if principal := principal_in_request():
            setattr(record, "user.name", principal.username)
        return record

    logging.setLogRecordFactory(record_with_user_name)
    _installed = True
