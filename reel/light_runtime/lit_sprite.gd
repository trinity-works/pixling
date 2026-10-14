class_name LitSprite
extends Node2D
## Player for "pixling.lit-sprite" sheets (reel light build / reel light export --engine godot), Godot 4.
## Every frame is a Sprite2D with a CanvasTexture (colour + normal), so any PointLight2D / DirectionalLight2D in the
## scene shades it per pixel. The node's position is the character's anchor: x on its travel line, y on the ground.
##
##   var golem := LitSprite.new()
##   golem.sheet_path = "res://art/golem.json"
##   add_child(golem)
##   golem.move_dir = Input.get_axis("ui_left", "ui_right")   # each frame; golem.play("swing") for a one-shot clip
##
## Motion rules (the same as litsprite.js): the lead clip (walk) advances with distance and the drawn sprite moves in
## frame-synced steps (planted feet never slide); on release it finishes the step (<= ~0.4 s) to the next lead frame
## that matches a rest pose (stops), then crossfades into it; moving again starts from the matching lead frame
## (starts). Other clips play once and return to rest. Facing left mirrors the node (scale.x < 0), so Godot mirrors
## the normals too (flip_h would not).

signal clip_finished(clip: String)

@export_file("*.json") var sheet_path: String
@export var sprite_scale := 1.0
@export var move_dir := 0.0
@export var hurry := false
@export var min_x := -INF
@export var max_x := INF

var M: Dictionary
var lead: Dictionary
var rest: Dictionary
var faces := 1
var face := 1
var mode := "rest"
var dist := 0.0
var t := 0.0
var pose := 0
var rate := 1.0
var fade := 0.0
var shot := ""
var prev := {}
var last := {}
var _spr: Array[Sprite2D] = []

func _ready() -> void:
	if sheet_path != "":
		load_sheet(sheet_path)

func load_sheet(path: String) -> void:
	M = JSON.parse_string(FileAccess.get_file_as_string(path))
	var dir := path.get_base_dir()
	var imgs: Dictionary = M.get("images", {"color": M["name"] + "_color.png", "normal": M["name"] + "_normal.png"})
	var ct := CanvasTexture.new()
	ct.diffuse_texture = _tex(dir.path_join(imgs["color"]))
	ct.normal_texture = _tex(dir.path_join(imgs["normal"]))        # green-up, as Godot expects
	lead = M["anims"][M.get("lead", "walk")]
	var rest_name = M.get("rest", "idle")
	rest = M["anims"][rest_name] if rest_name != null and M["anims"].has(rest_name) else {}
	faces = int(M.get("faces", 1))
	mode = "rest" if not rest.is_empty() else "hold"
	for s in _spr:
		s.queue_free()
	_spr.clear()
	for i in 3:                      # current frame, next pose blended over it, fading previous frame
		var s := Sprite2D.new()
		s.texture = ct
		s.centered = false
		s.region_enabled = true
		s.z_index = i
		add_child(s)
		_spr.append(s)

func _tex(p: String) -> Texture2D:
	if ResourceLoader.exists(p):
		return load(p)
	return ImageTexture.create_from_image(Image.load_from_file(p))   # not imported (e.g. copied at runtime)

func play(clip: String) -> bool:
	if not M["anims"].has(clip):
		return false
	_start_fade()
	shot = clip
	mode = "shot"
	t = 0.0
	return true

func _step() -> float:
	return float(lead.get("speed", 0.0)) * sprite_scale

func _durs(a: Dictionary) -> Array:
	if a.has("durations"):
		return a["durations"]
	var d := []
	for i in int(a["count"]):
		d.append(1.0 / float(a["fps"]))
	return d

func _total(a: Dictionary) -> float:
	var s := 0.0
	for d in _durs(a):
		s += float(d)
	return s

func _at(a: Dictionary, tt: float) -> Vector2:          # (pose index, progress inside it)
	var D := _durs(a)
	var i := 0
	while i < D.size() - 1 and tt >= float(D[i]):
		tt -= float(D[i])
		i += 1
	return Vector2(i, min(1.0, tt / float(D[i])))

func _start_fade() -> void:
	if not last.is_empty():
		prev = last.duplicate()
		fade = 1.0

func _move(d: float) -> void:
	var nx: float = clamp(position.x + d, min_x, max_x)
	dist += abs(nx - position.x)
	position.x = nx

func _process(dt: float) -> void:
	if M.is_empty():
		return
	dt = min(dt, 0.05)
	var n := int(lead["count"])
	var step := _step()
	var iou := float(M.get("stop_iou", 0.85))
	var dir := int(sign(move_dir))
	var v := step * float(lead["fps"]) * (1.6 if hurry else 1.0)
	if mode == "shot":
		t += dt
		if t >= _total(M["anims"][shot]):
			_start_fade()
			var done := shot
			shot = ""
			mode = "rest" if not rest.is_empty() else "hold"
			t = 0.0
			clip_finished.emit(done)
	elif dir != 0 and step > 0.0:
		if mode == "rest":
			var st: Dictionary = M["starts"][pose]
			_start_fade()
			position.x -= face * faces * float(st["dx"]) * sprite_scale
			dist = (float(st["walk"]) + 0.5) * step
		elif dir != face:
			_start_fade()
		face = dir
		mode = "lead"
		_move(dir * v * dt)
	elif dir != 0:
		if dir != face:
			_start_fade()
			face = dir
	elif mode == "lead" or mode == "stopping":
		var k := int(floor(dist / step)) % n
		var stops: Array = M["stops"]
		if rest.is_empty():
			mode = "hold"
		elif mode == "stopping" and float(stops[k]["iou"]) >= iou:
			_start_fade()
			position.x += face * faces * float(stops[k]["dx"]) * sprite_scale
			mode = "rest"
			t = 0.0
			var D := _durs(rest)
			for q in int(stops[k]["idle"]):
				t += float(D[q])
		else:
			if mode != "stopping":           # frames left to the next stop pose, finished within ~0.4 s
				var r := 1
				while r < n and float(stops[(k + r) % n]["iou"]) < iou:
					r += 1
				rate = clamp(r / (0.4 * float(lead["fps"])), 1.0, 4.0)
				mode = "stopping"
			_move(face * v * rate * dt)
	if mode == "rest":
		t += dt
	fade = max(0.0, fade - dt / (float(M.get("blend_frames", 4)) / 12.0))
	_draw_frames()

func _draw_frames() -> void:
	var fi := 0
	var fb := -1
	var fw := 0.0
	var x := global_position.x
	var mirror := face * faces < 0
	if mode == "shot" or mode == "rest":
		var a: Dictionary = M["anims"][shot] if mode == "shot" else rest
		var tt := t if mode == "shot" else fmod(t, _total(a))
		var ip := _at(a, tt)
		var i := int(ip.x)
		if mode == "rest":
			pose = i
		fi = int(a["start"]) + i
		if a.get("blend", false) and (a.get("loop", true) or i + 1 < int(a["count"])):
			fb = int(a["start"]) + (i + 1) % int(a["count"])
			fw = ip.y
	else:
		var step: float = max(_step(), 0.001)
		fi = int(lead["start"]) + int(floor(dist / step)) % int(lead["count"])
		x -= face * fmod(dist, step)            # frame-synced travel: no foot slide
	last = {"fi": fi, "mirror": mirror, "x": x}
	_show(_spr[0], fi, mirror, x, 1.0)
	_show(_spr[1], fb, mirror, x, fw)
	_show(_spr[2], int(prev.get("fi", -1)), bool(prev.get("mirror", false)), float(prev.get("x", x)), fade)

func _show(s: Sprite2D, idx: int, mirror: bool, world_x: float, alpha: float) -> void:
	if idx < 0 or alpha <= 0.01:
		s.visible = false
		return
	var fr: Dictionary = M["frames"][idx]
	s.visible = true
	s.region_rect = Rect2(fr["u"], fr["v"], fr["w"], fr["h"])
	s.offset = Vector2(fr["ox"], fr["oy"])
	s.scale = Vector2(sprite_scale * (-1.0 if mirror else 1.0), sprite_scale)
	s.position = Vector2((world_x - global_position.x) / max(abs(global_scale.x), 0.0001), 0.0)
	s.modulate = Color(1, 1, 1, alpha)
