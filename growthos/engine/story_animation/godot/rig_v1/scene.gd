extends Node2D
# rig_v1 (packaged from the Gate 3c prototype; acting and framing now come from the shot plan): reads ONLY a pack directory and a timeline file given on the command line.
# Usage: godot --path <this dir> main.tscn -- --pack=<dir> --timeline=<file>. Nothing else is read; no network, no user text is evaluated.
# The timeline carries `shots` (one per spoken line): setting, framing, who stands where, mood, gesture, props.; cuts, subtitles, rings derive from timeline.json. Two original characters (Pip, Rosette), dialogue driven by measured audio (timeline.json), mouths from the audio envelope.
# Same puppet technique as scene2.gd, with per-character anchors so a new character is data, not code.

const FPS := 24.0
const W := 540.0
const H := 960.0
const K := 0.28
const FEET_Y := 800.0
const INK := Color(0.03, 0.03, 0.04)

# native anchors per character (pixels of the 1024x1536 source) + sprite names
const CH := {
	"pip": {
		"hip": Vector2(512, 985), "neck": Vector2(512, 636), "sh_l": Vector2(405, 705), "sh_r": Vector2(620, 705),
		"hip_l": Vector2(455, 975), "hip_r": Vector2(572, 975), "wr_l": Vector2(300, 930), "wr_r": Vector2(725, 930),
		"an_l": Vector2(445, 1240), "an_r": Vector2(587, 1240), "shoe_l": Vector2(210, 8), "shoe_r": Vector2(77, 8),
		"glove_l": Vector2(150, 13), "glove_r": Vector2(95, 13), "torso_o": Vector2(385, 636), "head_o": Vector2(265, 262),
		"ground": 445.0, "arm_w": 58.0, "leg_w": 55.0, "dome": true,
		"t_torso": "torso", "t_gl": "glove_l", "t_gr": "glove_r", "t_sl": "shoe_l", "t_sr": "shoe_r",
		"head": {"c": "head_neutral", "o": "head_talk", "r": "head_o", "worry": "head_worried"},
	},
	"ros": {
		"hip": Vector2(517, 1150), "neck": Vector2(490, 690), "sh_l": Vector2(310, 780), "sh_r": Vector2(710, 780),
		"hip_l": Vector2(420, 1150), "hip_r": Vector2(618, 1150), "wr_l": Vector2(275, 940), "wr_r": Vector2(755, 940),
		"an_l": Vector2(448, 1255), "an_r": Vector2(592, 1255), "shoe_l": Vector2(223, 20), "shoe_r": Vector2(67, 20),
		"glove_l": Vector2(107, 13), "glove_r": Vector2(97, 16), "torso_o": Vector2(285, 690), "head_o": Vector2(150, 140),
		"ground": 250.0, "arm_w": 56.0, "leg_w": 58.0, "dome": false,
		"t_torso": "ros_torso", "t_gl": "ros_glove_l", "t_gr": "ros_glove_r", "t_sl": "ros_shoe_l", "t_sr": "ros_shoe_r",
		"head": {"c": "ros_head_blank", "o": "ros_head_blank", "r": "ros_head_blank", "worry": "ros_head_blank"}, "mouth_at": Vector2(-50, -105),
	},
}

var frame := 0
var PACK_DIR := ""
var TIMELINE_PATH := ""
var T := {}
var TL := {}
var vignette: GradientTexture2D

# Looks: a tint multiplied over the finished frame (black stays black, white takes the colour of the paper), plus the
# strength of the film effects. Same drawings, different print. "noir_1930" is the reference look and changes nothing.
const LOOKS := {
	"noir_1930": {"tint": Color(1.0, 1.0, 1.0), "grain": 1.0, "vignette": 1.0},
	"sepia_1930": {"tint": Color(1.0, 0.86, 0.64), "grain": 1.25, "vignette": 1.15},
	"cyanotype_1930": {"tint": Color(0.62, 0.84, 1.0), "grain": 1.1, "vignette": 1.1},
	"couleur_1930": {"tint": Color(1.0, 1.0, 1.0), "grain": 0.8, "vignette": 0.85},
}
var LOOK: Dictionary = LOOKS["noir_1930"]
# Pip's bald dome is filled in code to continue his face: it takes the skin tone of the pack instead of a fixed white
var DOME_FILL := Color(1, 1, 1)

func _fail(msg: String, code: int) -> void:
	push_error(msg)
	get_tree().quit(code)

func _ready() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--pack="):
			PACK_DIR = a.substr(7)
		elif a.begins_with("--timeline="):
			TIMELINE_PATH = a.substr(11)
	if PACK_DIR == "" or TIMELINE_PATH == "":
		_fail("missing --pack or --timeline", 2)
		return
	scale = Vector2(2, 2)
	for n in ["hat", "torso", "glove_l", "glove_r", "shoe_l", "shoe_r", "head_neutral", "head_talk", "head_worried", "head_o", "clock", "head_blank_pip", "ros_head_blank2", "bg_alley", "bg_shop", "bg_street", "bg_cafe",
			"ros_torso", "ros_glove_l", "ros_glove_r", "ros_shoe_l", "ros_shoe_r", "ros_head_blank"]:
		var img := Image.load_from_file(PACK_DIR.path_join(n + ".png"))
		if img == null or img.is_empty():
			_fail("missing or unreadable pack image: " + n, 3)
			return
		T[n] = ImageTexture.create_from_image(img)
		if n == "head_blank_pip":
			DOME_FILL = img.get_pixel(250, 30)
			DOME_FILL.a = 1.0
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(TIMELINE_PATH))
	if typeof(parsed) != TYPE_DICTIONARY or not parsed.has("lines") or not parsed.has("total") or not parsed.has("subs") or not parsed.has("shots") or parsed["shots"].is_empty():
		_fail("invalid timeline file", 4)
		return
	TL = parsed
	var style_id := String(TL.get("style", "noir_1930"))
	LOOK = LOOKS[style_id] if LOOKS.has(style_id) else LOOKS["noir_1930"]
	if LOOK["tint"] != Color(1.0, 1.0, 1.0):
		var tint := ColorRect.new()
		tint.size = Vector2(W, H)
		tint.color = LOOK["tint"]
		var mat := CanvasItemMaterial.new()
		mat.blend_mode = CanvasItemMaterial.BLEND_MODE_MUL
		tint.material = mat
		add_child(tint)
	var g := Gradient.new()
	g.offsets = PackedFloat32Array([0.45, 1.0])
	g.colors = PackedColorArray([Color(0, 0, 0, 0), Color(0, 0, 0, 0.55)])
	vignette = GradientTexture2D.new()
	vignette.gradient = g
	vignette.fill = GradientTexture2D.FILL_RADIAL
	vignette.fill_from = Vector2(0.5, 0.5)
	vignette.fill_to = Vector2(1.0, 0.85)
	vignette.width = 270
	vignette.height = 480

func _process(_d: float) -> void:
	if TL.is_empty():
		return
	if frame / FPS >= TL["total"]:
		get_tree().quit()
		return
	queue_redraw()
	frame += 1

# ---------- helpers ----------
func ease_io(x: float) -> float:
	x = clampf(x, 0.0, 1.0)
	return x * x * (3.0 - 2.0 * x)

func ease_back(x: float) -> float:
	x = clampf(x, 0.0, 1.0)
	return 1.0 + 2.9 * pow(x - 1.0, 3.0) + 1.9 * pow(x - 1.0, 2.0)

func seg(t: float, a: float, b: float) -> float:
	return clampf((t - a) / (b - a), 0.0, 1.0)

func boil(i: float, amp := 1.0) -> Vector2:
	var k := floorf(frame / 2.0)
	return Vector2(sin(k * 7.13 + i * 3.71), cos(k * 5.31 + i * 2.17)) * amp

func cam_xf(zoom: float, c: Vector2, par := 1.0) -> Transform2D:
	c = Vector2(clampf(c.x, 270.0 / zoom, 640.0 - 270.0 / zoom), clampf(c.y, 480.0 / zoom, 960.0 - 480.0 / zoom))
	var cc := c * par + Vector2(320, 480) * (1.0 - par)
	return Transform2D(0.0, Vector2(zoom, zoom), 0.0, Vector2(W, H) * 0.5 - cc * zoom)

func bez(a: Vector2, b: Vector2, bend: float, n := 16) -> PackedVector2Array:
	var d := b - a
	var perp := Vector2(-d.y, d.x).normalized()
	var c := (a + b) * 0.5 + perp * bend
	var pts := PackedVector2Array()
	for i in n + 1:
		var u := float(i) / n
		pts.append(a.lerp(c, u).lerp(c.lerp(b, u), u))
	return pts

func spr(cam: Transform2D, tex: Texture2D, pivot: Vector2, wp: Vector2, ang: float, sx: float, sy: float, seed_: float) -> void:
	var a := ang + sin(floorf(frame / 2.0) * 3.1 + seed_) * 0.006
	draw_set_transform_matrix(cam * Transform2D(a, Vector2(sx, sy), 0.0, wp + boil(seed_, 0.55)))
	draw_texture(tex, -pivot)

func hose(cam: Transform2D, a: Vector2, b: Vector2, bend: float, w: float, seed_: float) -> void:
	draw_set_transform_matrix(cam)
	var pts := bez(a, b, bend)
	for i in pts.size():
		pts[i] += boil(seed_ + i, 0.35)
	draw_polyline(pts, INK, w, true)
	draw_circle(pts[0], w * 0.5, INK)
	draw_circle(pts[pts.size() - 1], w * 0.5, INK)

# mouth class of a character at the current frame: "c" closed, "o" open, "r" round (from the measured audio)
func mouth_of(who: String) -> String:
	var t := frame / FPS
	for l in TL["lines"]:
		if l["who"] == who and t >= l["start"] and t < l["end"]:
			var i := int((t - l["start"]) * FPS)
			var m: String = l["mouth"]
			return m[mini(i, m.length() - 1)]
	return "c"

func speaker_now() -> String:
	var t := frame / FPS
	for l in TL["lines"]:
		if t >= l["start"] and t < l["end"]:
			return l["who"]
	return ""

# mouths drawn in head-local native units so the face never drifts: c closed smile, o open, r/worry round
func draw_mouth(xf_: Transform2D, at: Vector2, key: String) -> void:
	draw_set_transform_matrix(xf_)
	if key == "c":
		var pts := PackedVector2Array()
		for i in 21:
			var u := lerpf(-1.0, 1.0, i / 20.0)
			pts.append(at + Vector2(u * 100.0, -15.0 + 30.0 * (1.0 - u * u)))
		draw_polyline(pts, INK, 7.0, true)
	elif key == "o":
		var m := PackedVector2Array()
		var tg := PackedVector2Array()
		for i in 28:
			var an := TAU * i / 28.0
			m.append(at + Vector2(0, 8) + Vector2(cos(an) * 64.0, sin(an) * 50.0))
			tg.append(at + Vector2(0, 32) + Vector2(cos(an) * 38.0, sin(an) * 17.0))
		draw_colored_polygon(m, INK)
		draw_colored_polygon(tg, Color(0.82, 0.08, 0.08))
	else:
		var m := PackedVector2Array()
		for i in 24:
			var an := TAU * i / 24.0
			m.append(at + Vector2(0, 5) + Vector2(cos(an) * 24.0, sin(an) * 30.0))
		draw_colored_polygon(m, INK)

# ---------- character ----------
func draw_puppet(who: String, P: Dictionary) -> void:
	var C: Dictionary = CH[who]
	var cam: Transform2D = P["cam"]
	var flip: float = P.get("flip", 1.0)
	var rot: float = P.get("lean", 0.0) * flip
	var sqy: float = P.get("squash", 1.0)
	var sqx: float = 1.0 / sqy
	var hip: Vector2 = C["hip"]
	var hipw: Vector2 = P["pos"] + Vector2(0, -P.get("bob", 0.0) - 2.0 * sin(frame / FPS * 3.0))
	var rw := func(n: Vector2) -> Vector2:
		return hipw + (Vector2((n.x - hip.x) * flip * sqx, (n.y - hip.y) * sqy) * K).rotated(rot)
	var fw := func(n: Vector2) -> Vector2:
		return hipw + Vector2((n.x - hip.x) * flip, (n.y - hip.y) * sqy) * K
	var ground: float = P.get("ground", FEET_Y)
	draw_set_transform_matrix(cam)
	var sh := PackedVector2Array()
	for i in 24:
		var an := TAU * i / 24.0
		sh.append(Vector2(P["pos"].x + cos(an) * 74.0, ground + 4 + sin(an) * 10))
	draw_colored_polygon(sh, Color(0, 0, 0, 0.28))
	var al: Vector2 = P.get("ankle_l", C["an_l"])
	var ar: Vector2 = P.get("ankle_r", C["an_r"])
	hose(cam, fw.call(C["hip_l"]), fw.call(al), -6.0 * flip, C["leg_w"] * K, 1.0)
	hose(cam, fw.call(C["hip_r"]), fw.call(ar), -6.0 * flip, C["leg_w"] * K, 2.0)
	var fa: float = P.get("foot_ang", 0.0) * flip
	spr(cam, T[C["t_sl"]], C["shoe_l"], fw.call(al), fa, K * flip, K * sqy, 3.0)
	spr(cam, T[C["t_sr"]], C["shoe_r"], fw.call(ar), fa, K * flip, K * sqy, 4.0)
	var idle := Vector2(sin(frame / FPS * 2.1 + (1.0 if who == "pip" else 0.0)) * 10.0, cos(frame / FPS * 2.6) * 7.0)
	var wl: Vector2 = P.get("wrist_l", C["wr_l"]) + idle
	var wr: Vector2 = P.get("wrist_r", C["wr_r"]) - idle
	var bl: float = P.get("bend_l", 10.0)
	var br: float = P.get("bend_r", -10.0)
	hose(cam, rw.call(C["sh_l"]), rw.call(wl), bl * flip, C["arm_w"] * K, 5.0)
	hose(cam, rw.call(C["sh_r"]), rw.call(wr), br * flip, C["arm_w"] * K, 6.0)
	spr(cam, T[C["t_torso"]], hip - C["torso_o"], hipw, rot, K * flip * sqx, K * sqy, 7.0)
	# head
	var neck_w: Vector2 = rw.call(C["neck"])
	var pop: float = P.get("head_pop", 1.0)
	var hang: float = rot + P.get("tilt", 0.0) * flip
	var key: String = P.get("head_key", mouth_of(who))
	var hp: Vector2 = C["head_o"]
	var neck: Vector2 = C["neck"]
	if C["dome"]:
		draw_set_transform_matrix(cam * Transform2D(hang, Vector2(K * flip * pop, K * pop), 0.0, neck_w))
		var dome := PackedVector2Array()
		var ctr := Vector2(4, -246.0)
		for i in range(0, 41):
			var an := lerpf(PI + 0.56, TAU - 0.56, float(i) / 40.0)
			dome.append(ctr + Vector2(cos(an), sin(an)) * 233.0)
		var cap := dome.duplicate()
		cap.append(Vector2(dome[40].x, -336.0)); cap.append(Vector2(dome[0].x, -336.0))
		draw_colored_polygon(cap, DOME_FILL)
		draw_polyline(dome, INK, 13.0, true)
	spr(cam, T["head_blank_pip" if who == "pip" else "ros_head_blank2"], neck - hp, neck_w, hang, K * flip * pop, K * pop, 8.0)
	draw_face(cam * Transform2D(hang, Vector2(K * flip * pop, K * pop), 0.0, neck_w), who, P, key)
	if C["dome"] and (not P.get("hat_off", false) or P.has("hat_world")):
		if P.has("hat_world"):
			spr(cam, T["hat"], Vector2(184, 183), P["hat_world"], P.get("hat_rot", 0.0), K * flip, K, 9.0)
		else:
			var top := neck_w + Vector2(0, -(neck.y - 238.0) * K * pop).rotated(hang)
			spr(cam, T["hat"], Vector2(184, 183), top + Vector2(0, P.get("hat_lift", 0.0)).rotated(hang), hang, K * flip, K, 9.0)
	for side in [0, 1]:
		var tgt: Vector2 = rw.call(wl if side == 0 else wr)
		var origin: Vector2 = rw.call(C["sh_l"] if side == 0 else C["sh_r"])
		var pts := bez(origin, tgt, (bl if side == 0 else br) * flip)
		var dir: Vector2 = (pts[pts.size() - 1] - pts[pts.size() - 4]).normalized()
		spr(cam, T[C["t_gl"] if side == 0 else C["t_gr"]], C["glove_l"] if side == 0 else C["glove_r"], tgt, dir.angle() - PI * 0.5, K * flip, K, 10.0 + side)
	draw_set_transform_matrix(Transform2D.IDENTITY)

# ---------- world ----------
func draw_world(cam: Transform2D, t: float, bg: String, ring: float, clock_x: float, clock_move := 0.0, clock_vis := true) -> void:
	draw_set_transform_matrix(cam)
	draw_texture_rect(T[bg], Rect2(0, 0, 640, 960), false)
	if bg == "bg_alley":
		for ci in 2:
			var cx := 560.0 + ci * 48.0
			for p in 5:
				var u := fmod(t * 0.3 + p * 0.2 + ci * 0.37, 1.0)
				var pc := Vector2(cx + u * 70.0 + sin(u * 8.0) * 8.0, 280.0 - ci * 40.0 - u * 150.0)
				draw_circle(pc + boil(p + ci * 9, 1.0), 12 + u * 26, Color(0.82, 0.82, 0.80, 0.55 * (1.0 - u)))
	if not clock_vis:
		draw_set_transform_matrix(Transform2D.IDENTITY)
		return
	var act := maxf(ring, clock_move)
	var ph := absf(sin(frame * 0.9))
	var base := Vector2(clock_x, FEET_Y + 6)
	var hop: float = ph * 16.0 * act
	var kc := 0.2
	var sx := kc * (1.0 + 0.09 * (1.0 - ph) * act)
	var sy := kc * (1.0 - 0.11 * (1.0 - ph) * act)
	var shake := sin(frame * 2.7) * 0.07 * ring + 0.12 * clock_move
	spr(cam, T["clock"], Vector2(328, 780), base + Vector2(0, -hop), shake, sx, sy, 20.0)
	if ring > 0.0:
		draw_set_transform_matrix(cam)
		for k in 3:
			var rr := 78.0 + k * 13.0 + fmod(frame * 2.5, 13.0)
			draw_arc(base + Vector2(0, -85 - hop), rr, -2.45, -0.7, 10, INK, 2.6, true)
			draw_arc(base + Vector2(0, -85 - hop), rr, -2.45 + 3.14, -0.7 + 3.14 - 0.6, 10, INK, 2.6, true)
	draw_set_transform_matrix(Transform2D.IDENTITY)

# ---------- procedural settings: drawn in code over the same background pictures, no new asset ----------
const QUEUE_MAX := 44

func draw_setting_back(cam: Transform2D, t: float, sh: Dictionary) -> void:
	if String(sh.get("setting", "")) == "street_queue":
		draw_queue(cam, t)

func draw_setting_front(cam: Transform2D, t: float, sh: Dictionary) -> void:
	var s := String(sh.get("setting", ""))
	if s == "street_rain":
		draw_rain(cam, t)
	elif s == "clock_shop_closed":
		draw_night_shop(cam, t)

# a queue of black silhouettes down the middle of the street (between the two characters), toward a closed door; it grows with the story's time ("forty, then a hundred")
func draw_queue(cam: Transform2D, t: float) -> void:
	draw_set_transform_matrix(cam)
	draw_rect(Rect2(292.0, 458.0, 30.0, 58.0), INK)
	draw_circle(Vector2(315.0, 490.0), 2.2, Color(0.92, 0.92, 0.9))
	var n := clampi(6 + int(t * 1.6), 6, QUEUE_MAX)
	for k in range(n):
		var i := n - 1 - k
		var u := float(i) / float(QUEUE_MAX)
		var d := pow(u, 0.9)
		var sc := lerpf(0.58, 0.19, u)
		var pos := Vector2(lerpf(262.0, 316.0, d) + (9.0 if i % 2 == 0 else -9.0) * sc, lerpf(690.0, 506.0, d))
		pos.y += sin(t * 3.0 + float(i) * 1.7) * 1.6 * sc
		pos += boil(float(i) * 3.1, 0.5 * sc)
		draw_set_transform_matrix(cam * Transform2D(0.0, Vector2(sc, sc), 0.0, pos))
		draw_colored_polygon(ell_pts(Vector2(0, 2), 34.0, 9.0, 16), Color(0, 0, 0, 0.3))
		draw_rect(Rect2(-17.0, -118.0, 34.0, 118.0), INK)
		draw_circle(Vector2(0, -136.0), 21.0, Color(0.96, 0.96, 0.94))
		draw_arc(Vector2(0, -136.0), 21.0, 0.0, TAU, 20, INK, 4.0, true)
		if i % 3 == 0:
			draw_rect(Rect2(-24.0, -160.0, 48.0, 7.0), INK)
			draw_rect(Rect2(-15.0, -184.0, 30.0, 26.0), INK)
		elif i % 3 == 1:
			draw_colored_polygon(ell_pts(Vector2(0, -150.0), 26.0, 12.0, 16), INK)
	draw_set_transform_matrix(Transform2D.IDENTITY)

func draw_rain(cam: Transform2D, t: float) -> void:
	draw_set_transform_matrix(cam)
	draw_rect(Rect2(0.0, 0.0, 640.0, 960.0), Color(0.04, 0.05, 0.08, 0.22))
	for i in 150:
		var x := fmod(float(i) * 97.0 + t * 60.0, 700.0) - 30.0
		var y := fmod(float(i) * 53.0 + t * 640.0 * (0.8 + 0.4 * fmod(float(i) * 0.37, 1.0)), 1000.0) - 20.0
		var len := 22.0 + float(i % 5) * 6.0
		draw_line(Vector2(x, y), Vector2(x - 8.0, y + len), Color(0.92, 0.93, 0.95, 0.5), 1.8)
	draw_set_transform_matrix(Transform2D.IDENTITY)

func draw_night_shop(cam: Transform2D, t: float) -> void:
	draw_set_transform_matrix(cam)
	draw_rect(Rect2(0.0, 0.0, 640.0, 960.0), Color(0.02, 0.03, 0.08, 0.5))
	var font := ThemeDB.fallback_font
	draw_set_transform_matrix(cam * Transform2D(-0.05, Vector2(1.0, 1.0), 0.0, Vector2(92.0, 455.0)))
	draw_rect(Rect2(-46.0, -26.0, 92.0, 38.0), Color(0.93, 0.9, 0.82))
	draw_rect(Rect2(-46.0, -26.0, 92.0, 38.0), INK, false, 3.0)
	draw_string(font, Vector2(-34.0, 0.0), "FERMÉ", HORIZONTAL_ALIGNMENT_LEFT, -1, 24, INK)
	draw_set_transform_matrix(Transform2D.IDENTITY)

func overlays(t: float) -> void:
	draw_set_transform_matrix(Transform2D.IDENTITY)
	draw_texture_rect(vignette, Rect2(0, 0, W, H), false, Color(1, 1, 1, clampf(float(LOOK["vignette"]) - 0.0, 0.0, 1.0)))
	var fl := (0.04 * sin(frame * 5.7) + 0.02 * sin(frame * 13.1)) * float(LOOK["grain"])
	draw_rect(Rect2(0, 0, W, H), Color(0, 0, 0, clampf(0.05 + fl, 0.0, 1.0)) if fl > 0 else Color(1, 1, 1, clampf(-fl, 0.0, 1.0)))
	for i in 90:
		var k := frame * 131.0 + i * 17.0
		draw_rect(Rect2(fmod(k * 7.31, W), fmod(k * 3.77, H), 2, 2), Color(0, 0, 0, 0.16) if i % 3 else Color(1, 1, 1, 0.2))
	draw_cards(t)
	for s in TL["subs"]:
		if t >= s["start"] and t < s["end"]:
			draw_sub(String(s["text"]))
	var fade := minf(clampf(t / 0.3, 0.0, 1.0), clampf((float(TL["total"]) - t) / 0.7, 0.0, 1.0))
	if fade < 1.0:
		draw_rect(Rect2(0, 0, W, H), Color(0, 0, 0, 1.0 - fade))

# A word the narrator puts between quotation marks appears large on screen while it is spoken: something to see during the narration.
func draw_cards(t: float) -> void:
	for c in TL.get("cards", []):
		var a := float(c["start"])
		var b := float(c["end"])
		if t < a or t >= b:
			continue
		var pop := ease_back(seg(t, a, a + 0.22))
		var fade := 1.0 - seg(t, b - 0.3, b)
		var text := String(c["text"]).to_upper()
		var font := ThemeDB.fallback_font
		var size := 84
		var w := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
		if w > W - 80.0:
			size = int(size * (W - 80.0) / w)
			w = font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
		var sc := lerpf(0.72, 1.0, pop)
		draw_set_transform_matrix(Transform2D(-0.04, Vector2(sc, sc), 0.0, Vector2(W * 0.5, 215.0)))
		draw_rect(Rect2(-w * 0.5 - 26.0, -size * 0.95, w + 52.0, size * 1.3), Color(0.04, 0.04, 0.05, 0.62 * fade))
		draw_string_outline(font, Vector2(-w * 0.5, 0.0), text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, 10, Color(0, 0, 0, fade))
		draw_string(font, Vector2(-w * 0.5, 0.0), text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, Color(1.0, 0.95, 0.75, fade))
	draw_set_transform_matrix(Transform2D.IDENTITY)

func draw_sub(text: String) -> void:
	var font := ThemeDB.fallback_font
	var size := 38
	var w := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
	if w > W - 60.0:
		size = int(size * (W - 60.0) / w)
		w = font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
	var x := (W - w) * 0.5
	var y := 860.0
	draw_rect(Rect2(x - 16, y - size - 4, w + 32, size + 22), Color(0.04, 0.04, 0.05, 0.7))
	draw_string_outline(font, Vector2(x, y), text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, 6, Color(0, 0, 0, 1))
	draw_string(font, Vector2(x, y), text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, Color(1.0, 0.95, 0.75))

func walk_pose(C: Dictionary, ph: float, amp: float) -> Dictionary:
	var a := sin(ph)
	var b := sin(ph + PI)
	var al: Vector2 = C["an_l"]
	var ar: Vector2 = C["an_r"]
	var wl: Vector2 = C["wr_l"]
	var wr: Vector2 = C["wr_r"]
	return {
		"ankle_l": Vector2(al.x + a * 110.0 * amp, al.y - maxf(0.0, cos(ph)) * 95.0 * amp),
		"ankle_r": Vector2(ar.x + b * 110.0 * amp, ar.y - maxf(0.0, cos(ph + PI)) * 95.0 * amp),
		"wrist_l": Vector2(wl.x - b * 70.0 * amp, wl.y - absf(b) * 50.0 * amp),
		"wrist_r": Vector2(wr.x + a * 70.0 * amp, wr.y - absf(a) * 50.0 * amp),
		"bob": absf(cos(ph)) * 5.0 * amp, "foot_ang": 0.14 * cos(ph) * amp,
		"squash": 1.0 + 0.045 * cos(2.0 * ph) * amp,
	}

func hip_y(who: String) -> float:
	return FEET_Y - float(CH[who]["ground"]) * K

func merge_into(dst: Dictionary, src: Dictionary) -> void:
	for k in src:
		dst[k] = src[k]

func smooth_env(who: String) -> float:
	var e := 0.0
	for d in [-2, -1, 0, 1, 2]:
		var f: int = frame + d
		var t: float = f / FPS
		for l in TL["lines"]:
			if l["who"] == who and t >= l["start"] and t < l["end"]:
				var i := int((t - l["start"]) * FPS)
				var m: String = l["mouth"]
				e += 1.0 if m[mini(i, m.length() - 1)] != "c" else 0.0
	return e / 5.0

# ---------- shots, driven by TL["shots"] (the shot plan built by the engine from the validated contract) ----------
const SIDE_X := {"left": 165.0, "center": 320.0, "right": 465.0}
const HAT_LOSS_AT := {"clutch_head": 1.2, "run_away": 0.6}

func shot_index_at(t: float) -> int:
	var S: Array = TL["shots"]
	var idx := 0
	for i in range(S.size()):
		if t >= float(S[i]["start"]):
			idx = i
	return idx

func actor_of(sh: Dictionary, role: String) -> Variant:
	for a in sh["actors"]:
		if a["role"] == role:
			return a
	return null

func facing_flip(a: Dictionary) -> float:
	return 1.0 if a["facing"] == "right" else -1.0

# screen direction (+1 right, -1 left) from this actor toward the other one in the shot (its own facing when alone)
func dir_to_other(sh: Dictionary, a: Dictionary) -> float:
	for o in sh["actors"]:
		if o["role"] != a["role"]:
			var dx: float = float(SIDE_X[o["side"]]) - float(SIDE_X[a["side"]])
			if absf(dx) > 1.0:
				return 1.0 if dx > 0.0 else -1.0
	return facing_flip(a)

func arm(P: Dictionary, right: bool, target: Vector2, bend: float) -> void:
	P["wrist_r" if right else "wrist_l"] = target
	P["bend_r" if right else "bend_l"] = -absf(bend) if right else absf(bend)

func rest_pose(role: String) -> Dictionary:
	if role == "pip":
		return {"wrist_l": Vector2(440, 905), "bend_l": 30.0, "wrist_r": Vector2(585, 895), "bend_r": -30.0, "lean": -0.04}
	return {"wrist_l": Vector2(250, 990), "bend_l": 45.0, "wrist_r": Vector2(785, 990), "bend_r": -45.0}

# Gesture library: hand targets are native pixels relative to the character's own anchors, so one gesture fits both packs.
# `dn` is the native direction (+1 = native right arm) that points toward the other actor.
func gesture_pose(role: String, g: String, dn: float, tt: float, e: float) -> Dictionary:
	var C: Dictionary = CH[role]
	var hip: Vector2 = C["hip"]
	var neck: Vector2 = C["neck"]
	var P := rest_pose(role)
	var right := dn > 0.0
	var sh: Vector2 = C["sh_r"] if right else C["sh_l"]
	match g:
		"accuse":
			arm(P, right, sh + Vector2(580.0 * dn, 18.0 * sin(tt * 7.0) * e), 45.0)
			arm(P, not right, hip + Vector2(-147.0 * dn, -80.0), 70.0)
			P["lean"] = 0.07
			P["tilt"] = 0.04 * sin(tt * 4.0) * e
		"point":
			arm(P, right, sh + Vector2(330.0 * dn, 420.0), 30.0)
			arm(P, not right, hip + Vector2(-147.0 * dn, -80.0), 70.0)
			P["tilt"] = -0.05
		"defend":
			arm(P, false, neck + Vector2(-212.0 + 26.0 * sin(tt * 9.0) * e, 10.0), 35.0)
			arm(P, true, neck + Vector2(213.0 - 26.0 * sin(tt * 9.0) * e, 10.0), 35.0)
			P["lean"] = -0.05
			P["tilt"] = 0.06 * sin(tt * 5.0) * e
		"wring":
			arm(P, false, hip + Vector2(-42.0 + 28.0 * sin(tt * 10.0), -100.0), 30.0)
			arm(P, true, hip + Vector2(43.0 - 28.0 * sin(tt * 10.0), -115.0), 30.0)
			P["lean"] = 0.1
		"indignant":
			arm(P, false, hip + Vector2(-302.0, -140.0 + 26.0 * sin(tt * 13.0) * e), 70.0)
			arm(P, true, hip + Vector2(303.0, -140.0 - 26.0 * sin(tt * 13.0) * e), 70.0)
			P["lean"] = 0.1 + 0.03 * sin(tt * 8.0) * e
			P["squash"] = 1.0 - 0.07 * absf(sin(tt * 6.5)) * e
			P["tilt"] = 0.06 * sin(tt * 9.0)
		"clutch_head":
			var k := ease_io(seg(tt, 0.5, 1.0))
			var rl: Vector2 = P["wrist_l"]
			var rr: Vector2 = P["wrist_r"]
			var hold_l := Vector2(-132.0, -136.0)
			var hold_r := Vector2(128.0, -156.0)
			if role == "pip":
				# his glasses sit about 250 px above the neck anchor: the hands hold the top of the head, clear of the eyes
				hold_l = Vector2(-250.0, -392.0)
				hold_r = Vector2(250.0, -402.0)
			arm(P, false, rl.lerp(neck + hold_l, k), 40.0)
			arm(P, true, rr.lerp(neck + hold_r, k), 40.0)
			P["lean"] = -0.08 * k
		"hands_on_hips":
			arm(P, false, hip + Vector2(-147.0, -80.0), 80.0)
			arm(P, true, hip + Vector2(147.0, -80.0), 80.0)
			P["lean"] = 0.06
		"shrug":
			arm(P, false, hip + Vector2(-260.0, -230.0), 50.0)
			arm(P, true, hip + Vector2(260.0, -230.0), 50.0)
			P["squash"] = 0.97
			P["tilt"] = 0.05 * sin(tt * 3.0)
		"wave":
			arm(P, true, neck + Vector2(330.0, -60.0 + 40.0 * sin(tt * 8.0)), 40.0)
	return P

# Body life on top of the acted gesture, so nobody freezes between gestures: breathing, weight shift, drifting hands,
# accents on the spoken beats, and a listener who reacts to the speaker. Everything stays small enough that no hand
# can reach the face (the gesture gallery checks every gesture for both characters).
func add_life(role: String, P: Dictionary, t: float, tt: float, e: float, speaking: bool, mood: String) -> void:
	var ph := 1.0 if role == "pip" else 2.3
	var other_e := smooth_env("ros" if role == "pip" else "pip")
	P["squash"] = float(P.get("squash", 1.0)) + 0.014 * sin(t * 2.4 + ph)
	P["lean"] = float(P.get("lean", 0.0)) + 0.02 * sin(t * 0.9 + ph)
	P["tilt"] = float(P.get("tilt", 0.0)) + 0.035 * sin(t * 1.3 + ph * 2.0)
	var drift_l := Vector2(sin(t * 1.7 + ph) * 34.0, cos(t * 2.1 + ph) * 24.0)
	var drift_r := Vector2(sin(t * 1.9 + ph + 1.7) * -34.0, cos(t * 2.3 + ph + 0.6) * 24.0)
	if speaking:
		# a stroke on the syllable rhythm: the head dips, the shoulders drop, the hands punctuate
		var hit := maxf(0.0, sin(t * 7.3 + ph)) * e
		P["bob"] = float(P.get("bob", 0.0)) + 5.0 * hit
		P["tilt"] = float(P["tilt"]) + 0.05 * e * sin(t * 4.1 + ph)
		P["lean"] = float(P["lean"]) + 0.025 * hit
		drift_l += Vector2(0.0, -44.0 * hit)
		drift_r += Vector2(0.0, -44.0 * hit)
		P["squash"] = float(P["squash"]) + 0.09 * exp(-tt * 5.0) * sin(tt * 26.0)
	else:
		# listening: small nods and a lean toward the speaker while they talk
		P["tilt"] = float(P["tilt"]) + 0.045 * other_e * sin(t * 3.7 + ph)
		P["bob"] = float(P.get("bob", 0.0)) + 2.5 * other_e * maxf(0.0, sin(t * 3.7 + ph))
		P["lean"] = float(P["lean"]) + 0.03 * other_e
	if mood == "worry" or mood == "panic":
		drift_l += Vector2(sin(t * 19.0) * 9.0, 0.0)
		drift_r += Vector2(sin(t * 17.0 + 1.0) * 9.0, 0.0)
	elif mood == "angry":
		P["lean"] = float(P["lean"]) + 0.03 + 0.02 * sin(t * 6.0)
	elif mood == "joy":
		P["bob"] = float(P.get("bob", 0.0)) + 3.0 * absf(sin(t * 5.0 + ph))
	P["wrist_l"] = Vector2(P["wrist_l"]) + drift_l
	P["wrist_r"] = Vector2(P["wrist_r"]) + drift_r

func act(role: String, t: float) -> Dictionary:
	var sh: Dictionary = TL["shots"][shot_index_at(t)]
	var a: Variant = actor_of(sh, role)
	var e := smooth_env(role)
	var P: Dictionary
	var mood := "neutral"
	if a == null:
		P = rest_pose(role)
	else:
		var tt: float = t - float(sh["start"])
		var g: String = a["gesture"]
		if g == "run_away" and tt < 0.9:
			g = "clutch_head"
		P = gesture_pose(role, g, dir_to_other(sh, a) * facing_flip(a), tt, e)
		mood = a["mood"]
		if sh["speaker"] == role:
			P["bob"] = 3.0 * e
			P["squash"] = float(P.get("squash", 1.0)) - 0.04 * e
	P["mood"] = mood
	P["e"] = e
	add_life(role, P, t, t - float(sh["start"]), e, sh["speaker"] == role, mood)
	return smooth_pose(role, P)

# time at which Pip's hat comes off (it never comes back), or a huge number
func hat_loss_time() -> float:
	var best := 1.0e9
	for sh in TL["shots"]:
		var a: Variant = actor_of(sh, "pip")
		if a != null and HAT_LOSS_AT.has(a["gesture"]):
			best = minf(best, float(sh["start"]) + float(HAT_LOSS_AT[a["gesture"]]))
	return best

func actor_x_at(sh: Dictionary, a: Dictionary, t: float) -> float:
	var x: float = SIDE_X[a["side"]]
	if a["gesture"] == "run_away":
		var tt: float = t - float(sh["start"])
		var span: float = maxf(float(sh["end"]) - float(sh["start"]) - 0.9, 0.5)
		x += facing_flip(a) * 480.0 * ease_io(seg(tt, 0.9, 0.9 + span))
	return x

# the alarm clock follows the actor that carries it: beside them, or chasing them when they run away
func prop_state(sh: Dictionary, t: float) -> Dictionary:
	for a in sh["actors"]:
		if "alarm_clock" in a["props"]:
			var ax := actor_x_at(sh, a, t)
			if a["gesture"] == "run_away" and t - float(sh["start"]) > 0.9:
				return {"vis": true, "x": ax - facing_flip(a) * 150.0, "ring": 1.0, "move": 1.0}
			return {"vis": true, "x": SIDE_X[a["side"]] + dir_to_other(sh, a) * 130.0, "ring": 1.0, "move": 0.0}
	return {"vis": false, "x": 320.0, "ring": 0.0, "move": 0.0}

func shot_camera(sh: Dictionary, t: float, prop: Dictionary) -> Transform2D:
	var u := seg(t, float(sh["start"]), float(sh["end"]))
	var c: Dictionary = sh["camera"]
	var zoom := lerpf(float(c["zoom_from"]), float(c["zoom_to"]), ease_io(u))
	zoom *= 1.0 + 0.012 * maxf(smooth_env("ros"), smooth_env("pip"))
	var centre := Vector2(320, 560)
	var st: String = sh["shot_type"]
	var sp: String = sh["speaker"]
	var sa: Variant = actor_of(sh, sp)
	var focus_role = sh.get("focus", null)
	var fa: Variant = actor_of(sh, focus_role) if focus_role != null else null
	if fa != null:
		centre = Vector2(actor_x_at(sh, fa, t) + 10.0 * facing_flip(fa), hip_y(String(focus_role)) - (170.0 if focus_role == "pip" else 215.0))
		zoom *= 0.95 + 0.05 * ease_back(seg(t, float(sh["start"]), float(sh["start"]) + 0.25))
	elif st == "medium":
		var sx := 0.0
		for a in sh["actors"]:
			sx += actor_x_at(sh, a, t)
		centre = Vector2(sx / float(sh["actors"].size()), 600) if sh["actors"].size() > 0 else Vector2(320, 600)
	elif st == "close_up" and sa != null:
		centre = Vector2(actor_x_at(sh, sa, t) + 10.0 * facing_flip(sa), hip_y(sp) - (170.0 if sp == "pip" else 215.0))
		zoom *= 0.95 + 0.05 * ease_back(seg(t, float(sh["start"]), float(sh["start"]) + 0.25))
	elif st == "insert" and prop["vis"]:
		centre = Vector2(float(prop["x"]), FEET_Y - 60.0)
	centre += Vector2(sin(t * 0.55) * 5.0, cos(t * 0.43) * 3.5)
	if c["move"] == "pan_left":
		centre.x -= 40.0 * (u - 0.5) * 2.0
	elif c["move"] == "pan_right":
		centre.x += 40.0 * (u - 0.5) * 2.0
	return cam_xf(zoom, centre)

func draw_actor(sh: Dictionary, a: Dictionary, t: float, cam: Transform2D) -> void:
	var role: String = a["role"]
	var P: Dictionary = POSES[role].duplicate()
	var tt: float = t - float(sh["start"])
	var flip := facing_flip(a)
	P["cam"] = cam
	P["flip"] = flip
	P["pos"] = Vector2(actor_x_at(sh, a, t), hip_y(role))
	if role == "pip":
		var lost := hat_loss_time()
		if t > lost:
			P["hat_off"] = true
			var hu := seg(t - lost, 0.0, 1.2)
			if hu < 1.0:
				P["hat_world"] = Vector2(P["pos"].x + 18.0 * hu, hip_y(role) - 300.0 - 260.0 * sin(PI * hu * 0.5) + 360.0 * hu * hu)
				P["hat_rot"] = hu * 8.0
	if a["gesture"] == "run_away":
		if tt < 0.9:
			var ant := ease_io(seg(tt, 0.55, 0.9))
			P["squash"] = 1.0 - 0.13 * ant
			P["lean"] = -0.15 * ant
		else:
			merge_into(P, walk_pose(CH[role], t * 17.0, 1.6))
			P["lean"] = 0.22
	draw_puppet(role, P)

func _draw() -> void:
	draw_rect(Rect2(0, 0, W, H), Color.BLACK)
	var t := frame / FPS
	var sh: Dictionary = TL["shots"][shot_index_at(t)]
	POSES = {"ros": act("ros", t), "pip": act("pip", t)}
	var prop := prop_state(sh, t)
	var cam := shot_camera(sh, t, prop)
	draw_world(cam, t, sh["background"], float(prop["ring"]), float(prop["x"]), float(prop["move"]), bool(prop["vis"]))
	draw_setting_back(cam, t, sh)
	var order: Array = [] if bool(sh.get("empty", false)) else sh["actors"].duplicate()
	order.sort_custom(func(p, q): return float(SIDE_X[p["side"]]) < float(SIDE_X[q["side"]]))
	for a in order:
		draw_actor(sh, a, t, cam)
	draw_setting_front(cam, t, sh)
	if sh["transition_in"] == "fade":
		var f := 1.0 - seg(t, float(sh["start"]), float(sh["start"]) + 0.3)
		if f > 0.0:
			draw_set_transform_matrix(Transform2D.IDENTITY)
			draw_rect(Rect2(0, 0, W, H), Color(0, 0, 0, f))
	overlays(t)

# ---------- faces drawn in code: any mood, gaze, blink and mouth shape on a faceless generated base ----------
const MOODS := {
	"neutral": {"by": 0.0, "tilt": 0.0, "eye": 1.0, "pup": 1.0, "smile": 0.35},
	"worry": {"by": 0.5, "tilt": 0.9, "eye": 1.05, "pup": 0.8, "smile": -0.5},
	"angry": {"by": -0.4, "tilt": -0.9, "eye": 0.8, "pup": 0.9, "smile": -0.7},
	"surprise": {"by": 1.0, "tilt": 0.0, "eye": 1.3, "pup": 0.55, "smile": 0.0},
	"joy": {"by": 0.3, "tilt": 0.0, "eye": 0.85, "pup": 1.0, "smile": 1.0},
	"puzzled": {"by": 0.2, "tilt": 0.3, "eye": 1.0, "pup": 0.9, "smile": -0.1, "bl": 0.9, "br": -0.3},
	"panic": {"by": 1.0, "tilt": 0.7, "eye": 1.35, "pup": 0.45, "smile": -0.8},
}
var FACE := {}
var SM := {}
var POSES := {}

func ell_pts(c: Vector2, rx: float, ry: float, n := 22) -> PackedVector2Array:
	var pts := PackedVector2Array()
	for i in n:
		var an := TAU * i / n
		pts.append(c + Vector2(cos(an) * rx, sin(an) * ry))
	return pts

func brow(c: Vector2, s: float, half: float, raise: float, tilt: float, w: float) -> void:
	var inner := c + Vector2(-s * half, -raise - tilt * half * 0.55)
	var outer := c + Vector2(s * half, -raise + tilt * half * 0.2)
	var pts := bez(outer, inner, -s * 9.0)
	draw_polyline(pts, INK, w, true)
	draw_circle(outer, w * 0.5, INK)
	draw_circle(inner, w * 0.5, INK)

func blink_amt(who: String) -> float:
	var period := 77 if who == "pip" else 91
	var off := 11 if who == "pip" else 30
	var k := (frame + off) % period
	return 1.0 if k < 4 else 0.0

func draw_face(xf_: Transform2D, who: String, P: Dictionary, key: String) -> void:
	var mood: String = P.get("mood", "neutral")
	var tgt: Dictionary = MOODS[mood]
	if not FACE.has(who):
		FACE[who] = tgt.duplicate()
	var F: Dictionary = FACE[who]
	for k in ["by", "tilt", "eye", "pup", "smile", "bl", "br"]:
		F[k] = lerpf(float(F.get(k, 0.0)), float(tgt.get(k, 0.0)), 0.3)
	var bl := blink_amt(who)
	var gaze: Vector2 = P.get("gaze", Vector2(0.7, 0.0))
	var e: float = P.get("e", 0.0)
	var vis := key if key in ["c", "o", "r"] else "c"
	if vis == "o":
		e = maxf(e, 0.45)
	draw_set_transform_matrix(xf_)
	var raise: float = float(F["by"]) * 26.0
	if who == "ros":
		var ec := [Vector2(-90, -215), Vector2(7, -215)]
		for i in 2:
			var c: Vector2 = ec[i] + gaze * Vector2(10, 6)
			var ry: float = lerpf(26.0 * float(F["eye"]), 3.0, bl)
			draw_colored_polygon(ell_pts(c, 15.0, ry), INK)
			brow(Vector2(ec[i].x, -285.0), -1.0 if i == 0 else 1.0, 40.0, raise + (float(F["bl"]) if i == 0 else float(F["br"])) * 22.0, float(F["tilt"]), 7.0)
		var nose := ell_pts(Vector2(-55, -158), 38.0, 24.0)
		nose.append(nose[0])
		draw_polyline(nose, INK, 6.0, true)
		var at := Vector2(-50, -105)
		if vis == "c":
			var sm: float = float(F["smile"])
			var pts := PackedVector2Array()
			for i in 21:
				var u := lerpf(-1.0, 1.0, i / 20.0)
				pts.append(at + Vector2(u * 100.0, -sm * 26.0 + sm * 52.0 * (1.0 - u * u)))
			draw_polyline(pts, INK, 7.0, true)
		elif vis == "o":
			var ry2 := 24.0 + 30.0 * e
			draw_colored_polygon(ell_pts(at + Vector2(0, 8), 52.0 + 14.0 * e, ry2), INK)
			draw_colored_polygon(ell_pts(at + Vector2(0, 8 + ry2 * 0.55), 34.0, ry2 * 0.38), Color(0.82, 0.08, 0.08))
		else:
			draw_colored_polygon(ell_pts(at + Vector2(0, 5), 24.0, 30.0), INK)
	else:
		var lens := [Vector2(-95, -252), Vector2(75, -252)]
		for i in 2:
			var c: Vector2 = lens[i] + gaze * Vector2(26.0, 20.0)
			if bl > 0.5:
				draw_polyline(bez(lens[i] + Vector2(-48, 4), lens[i] + Vector2(48, 4), 14.0), INK, 8.0, true)
			else:
				var pr: float = float(F["pup"])
				draw_colored_polygon(ell_pts(c, 24.0 * pr + 4.0, 34.0 * pr * minf(1.15, float(F["eye"])) + 4.0), INK)
				draw_circle(c + Vector2(-8, -12) * pr, 7.0, Color(1, 1, 1))
			brow(Vector2(lens[i].x, -352.0), -1.0 if i == 0 else 1.0, 52.0, raise * 0.6 + (float(F["bl"]) if i == 0 else float(F["br"])) * 14.0, float(F["tilt"]), 11.0)
		var mc := Vector2(-2, -39)
		if vis == "c":
			var sm2: float = float(F["smile"])
			if absf(sm2) > 0.2:
				var pts2 := PackedVector2Array()
				for i in 21:
					var u := lerpf(-1.0, 1.0, i / 20.0)
					pts2.append(mc + Vector2(u * 62.0, 12.0 - sm2 * 8.0 + sm2 * 20.0 * (1.0 - u * u)))
				draw_polyline(pts2, INK, 7.0, true)
		elif vis == "o":
			var ry3 := 14.0 + 22.0 * e
			draw_colored_polygon(ell_pts(mc + Vector2(0, 10 + ry3 * 0.5), 46.0, ry3), INK)
			draw_colored_polygon(ell_pts(mc + Vector2(0, 10 + ry3 * 0.95), 26.0, ry3 * 0.4), Color(0.82, 0.08, 0.08))
		else:
			draw_colored_polygon(ell_pts(mc + Vector2(0, 20), 22.0, 26.0), INK)
		if float(P.get("sweat", 0.0)) > 0.0:
			for i in 2:
				var d := Vector2(-205 - i * 22, -330 + i * 40 + fmod(frame * 4.0 + i * 20.0, 36.0))
				draw_colored_polygon(PackedVector2Array([d + Vector2(0, -22), d + Vector2(13, 0), d + Vector2(0, 12), d + Vector2(-13, 0)]), Color(0.75, 0.88, 0.98))

# critically-underdamped spring toward the acted pose, so gestures overshoot and settle instead of snapping
func smooth_pose(who: String, P: Dictionary) -> Dictionary:
	var C: Dictionary = CH[who]
	var defaults := {"wrist_l": C["wr_l"], "wrist_r": C["wr_r"], "lean": 0.0, "tilt": 0.0, "squash": 1.0, "bob": 0.0, "bend_l": 10.0, "bend_r": -10.0, "head_pop": 1.0}
	if not SM.has(who):
		SM[who] = {}
	var out := P.duplicate()
	for k in defaults:
		var tgt = P.get(k, defaults[k])
		if not SM[who].has(k):
			SM[who][k] = [tgt, tgt - tgt]
		var st: Array = SM[who][k]
		var vel = st[1] * 0.62 + (tgt - st[0]) * 0.2
		st[0] = st[0] + vel
		st[1] = vel
		out[k] = st[0]
	return out

func pose(who: String) -> Dictionary:
	return POSES[who].duplicate()
