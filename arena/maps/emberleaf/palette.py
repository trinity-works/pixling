"""Emberleaf Hollow's palette: a clearing in an autumn-red forest at midday. Closed and hand-picked, every key a
ramp step (paint.py RAMPS); zones (arena/zones.py) derive their hazed, clamped variants.

The value structure, light to dark (arena/STYLE.md):
- PLAYFIELD: the fighting ground is the light warm band (dirt 0.48-0.55, flat cobbles 0.58-0.66); the grass is the
  mid tone (teal shade 0.36, emerald body 0.46, lime lights 0.58) and saturated but calm: two steps per material, the
  variety is in big soft patches, not noise.
- FRAME: darker and saturated: coral-red crowns (plum undersides 0.25, coral 0.47, peach-pink tops 0.62), deep teal
  pines (0.20-0.42), slate boulders, the forest floor in teal shade.
- BACKDROP / VISTA: the valley's canopy and the far hills pushed into a cool blue-green haze (`fog`); the sky a soft
  midday blue, pale and warm at the horizon.

The embers own the coral and pink (hue 335-15 degrees, SUN_HUES): the crowns, the flowers, the waystones' glow. They
may be saturated in the frame and the back, never on the fighting ground.

Kept free for the units (UNIT_HUES): gold (40-64 degrees) and violet (240-290). No pixel of the map shows either above
chroma 0.2. This map is green grass under red trees round a cyan pond, so Hushfall's green and azure bands are not
free here: each map reserves its own bands (arena/STYLE.md "units"), and every unit also carries the shared dark
outline and light rim, which hold on any ground.
"""
from __future__ import annotations

PAL = {
    # the sky: soft midday blue at the top, pale and warm at the horizon over the hills
    "sk_top": "#6fa7c4", "sk_hi": "#88b6c9", "sk_mid": "#a6c6cc", "sk_lo": "#c4d6cc", "glow": "#efe6cc",
    # the haze everything behind the plateau is pushed toward
    "fog": "#a6c0bd",
    # fair-weather cumulus: lilac-grey base, cream faces, warm white crowns
    "cl_base": "#9ea3bf", "cl_shade": "#b3b5cc", "cl_mid": "#cfcdd3", "cl_lit": "#e6dfd6", "cl_hi": "#f3e8da",
    # far hills (vista): blue-green ranges
    "hl_sh": "#6f909c", "hl": "#86a3a8", "hl_lit": "#9db6b0",
    # grass, shade -> lime (the playfield's mid tone), and its patches
    "gr_deep": "#2f5048", "gr_teal": "#3a6a5c", "gr_sh": "#436d55", "gr": "#5f9156", "gr_lit": "#6fa34f", "gr_hi": "#8fbb4e",
    # the forest floor (frame): the grass in the trees' shade
    "ff_dk": "#22403f", "ff": "#2b4c44", "ff_lit": "#385d4b",
    # dirt and cobbles: the fighting ground (the lightest large area)
    "dt_sh": "#6e5552", "dt_pk": "#88695a", "dt": "#9c7c65", "dt_lit": "#bd9570", "dt_du": "#c8a37f", "cb_sh": "#7e6253", "cb": "#bc9f84", "cb_hi": "#c8ad91",
    "cb_top": "#d3bb9e",
    # coral crowns: plum undersides -> coral -> peach-pink tops; and the ember variety, redder
    "cr_deep": "#432740", "cr_under": "#553048", "cr_mag": "#a8456a", "ce_mag": "#9c3f5c",
    "cr_sh": "#853b5b", "cr": "#c25563", "cr_lit": "#de6869",
    "cr_hi": "#f29a80",
    "ce_under": "#4c2a42", "ce_sh": "#7e364d", "ce": "#b84b55", "ce_lit": "#d25d58", "ce_hi": "#e57f6c",
    # pines: deep teal
    "pn_deep": "#152629", "pn_sh": "#1c3536", "pn": "#24443f", "pn_lit": "#2c524a", "pn_hi": "#3c6858",
    # bushes: green, and a red one under the crowns
    "bu_sh": "#2b4c41", "bu": "#3b664a", "bu_lit": "#4f7f52",
    # slate boulders, warm-grey tops; the ruin's stone, a step warmer; moss
    "rk_deep": "#2b2a38", "rk_sh": "#3f3b4c", "rk": "#565663", "rk_lit": "#78716f", "rk_hi": "#958a82",
    "rs_sh": "#4a4b52", "rs": "#67656a", "rs_lit": "#85807d", "moss": "#58784e",
    # the plateau's cliffs and the valley floor
    "cf_dk": "#363846", "cf": "#4d4f5c", "cf_lit": "#66666f",
    "vf": "#4d7457", "vf_lit": "#5f8a5e",
    # wood: bark, logs and stumps, the cut ends' rings
    "wd_dk": "#3a2a2e", "wd": "#583e37", "wd_lit": "#755443", "wd_end": "#a7845f", "wd_ring": "#8c6a4c",
    # water: deep -> cyan, the shimmer, the wet bank
    "wa_deep": "#123f68", "wa_mid": "#17507f", "wa": "#1a6493", "wa_lit": "#2584b5", "wa_sh": "#3aa2c6", "wa_hi": "#9ad8e6", "shore": "#3c5552",
    "lily": "#4f8a4a", "lily_lit": "#76a957",
    "rv": "#7cb5c4", "rv_hi": "#b3d8dc",
    # small things: flowers (pink, orange, white), mushrooms, reeds
    "fl_pink": "#f0a0ae", "fl_orange": "#ee9459", "fl_white": "#eceed8", "fl_lilac": "#d690d8", "mu_cap": "#cc4840", "mu_dot": "#f2e4d6",
    "reed": "#5e8a4c", "reed_lit": "#86a85a",
    # the waystones' rune and the lanterns: warm light
    "lamp": "#ffd4a0", "lamp_core": "#fff1d6", "fire": "#f28a52", "rune": "#ff9a8a",
    # banner cloth / the people of the scale sheet, ink for the UI, the motes and petals of the viewer
    "cloth_dk": "#8a8478", "cloth": "#b9b2a2", "cloth_lit": "#ddd5c2",
    "ink": "#141a30", "ink2": "#1c2440", "smoke": "#d6dcd2", "smoke_lo": "#aab8b0",
}

# hue bands (degrees) kept free for the units: no pixel of the map shows them above chroma 0.2 (zones.lint)
UNIT_HUES = {"gold": (40, 64), "violet": (240, 290)}
# the embers' family: coral and pink, saturated only in the frame, the back and the focus (see biome.SUN_SHARE)
SUN_HUES = (335, 15)


def rgb(h: str):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))
