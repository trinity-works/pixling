"""Write style/world JSON readably: objects indented, short lists (ramps, stops, vectors) on one line."""
from __future__ import annotations

import json


def dumps(obj, indent=0, width=118) -> str:
    one = json.dumps(obj)
    if len(one) + indent <= width or not isinstance(obj, (dict, list)):
        return one
    pad = " " * (indent + 2)
    if isinstance(obj, dict):
        items = ["%s%s: %s" % (pad, json.dumps(k), dumps(v, indent + 2, width)) for k, v in obj.items()]
        return "{\n" + ",\n".join(items) + "\n" + " " * indent + "}"
    items = ["%s%s" % (pad, dumps(v, indent + 2, width)) for v in obj]
    return "[\n" + ",\n".join(items) + "\n" + " " * indent + "]"


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        with open(p) as f:
            d = json.load(f)
        with open(p, "w") as f:
            f.write(dumps(d) + "\n")
