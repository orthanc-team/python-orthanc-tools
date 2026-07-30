import os
from typing import Optional


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def get_env_bool(name: str, default: Optional[bool] = False) -> Optional[bool]:
    value = os.environ.get(name)
    if value is None:
        return default

    normalized_value = value.strip().lower()
    if normalized_value in TRUE_VALUES:
        return True
    if normalized_value in FALSE_VALUES:
        return False

    allowed_values = sorted(TRUE_VALUES | FALSE_VALUES)
    raise ValueError(
        f"Invalid boolean value for environment variable {name}: {value!r}. "
        f"Expected one of {allowed_values}."
    )
