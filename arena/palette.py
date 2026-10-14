"""The active map's palette (arena/maps/<name>/palette.py): PAL, UNIT_HUES, SUN_HUES, looked up when used."""


def rgb(h: str):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))


def __getattr__(name):
    from .maps import active
    return getattr(active().palette, name)
