ENABLED_BOOL_VALUES = ['enabled', 'enable', 'true', 'yes', 'on', '1']
DISABLED_BOOL_VALUES = ['disabled', 'disable', 'false', 'no', 'off', '0']
ALL_BOOL_VALUES = ENABLED_BOOL_VALUES + DISABLED_BOOL_VALUES

def is_true(value: str) -> bool:
    return value.lower() in ENABLED_BOOL_VALUES
