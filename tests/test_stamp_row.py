"""stamp_row: a row of windows laid out on the wall as drawn. Run: python3 -m unittest tests.test_stamp_row"""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pp.forge import Forge, load_style  # noqa: E402


def house(rows):
    parts = [{"shape": "box", "at": [0, 0, 6], "half": [10, 5, 6], "mat": "plaster"}] + rows
    return {"name": "t_row", "style": "vista", "rig": "prop", "directions": ["S"], "frame": [48, 40], "anchor": [24, 34],
            "view": {"yaw": {"S": -24}}, "clips": ["idle"], "custom_clips": {"idle": {"loop": True, "frames": [{"pose": {}}]}},
            "bones": [{"name": "root"}, {"name": "walls", "parent": "root", "parts": parts}]}


def row(z, count, normal=(0, -1, 0), rows=("a",)):
    return {"shape": "stamp_row", "normal": list(normal), "at": [0, 0, z], "count": count, "rows": list(rows),
            "key": {"a": "window"}, "min_facing": 0.05}


def window_px(spec):
    f = Forge(spec)
    img = f.frame(f.clips()[0].frames[0], "S")
    style = load_style("vista")
    cols = [np.array(c, np.uint8) for c in style.mat_colors("window")]
    win = np.zeros(img.shape[:2], bool)
    for c in cols:
        win |= np.all(img[..., :3] == c, axis=-1)
    return win, f._buf, f.model.order.index("walls")


class StampRow(unittest.TestCase):
    def test_even_pitch_and_parallel_to_the_bottom_edge(self):
        win, buf, bi = window_px(house([row(3, 5)]))
        ys, xs = np.nonzero(win)
        self.assertGreaterEqual(len(xs), 3)
        gaps = np.diff(np.sort(xs))
        self.assertEqual(len(set(gaps.tolist())), 1)                 # one whole-pixel pitch
        walls = buf.bone == bi
        for y, x in zip(ys, xs):                                      # each sits 3 px above its own column's bottom
            self.assertEqual(int(np.nonzero(walls[:, x])[0].max()) - y, 3)

    def test_drops_windows_rather_than_crowding(self):
        win, _, _ = window_px(house([row(3, 12)]))
        xs = np.sort(np.nonzero(win)[1])
        self.assertTrue((np.diff(xs) >= 3).all())

    def test_keeps_clear_of_an_earlier_row(self):
        alone, _, _ = window_px(house([row(3, 5)]))
        with_door, _, _ = window_px(house([row(1, 1, rows=("a", "a")), row(3, 5)]))
        door_x = int(np.nonzero(with_door & ~alone)[1].mean()) if (with_door & ~alone).any() else None
        self.assertIsNotNone(door_x)
        ys, xs = np.nonzero(with_door)
        near = [x for x in xs if abs(x - door_x) <= 1]
        self.assertEqual(len(near), 2)                                # only the door's own two pixels near it


if __name__ == "__main__":
    unittest.main()
