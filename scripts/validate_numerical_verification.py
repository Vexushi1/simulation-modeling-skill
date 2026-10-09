"""Read-only H1 plan checks; --require-reviewed is a distinct source-review gate."""
from validate_verification import main, validate_verification


def validate_numerical_verification(path, **kwargs):
    return validate_verification(path, kind='H1', **kwargs)


if __name__ == '__main__':
    raise SystemExit(main('H1'))
