"""The arena's palette: Hushfall's dusk (fp/draw2d.PAL) made into a map that units are added to later.

Zones (arena/zones.py) derive their hazed, value-clamped variants of these colours; every pixel of the map is one
of these keys as its zone renders it.

The value structure, light to dark:
- SKY: a warm dusk, cool grey-teal at the top, rose and peach down to the glow on the horizon (First Snow's sky).
- VISTA: the cumulus. Slate-violet bases, salmon faces, peach crowns, and the low sun's hot pink on the crowns that
  face it. The only saturated colour on the map outside its lights.
- PLAYFIELD: the lightest large area, calm, two tones: First Snow's light teal snow and blue-violet shade, the
  trodden lanes a step between them. Low chroma, so units of any strong hue pop on it.
- BACKDROP: the forests past the drop, the same spruces pushed into the violet-rose dusk haze (`fog`).
- FRAME: the darkest: navy spruces with snow shelves, the ruin's masonry, the palisades, the cliff's top.

The sun owns the pinks, peaches and salmons (hue 300-30 degrees): the sky's glow, the cloud crowns, the rims on the
tree line, the warm lamps. The map keeps every other hue at low chroma, and leaves three hue bands free for the units
the user adds (UNIT_HUES). Objectives and lights may be the brightest things on the map; nothing else is saturated.
"""
from __future__ import annotations

PAL = {
    # the dusk sky, zenith -> horizon, and the haze between the clouds
    "sky_top": "#7d8a90", "sky_hi": "#8f9392", "sky_mid": "#a39590", "sky_lo": "#b3968f", "glow": "#c69a92",
    "glow_lo": "#a18d90", "haze_hi": "#95938f", "haze": "#839a8c", "haze_lo": "#7a8c96", "mist": "#6f8590",
    "mist_lo": "#5b6a80",
    # the haze every zone behind the playfield is pushed toward: violet-rose dusk
    "fog": "#958f9f",
    # cumulus: slate-violet base, a face one step lighter, salmon lit, peach crown; the sun's hot pink on the crowns
    "cl_base": "#6f6a86", "cl_shade": "#887a8e", "cl_mid": "#a48888", "cl_lit": "#c2928e", "cl_hi": "#d4a296",
    "cl_crown": "#e4b6a4", "hot": "#fc5084", "hot2": "#e46088", "hot_deep": "#ac567e",
    "fl_base": "#68708e", "fl_lo": "#7c839a", "fl": "#9898a9", "fl_hi": "#b8a3a5",
    # the playfield: First Snow's light teal snow and blue-violet shade, the trodden lanes between
    "pf_lit": "#8aa5aa", "pf_shade": "#63748f", "pf_lane": "#7b949c", "pf_lane_sh": "#607089",
    # snow outside the field (drifts, pillows, roofs, the frame's ground, the far slopes): the field's family, from
    # deep violet shade up to the sun's warm glance
    "sn_deep": "#474d6c", "sn_shade": "#555b7a", "sn_mid": "#636987", "sn": "#777a90", "sn_hi": "#8b8c98",
    "sn_lit": "#9e9c9b", "sn_warm": "#aca79f", "sn_glow": "#b7b1a6", "sn_cap": "#c2bcaf",
    # spruces: body, snow shelf, sun-side snow, the shaded underside (two families for variety), the trunk; the low
    # sun's rim on the tree line
    "ta0": "#232843", "ta1": "#3f4c68", "ta2": "#4c5d79", "ta3": "#5c7286", "tau": "#1c2036",
    "tb0": "#2a324e", "tb1": "#45546f", "tb2": "#52637d", "tb3": "#62788a", "tbu": "#242a44", "trunk": "#202640",
    "rim": "#a07c8a", "rim_hot": "#c0928f",
    # stone, the ruin's masonry (a step warmer and lighter than the cliff), cliff
    "st_dk": "#1c2440", "st_lo": "#30365a", "st": "#41516c", "st_lit": "#4c5878", "st_hi": "#5b6a80",
    "ms_dk": "#353a58", "ms": "#4a5070", "ms_lit": "#5f6680", "ms_hi": "#777c90",
    "cl_rock_dk": "#2c3150", "cl_rock": "#383e60", "cl_rock_lit": "#474e70",
    # timber (violet-brown under the dusk), the planks' sunlit face, bark, rope, iron, dry grass, ash
    "wd_dk": "#2b2a44", "wd": "#403e5c", "wd_lit": "#58546e", "pl_hi": "#706678",
    "bark_dk": "#1c1830", "bark": "#283050", "bark_lit": "#3c4060", "rope": "#615d71",
    "metal_dk": "#141a30", "metal": "#30365a", "metal_lit": "#4c5878", "grass": "#4e5b79", "ash": "#30365a",
    # the two camps' canvas: west a warm plum-grey, east a slate blue; both low chroma (the units bring the colour)
    "cw_lo": "#2c2840", "cw": "#3e3652", "cw_mid": "#504663", "cw_lit": "#625875",
    "ce_lo": "#222c44", "ce": "#2f3c56", "ce_mid": "#3d4c66", "ce_lit": "#4d5d76",
    # banner cloth: cream, a colour slot for whoever holds the camp
    "cloth_dk": "#7d7a8a", "cloth": "#a9a6a6", "cloth_lit": "#c9c2b4",
    # warm light: lamps, the camps' hearts, fires (the sun's family)
    "lamp": "#e4b6a4", "lamp_core": "#f4dcc8", "fire": "#e98a76",
    # snowfall, ink for the UI
    "fur": "#a8b4ac", "fur_dk": "#7f9496", "ink": "#141a30", "ink2": "#1c2440",
}

# hue bands (degrees) kept free for the units: the map shows none of them above chroma 0.2 (zones.lint checks it)
UNIT_HUES = {"gold": (35, 70), "green": (80, 165), "azure": (190, 230)}
# the sun's family: allowed saturated only in the sky, the vista (cloud crowns), lights and objectives
SUN_HUES = (300, 30)


def rgb(h: str):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))
