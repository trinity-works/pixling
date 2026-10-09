"""Generate the starter style palettes from a few taste parameters.

Numbers follow hand-made pixel-art palettes: chroma mostly 0.03-0.09, OKLab L step ~0.08-0.10,
highlights rotate warm (+~30 deg over a ramp), warm shadows dip toward
purple, one shared near-black. Run: python3 tools/make_styles.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pp.color import make_ramp, rgb_to_hex  # noqa: E402


def ramp(h, c, n=4, lo=0.30, hi=0.80, shadow=315, light=90, shift=26, **kw):
    return [rgb_to_hex(x) for x in make_ramp(h, c, n, l_dark=lo, l_light=hi, shadow_hue=shadow,
                                             light_hue=light, hue_shift=shift, **kw)]


def mat(r, shades=None, **kw):
    d = {"ramp": r}
    if shades is not None:
        d["shades"] = shades
    d.update(kw)
    return d


def duskborne():
    ramps = {
        "ink": ["#090a14", "#151d28", "#202e37", "#394a50"],
        "bone": ramp(75, 0.045, 4, 0.52, 0.93, shadow=300, light=100, shift=22),
        "skin": ramp(45, 0.075, 4, 0.40, 0.82),
        "hide": ramp(200, 0.03, 4, 0.28, 0.66, shadow=285, light=110, shift=24),
        "fur": ramp(40, 0.06, 4, 0.30, 0.62, shadow=330),
        "cloth_red": ramp(22, 0.13, 4, 0.30, 0.62, shadow=340, shift=18),
        "cloth_blue": ramp(262, 0.07, 4, 0.22, 0.52, shadow=285, light=230, shift=14),
        "cloth_green": ramp(150, 0.055, 4, 0.26, 0.58, shadow=220, shift=24),
        "leather": ramp(48, 0.07, 4, 0.30, 0.62, shadow=330),
        "steel": ramp(235, 0.025, 4, 0.30, 0.78, shadow=275, light=120, shift=20),
        "gold": ramp(70, 0.12, 4, 0.52, 0.86, shadow=40, light=100, shift=18),
        "wood": ramp(55, 0.06, 4, 0.30, 0.58, shadow=340),
        "stone": ramp(250, 0.02, 4, 0.32, 0.70, shadow=290, light=90, shift=15),
        "glow_cyan": ["#1d6f8a", "#2fb4c8", "#6ff0f0", "#e4fffb"],
        "glow_pink": ["#7a1f5a", "#c23b8a", "#ff76c4", "#ffe0f2"],
        "glow_fire": ["#8a2a1a", "#e0602a", "#ffb640", "#fff2c0"],
        "leaf": ramp(135, 0.07, 4, 0.28, 0.66, shadow=200, light=100, shift=26),
        "bark": ramp(40, 0.045, 4, 0.22, 0.48, shadow=330),
        "ground": ramp(100, 0.035, 3, 0.26, 0.40, shadow=260),
        "rust": ramp(52, 0.11, 4, 0.30, 0.66, shadow=10, light=95, shift=24),
        "hex_pink": ["#3d0f3a", "#7a1f5a", "#c23b8a", "#ff76c4"],
        "hex_cyan": ["#0f3348", "#1d6f8a", "#2fb4c8", "#6ff0f0"],
        "fur_dark": ramp(265, 0.05, 4, 0.18, 0.50, shadow=290, light=220, shift=16),
    }
    materials = {
        "outline": mat("ink", [0]),
        "bone": mat("bone", [0, 1, 2, 3]),
        "skin": mat("skin", [0, 1, 2, 3]),
        "hide": mat("hide", [0, 1, 2, 3], detail={"kind": "hide"}),
        "fur": mat("fur", [0, 1, 2, 3], detail={"kind": "fur"}, edge={"kind": "fur", "amount": 0.4}),
        "cloth_red": mat("cloth_red", [0, 1, 2, 3], detail={"kind": "cloth"}),
        "cloth_blue": mat("cloth_blue", [0, 1, 2, 3], detail={"kind": "cloth"}),
        "cloth_green": mat("cloth_green", [0, 1, 2, 3], detail={"kind": "cloth"}),
        "leather": mat("leather", [0, 1, 2, 3]),
        "steel": mat("steel", [0, 1, 2, 3], detail={"kind": "plate"}),
        "gold": mat("gold", [0, 1, 2, 3]),
        "wood": mat("wood", [0, 1, 2, 3]),
        "stone": mat("stone", [0, 1, 2, 3], detail={"kind": "stone"}),
        "dark": mat("ink", [0, 1, 2, 3]),
        "eye_cyan": mat("glow_cyan", [1, 2], emissive=True, no_outline=True),
        "eye_red": mat("glow_fire", [1, 2], emissive=True, no_outline=True),
        "glow_pink": mat("glow_pink", [1, 2, 3], emissive=True, no_outline=True),
        "glow_cyan": mat("glow_cyan", [1, 2, 3], emissive=True, no_outline=True),
        "fire": mat("glow_fire", [1, 2, 3], emissive=True, no_outline=True),
        "pupil": mat("ink", [0], no_outline=True),
        "eye_pink": mat("glow_pink", [1, 2], emissive=True, no_outline=True),
        "rust": mat("rust", [0, 1, 2, 3]),
        "fur_dark": mat("fur_dark", [0, 1, 2, 3]),
        "leaf": mat("leaf", [0, 1, 2, 3], bias=-0.1, sky=0.35, sky_obj=0.3, detail={"kind": "leaf"},
                    edge={"kind": "leaf", "amount": 0.45}),
        "bark": mat("bark", [0, 1, 2, 3], detail={"kind": "bark"}),
    }
    return {
        "name": "duskborne",
        "about": "Dark-fantasy action style: deep desaturated bodies, 3-4 tone ramps, one glowing accent "
                 "per character, near-black ink edges, light from the upper left.",
        "light": [-0.55, -0.42, 0.72],
        "thresholds": [0.50, 0.80, 0.94],
        "outline": {"mode": "self", "dark_below": -0.3, "rim_above": 0.62},
        "inner_line_depth": 2.5,
        "bg": "#262b36",
        "flash": "#ebede9",
        "shadow_color": "#12161f",
        "dust": "#a8b5b2",
        "vfx_ramps": {"cyan": "glow_cyan", "pink": "glow_pink", "fire": "glow_fire", "white": "bone"},
        "scale": {"tile": 16, "hero_h": 30, "grunt_h": [22, 34], "boss_h": [48, 72], "tree_h": [48, 96]},
        # how the family moves: heavy, bent-forward lurch; long trembling wind-ups that land hard
        "motion": {"gait": "lurch", "attack_style": "heavy", "hitstop": 2},
        "ramps": ramps,
        "materials": materials,
    }


def sunmeadow():
    ramps = {
        "ink": ["#2a1b2d", "#3f2a3e", "#5a3d4f"],
        "skin": ramp(50, 0.075, 4, 0.52, 0.90, shadow=10),
        "fur_tan": ramp(62, 0.085, 4, 0.50, 0.88, shadow=20),
        "fur_brown": ramp(45, 0.07, 4, 0.36, 0.70, shadow=350),
        "fur_white": ramp(85, 0.02, 4, 0.72, 0.97, shadow=280, light=95, shift=14),
        "fur_grey": ramp(250, 0.02, 4, 0.48, 0.84, shadow=290, light=90, shift=10),
        "fur_orange": ramp(45, 0.155, 4, 0.47, 0.84, shadow=15, light=85, shift=20),
        "cloth_red": ramp(25, 0.13, 4, 0.42, 0.74, shadow=350, shift=20),
        "cloth_blue": ramp(245, 0.09, 4, 0.40, 0.76, shadow=280, light=200, shift=18),
        "cloth_green": ramp(140, 0.09, 4, 0.44, 0.80, shadow=190, light=110, shift=22),
        "cloth_yellow": ramp(92, 0.12, 4, 0.62, 0.93, shadow=50, light=105, shift=18),
        "leather": ramp(55, 0.08, 4, 0.40, 0.72, shadow=15),
        "wood": ramp(60, 0.075, 4, 0.38, 0.70, shadow=10),
        "steel": ramp(230, 0.025, 4, 0.52, 0.92, shadow=270, light=110, shift=18),
        "gold": ramp(80, 0.13, 4, 0.60, 0.92, shadow=45, light=105, shift=18),
        "leaf": ramp(142, 0.13, 5, 0.33, 0.76, shadow=195, light=112, shift=30, chroma_light=1.0, chroma_dark=0.85),
        "leaf_autumn": ramp(52, 0.15, 5, 0.40, 0.82, shadow=20, light=80, shift=22, chroma_light=1.0, chroma_dark=0.85),
        "bark": ramp(45, 0.06, 4, 0.32, 0.60, shadow=330),
        "stone": ramp(260, 0.025, 4, 0.46, 0.86, shadow=290, light=90, shift=16),
        "pink": ramp(0, 0.10, 4, 0.58, 0.90, shadow=330, light=40, shift=14),
        # orc warrior: olive skin
        "skin_orc": ramp(108, 0.105, 4, 0.40, 0.80, shadow=150, light=100, shift=18),
        "glow_fire": ["#b8412a", "#f07a32", "#ffc14a", "#fff4c8"],
        "glow_cyan": ["#2a7fa8", "#48c0dc", "#98f0f0", "#f0fffc"],
        "glow_leaf": ["#3f8f3a", "#a6e04a", "#f0f58a", "#fffce6"],
        "eye": ["#2a1b2d", "#fff6e8"],
        "ground": ramp(135, 0.085, 3, 0.50, 0.62, shadow=170, light=110, shift=12),
    }
    materials = {k: mat(k, [0, 1, 2, 3]) for k in ramps if k not in ("ink", "eye", "ground")}
    # detail materials: fur/cloth/bark/stone texture painted in part space; fur edges get tufts
    for k in materials:
        if k.startswith("fur_"):
            materials[k]["detail"] = {"kind": "fur", "amount": 0.8}
            materials[k]["edge"] = {"kind": "fur", "amount": 0.3}
        elif k.startswith("cloth_"):
            materials[k]["detail"] = {"kind": "cloth"}
    materials["bark"]["detail"] = {"kind": "bark"}
    materials["stone"]["detail"] = {"kind": "stone"}
    materials.update({
        "leaf": mat("leaf", [0, 1, 2, 3, 4], thresholds=[0.46, 0.66, 0.86, 0.985], sky=0.3, sky_obj=0.22,
                    detail={"kind": "leaf"}, edge={"kind": "leaf", "amount": 0.45}),
        "leaf_autumn": mat("leaf_autumn", [0, 1, 2, 3, 4], thresholds=[0.46, 0.66, 0.86, 0.985], sky=0.3,
                           sky_obj=0.22, detail={"kind": "leaf"}, edge={"kind": "leaf", "amount": 0.45}),
        "pupil": mat("eye", [0], no_outline=True),
        "eye_white": mat("eye", [1], no_outline=True),
        "nose": mat("ink", [0, 1], no_outline=True),
        "fire": mat("glow_fire", [1, 2, 3], emissive=True, no_outline=True),
        "glow_cyan": mat("glow_cyan", [1, 2, 3], emissive=True, no_outline=True),
        "glow_leaf": mat("glow_leaf", [1, 2, 3], emissive=True, no_outline=True),
        "dark": mat("ink", [0, 1, 2]),
    })
    for k in ("glow_fire", "glow_cyan", "glow_leaf"):
        materials.pop(k, None)
    return {
        "name": "sunmeadow",
        "about": "Bright cozy-adventure style: warm saturated mids, soft value range, colored (never black) "
                 "outlines from each material's own darkest shade, light from the upper left.",
        "light": [-0.55, -0.42, 0.72],
        "thresholds": [0.48, 0.78, 0.93],
        "outline": {"mode": "self", "dark_below": -0.3, "rim_above": 0.62},
        "inner_line_depth": 2.5,
        "bg": "#8fb56a",
        "flash": "#fffbe8",
        "shadow_color": "#44703f",
        "dust": "#e2dcc0",
        "vfx_ramps": {"fire": "glow_fire", "cyan": "glow_cyan", "leaf": "glow_leaf", "white": "fur_white"},
        "scale": {"tile": 16, "hero_h": 30, "critter_h": [8, 16], "animal_h": [14, 30], "tree_h": [40, 96]},
        # how the family moves: springy steps that squash on every footfall; hop-in attacks
        "motion": {"gait": "bounce", "attack_style": "hop", "hitstop": 1},
        "ramps": ramps,
        "materials": materials,
    }


def vermilion():
    """Folk-print spirit look: three inks (warm black, vermilion, bone white) on cream paper, 1-2 flat tones,
    black masses carry the silhouette, red carries the markings. No outer line."""
    ramps = {
        "ink": ["#1c1719", "#2a2326", "#3a3034"],
        "red": ["#7e2419", "#b8331f", "#dc4a2c", "#ef7a52"],
        "bone": ["#a89a84", "#cbbfa9", "#f6f0e4"],
        "paper": ["#cdbf9f", "#ddd0b0", "#e9dfc4"],
        "eye": ["#1c1719", "#f3ecdd"],
        "ground": ["#dccfae", "#e4d8ba", "#ebe1c7"],
        "glow_red": ["#7e2419", "#dc4a2c", "#ff9a64", "#fff0d8"],
        "glow_bone": ["#8d8270", "#ddd3c0", "#f3ecdd", "#fffaf0"],
        # on paper the hot core is the darkest ink, not the lightest: VFX ramps run red -> black
        "fx_ink": ["#ef7a52", "#dc4a2c", "#7e2419", "#1c1719"],
        "dust": ["#a89a84", "#bdb09a", "#cdbf9f"],
    }
    flat = [0.5, 0.9]
    materials = {
        "ink": mat("ink", [0, 1], thresholds=[0.72], sky=0.25),        # heads, limbs: near-flat black mass
        "ink_flat": mat("ink", [0], no_outline=True),                   # stick legs, antlers: one ink
        "red": mat("red", [1, 2], thresholds=[0.42], sky=0.2),          # coats, bodies
        "red_dark": mat("red", [0, 1], thresholds=[0.5]),               # undersides, inner feathers
        "red_mark": mat("red", [2], no_outline=True),                   # painted marks on black: one flat red
        "canopy": mat("red", [0, 1, 2], thresholds=[0.36, 0.62], sky=0.35,
                      edge={"kind": "leaf", "amount": 0.4}),              # tree crowns: dark underside, clumps
        "fur": mat("bone", [1, 2], thresholds=[0.46], sky=0.3,
                   edge={"kind": "fur", "amount": 0.7}),                # dry-brush collars: broken edge
        "bone": mat("bone", [1, 2], thresholds=[0.5]),                  # teeth, horns, trims
        "bone_mark": mat("bone", [2], no_outline=True),                 # white marks / stripes
        "eye": mat("eye", [1], no_outline=True),
        "pupil": mat("eye", [0], no_outline=True),
        "ember": mat("glow_red", [1, 2, 3], emissive=True, no_outline=True),
    }
    return {
        "name": "vermilion",
        "about": "Folk-print spirit style: three inks (warm black, vermilion, bone white) on cream paper. "
                 "Black masses carry the silhouette, red carries the markings, 1-2 flat tones, no outline.",
        "light": [-0.55, -0.42, 0.72],
        "thresholds": flat,
        "outline": {"mode": "self", "dark_below": -0.6, "rim_above": 2.0},
        "inner_line_depth": 1.8,
        "contact_shadow": 1,
        "bg": "#e9dfc4",
        "flash": "#fff6e6",
        "shadow_color": "#cdbf9f",
        "dust": "#a89a84",
        "vfx_ramps": {"red": "fx_ink", "bone": "glow_bone"},
        "scale": {"tile": 16, "hero_h": 34},
        # how the family moves: spirits float off the ground, hop to travel, dart in and drift back
        "motion": {"gait": "hop", "idle_style": "float", "hover": 2, "float_bob": 2, "attack_style": "dart"},
        "ramps": ramps,
        "materials": materials,
    }


def vista():
    """Aerial town-map look (hub screens, world maps): muted painterly palette, cream walls with cool blue-grey
    shadow sides, terracotta roofs, teal sea, dark forest with ochre clumps. Big calm value masses: almost no
    edge darkening, no rim light, 3 bands per material."""
    ramps = {
        "ink": ["#1a2227", "#2b353a", "#3b464a"],
        "plaster": ["#5b6173", "#878c99", "#bdbcb3", "#e2ddcc"],
        "roof": ["#5c2f2b", "#874633", "#ad6340", "#cc8654"],
        "roof_plum": ["#46303a", "#654146", "#855a52", "#a4775f"],
        "stone": ["#4a5160", "#6b7281", "#9599a2", "#c2c1b9"],
        "wood": ["#3e2f2d", "#5e4537", "#81634b", "#a2855f"],
        "leaf": ["#1c3533", "#2b4d42", "#44684b", "#708a56", "#9ea769"],
        "leaf_gold": ["#654723", "#946a2a", "#c3962f", "#e2c05a"],
        "grass": ["#46573d", "#5f7049", "#7f8a5a", "#a2a376"],
        "sand": ["#6b6753", "#8f896b", "#b2aa86", "#d2c8a0"],
        "rock": ["#353d43", "#4f585b", "#6c7470", "#8e9486"],
        "sea": ["#163844", "#1d4c5a", "#2a6570", "#468580", "#86b09c", "#d4ddbf"],
        "banner": ["#57212e", "#852f37", "#b1473d", "#d26e58"],
        "gold": ["#80622a", "#b8933f", "#e0c878"],
        "glow_fire": ["#8a4a2a", "#e0a050", "#f5d890"],
        "glow_arcane": ["#2f5f6a", "#5fb3ad", "#b8ecd8", "#effff4"],     # portals, dungeon wards, realm gates
        "mist": ["#b3b6b3", "#c9c9c1", "#d6d3c7", "#e2ddcc"],            # fog of war: close, soft whites
        "eye": ["#1a2227", "#e2ddcc"],
        "ground": ["#5f7049", "#7f8a5a", "#a2a376"],
    }
    materials = {k: mat(k, list(range(len(v)))) for k, v in ramps.items() if k not in ("ink", "eye", "ground", "glow_fire", "glow_arcane", "mist")}
    materials.update({
        "plaster": mat("plaster", [0, 1, 2, 3], thresholds=[0.35, 0.62, 0.86]),
        "roof": mat("roof", [0, 1, 2, 3], thresholds=[0.35, 0.6, 0.86], sky=0.25),
        "roof_plum": mat("roof_plum", [0, 1, 2, 3], thresholds=[0.35, 0.6, 0.86], sky=0.25),
        "window": mat("ink", [1, 2], no_outline=True),
        "glass": mat("glow_fire", [1, 2], emissive=True, no_outline=True),
        "arcane": mat("glow_arcane", [1, 2, 3], emissive=True, no_outline=True),
        "torch": mat("glow_fire", [0, 1, 2], emissive=True, no_outline=True),
        "dark": mat("ink", [0, 1, 2]),
    })
    return {
        "name": "vista",
        "about": "Aerial town-map style: muted painterly palette, cream walls with cool blue-grey shade, terracotta "
                 "roofs, teal sea, dark forest with ochre clumps. Calm value masses, no rim light, few edge lines.",
        "light": [-0.55, -0.42, 0.72],
        "thresholds": [0.4, 0.7, 0.9],
        "outline": {"mode": "self", "dark_below": -0.85, "rim_above": 5.0},
        "inner_line_depth": 3.0,
        "contact_shadow": 1,
        "bg": "#2a6570",
        "flash": "#f4efdc",
        "shadow_color": "#2b3a36",
        "dust": "#b2aa86",
        "vfx_ramps": {"fire": "glow_fire", "white": "plaster"},
        "scale": {"tile": 8},
        "motion": {},
        "ramps": ramps,
        "materials": materials,
    }


# ------------------------------------------------------------------ exact-iso styles (pp/iso.py)
# These are read by their kits (tools/tactics, tools/flat), not by the SDF forge: palettes and light only. The kits
# bind every material to a ramp and a tone per face class (top / lit / shade), so a style owns its colours and the
# kit owns its shapes.

def tactics(biome="valley"):
    """Crisp Tactics: authored isometric. Exact 2:1 iso, three flat face tones, a soft selout line (ink on the
    shadow side, the form's own dark on the lit side, corner AA), cube canopies and slab stone with masonry, a
    restricted sage / pink-stone / cream palette and one orange accent. Biomes: valley, autumn."""
    common = {
        "ink": ["#0c131a", "#15242e", "#24363f"],
        "stone": ["#996362", "#cea499", "#f3ecca"],
        "stone_b": ["#7d5f60", "#b5938f", "#e2d2b8"],
        "wood": ["#4a3e2c", "#867257", "#a99e80"],
        "trunk": ["#3a3a24", "#5b5a38", "#7b774d"],
        "water": ["#0d3a40", "#16525a", "#23707a", "#3a8a8e", "#6aaea6"],
        "path": ["#a99e80", "#cfc6a0", "#e2dcb4", "#ece3ba"],
        "accent": ["#a8502a", "#e17f41", "#f2a868"],
        "cloth": ["#a99e80", "#e8e2c4", "#f6f1dc"],
        "roof": ["#14494f", "#2f6e68", "#4f8f82"],
        "pane": ["#24363f"],
        "glow_fire": ["#a8502a", "#e17f41", "#f6d890"],
        "fur_brown": ["#3a2a22", "#5a4030", "#7a5a40"],
        "fur_grey": ["#4a5a5a", "#7a8a86", "#a3b0a4"],
        "fur_tan": ["#8a4422", "#c2602a", "#e48c4c"],
        "fur_orange": ["#7a3a1e", "#c2602a", "#e48c4c"],
        "fur_white": ["#a3a686", "#e4dfc0", "#f6f1dc"],
        "fur_dark": ["#2a2422", "#3a2a22", "#5a4030"],
        "wool": ["#a3a686", "#e4dfc0", "#f6f1dc"],
        "goods": ["#7b3a2a", "#c2602a", "#e9c46a"],
    }
    if biome == "valley":
        world = {"grass": ["#104a50", "#8aa67e", "#9cb48c", "#aebf98"],
                 "leaf": ["#14494f", "#6f9070", "#93b089"],
                 "leaf_b": ["#4f4a2a", "#7b774d", "#a39a58"],
                 "moss": ["#3f6a4a", "#6f9070"]}
        owner = "market awnings and sail trim"
    else:
        world = {"grass": ["#3d4a2c", "#a39a58", "#b5aa66", "#c4b878"],
                 "leaf": ["#6a2e22", "#b0582e", "#d98a46"],
                 "leaf_b": ["#5a4a1e", "#a8842e", "#d6b24a"],
                 "moss": ["#5a5a2a", "#8a8440"]}
        owner = "sails and mill blades (the orange canopies would compete with awnings)"
    # awnings take the accent in the valley; in autumn they turn teal so the accent keeps one owner
    ramps = {**common, **world, "plaster": common["cloth"],
             "awn": common["accent"] if biome == "valley" else common["roof"]}
    return {
        "name": "tactics" if biome == "valley" else "tactics_" + biome,
        "about": "Crisp Tactics (%s): authored isometric. Three flat face tones, a soft selout line, cube canopies "
                 "and slab stone with masonry, sage / pink stone / cream, one orange accent." % biome,
        "family": "tactics", "biome": biome, "camera": "iso_exact",
        "light": [-1.0, 0.22, 0.95],
        "accent": {"ramp": "accent", "owner": owner},
        "ramps": ramps,
    }


def flat(biome="forest"):
    """Flat Minimal: restraint. Two world hues (a dark sea of one hue, a lighter land of the same), one warm window
    accent, chunky pixels (a small map shown big), flat faces, flat long shadows, two or three tones per material.
    Biomes: forest (teal), dunes (ochre on deep blue)."""
    if biome == "forest":
        world = {"bg": ["#0f3a3d", "#134446", "#18504f"], "land": ["#2c8a7b", "#36a08e", "#4ab29c"],
                 "tree": ["#0c2a2e", "#163b40", "#235650"], "wall": ["#5a2a25", "#7e3f33"],
                 "roof": ["#3c7f8c", "#69b3b0", "#a6e0d0"], "cliff": ["#123a3c", "#1a4a4a"],
                 "path": ["#2a8a7c", "#4aa592", "#6cbba3"], "stone": ["#2a5a5e", "#4a8a88"],
                 "trunk": ["#5a2a25", "#7e3f33"]}
    else:
        world = {"bg": ["#1b2a4a", "#22365c", "#2b456e"], "land": ["#b06a36", "#c98444", "#dca15a"],
                 "tree": ["#3d4a2a", "#55633a", "#6f7e48"], "wall": ["#dcae6e", "#f2d29a"],
                 "roof": ["#7a3a26", "#94482c", "#ad5a34"], "trunk": ["#4a2c1c", "#6a4028"],
                 "cliff": ["#6a3a24", "#8a4e2e"], "path": ["#c98444", "#dca15a", "#ecc37c"],
                 "stone": ["#7a4e34", "#9e6a48"]}
    animals = {"fur_brown": ["#5a2e22", "#7e4630"], "fur_tan": ["#7e4630", "#a0623e"],
               "fur_white": ["#9fd8c8", "#d8f2e6"]}
    ramps = {"ink": ["#0b1d22", "#123036"], "glow_fire": ["#c27a1e", "#f2c544", "#fbe58a"], **world, **animals}
    return {
        "name": "flat" if biome == "forest" else "flat_" + biome,
        "about": "Flat Minimal (%s): two world hues, one warm window accent, chunky pixels, flat faces and flat "
                 "long shadows, two or three tones per material." % biome,
        "family": "flat", "biome": biome, "camera": "iso_exact",
        "light": [0, -1, 1],
        "accent": {"ramp": "glow_fire", "owner": "windows"},
        "night": {"ramp": ["#04141a", "#082228", "#0e3238", "#16474a", "#24605c"], "glow": ["#a8602a", "#f2c544", "#fbe58a"]},
        "ramps": ramps,
    }


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "styles"
    out.mkdir(exist_ok=True)
    for s in (duskborne(), sunmeadow(), vermilion(), vista(), tactics(), tactics("autumn"), flat(), flat("dunes")):
        (out / (s["name"] + ".json")).write_text(json.dumps(s, indent=1))
        print("wrote", s["name"], sum(len(r) for r in s["ramps"].values()), "colors")
