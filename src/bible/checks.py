"""The build's refusal: every check raises CheckFailed."""

from collections.abc import Collection, Mapping


class CheckFailed(RuntimeError):
    """A source, preparation, or output check refused the build."""


def require(condition: object, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


def present[T](value: T | None, message: str) -> T:
    """The value, which must not be missing."""
    if value is None:
        raise CheckFailed(message)
    return value


def require_fields(
    entry: object,
    required: Collection[str],
    optional: Collection[str],
    what: str,
) -> None:
    """A declaration must have its fields and no others: a misspelt one would
    otherwise be read as absent."""
    require(
        isinstance(entry, Mapping)
        and set(required) <= set(entry) <= set(required) | set(optional),
        f"{what} has missing or unknown fields",
    )
