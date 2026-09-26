"""The build's refusal: every check raises CheckFailed."""


class CheckFailed(RuntimeError):
    """A source, preparation, or output check refused the build."""


def require(condition, message):
    if not condition:
        raise CheckFailed(message)
