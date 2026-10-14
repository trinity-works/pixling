"""The active map's place (arena/maps/<name>/place.py): `from arena import place as P; P.terrain(...)` reads the map
that arena.maps.activate() chose (Hushfall Crossing by default). Every attribute is looked up when it is used."""


def __getattr__(name):
    from .maps import active
    return getattr(active().place, name)
