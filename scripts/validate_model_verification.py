"""Read-only H2 plan and material comparison decisions."""
from validate_verification import main, validate_verification


def validate_model_verification(path, **kwargs):
    return validate_verification(path, kind='H2', **kwargs)


if __name__ == '__main__':
    raise SystemExit(main('H2'))
