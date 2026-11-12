from oc_svccore.errors import InvalidDataError


class InvalidSortError(InvalidDataError):
    code = "invalid_sort"
