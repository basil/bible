"""The build's refusal: every check raises CheckFailed."""


class CheckFailed(RuntimeError):
    """A source, preparation, or output check refused the build."""


def require(condition, message):
    if not condition:
        raise CheckFailed(message)


def require_fields(entry, required, optional, what):
    """A declaration must have its fields and no others: a misspelt one would
    otherwise be read as absent."""
    require(
        hasattr(entry, "keys")
        and set(required) <= set(entry) <= set(required) | set(optional),
        f"{what} has missing or unknown fields",
    )
