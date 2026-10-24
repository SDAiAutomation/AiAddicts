extends Node2D
# rig_v1 (packaged from the Gate 3c prototype): reads ONLY a pack directory and a timeline file given on the command line.
# Usage: godot --path <this dir> main.tscn -- --pack=<dir> --timeline=<file>. Nothing else is read; no network, no user text is evaluated.
# NOTE: the shot layout (8 shots, per-line gestures) is the prototype story's; a contract-driven scene is a later PR.; cuts, subtitles, rings derive from timeline.json. Two original characters (Pip, Rosette), dialogue driven by measured audio (timeline.json), mouths from the audio envelope.
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
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(TIMELINE_PATH))
	if typeof(parsed) != TYPE_DICTIONARY or not parsed.has("lines") or not parsed.has("total") or not parsed.has("subs") or not parsed.has("rings"):
		_fail("invalid timeline file", 4)
		return
	TL = parsed
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
		draw_colored_polygon(cap, Color(1, 1, 1))
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

func overlays(t: float) -> void:
	draw_set_transform_matrix(Transform2D.IDENTITY)
	draw_texture_rect(vignette, Rect2(0, 0, W, H), false)
	var fl := 0.04 * sin(frame * 5.7) + 0.02 * sin(frame * 13.1)
	draw_rect(Rect2(0, 0, W, H), Color(0, 0, 0, clampf(0.05 + fl, 0.0, 1.0)) if fl > 0 else Color(1, 1, 1, clampf(-fl, 0.0, 1.0)))
	for i in 90:
		var k := frame * 131.0 + i * 17.0
		draw_rect(Rect2(fmod(k * 7.31, W), fmod(k * 3.77, H), 2, 2), Color(0, 0, 0, 0.16) if i % 3 else Color(1, 1, 1, 0.2))
	for s in TL["subs"]:
		if t >= s["start"] and t < s["end"]:
			draw_sub(String(s["text"]))
	var fade := minf(clampf(t / 0.3, 0.0, 1.0), clampf((float(TL["total"]) - t) / 0.7, 0.0, 1.0))
	if fade < 1.0:
		draw_rect(Rect2(0, 0, W, H), Color(0, 0, 0, 1.0 - fade))

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

func line_index(who_line_t: float) -> int:
	var L: Array = TL["lines"]
	var idx := -1
	for i in range(L.size()):
		if who_line_t >= float(L[i]["start"]) - 0.05:
			idx = i
	return idx

# Acting: one hand-built gesture set per spoken line, plus listening poses. All targets are native pixels of the character.
func act_raw(who: String, t: float) -> Dictionary:
	var C: Dictionary = CH[who]
	var L: Array = TL["lines"]
	var li := line_index(t)
	var speaking: bool = li >= 0 and L[li]["who"] == who and t < float(L[li]["end"]) + 0.15
	var e := smooth_env(who)
	var P := {}
	var tt: float = t - float(L[maxi(li, 0)]["start"])
	if speaking:
		P["bob"] = 3.0 * e
		P["squash"] = 1.0 - 0.04 * e
		if who == "ros":
			match li:
				0:  # accusing: right arm points at Pip, left hand on hip
					P["wrist_r"] = Vector2(1290, 780 + 18.0 * sin(tt * 7.0) * e); P["bend_r"] = -45.0
					P["wrist_l"] = Vector2(370, 1070); P["bend_l"] = 70.0
					P["lean"] = 0.07; P["tilt"] = 0.04 * sin(tt * 4.0) * e
				2:  # hand on chin, other hand points down at the clock
					P["wrist_l"] = Vector2(490, 760); P["bend_l"] = 55.0
					P["wrist_r"] = Vector2(1040, 1300); P["bend_r"] = -30.0
					P["tilt"] = -0.05
				_:  # indignant: fists shaking, torso pumping
					P["wrist_l"] = Vector2(215, 1010 + 26.0 * sin(tt * 13.0) * e); P["bend_l"] = 70.0
					P["wrist_r"] = Vector2(820, 1010 - 26.0 * sin(tt * 13.0) * e); P["bend_r"] = -70.0
					P["lean"] = 0.1 + 0.03 * sin(tt * 8.0) * e
					P["squash"] = 1.0 - 0.07 * absf(sin(tt * 6.5)) * e
					P["tilt"] = 0.06 * sin(tt * 9.0)
		else:
			match li:
				1:  # defending: palms up, shaking
					P["wrist_l"] = Vector2(300 + 26.0 * sin(tt * 9.0) * e, 640); P["bend_l"] = 35.0
					P["wrist_r"] = Vector2(725 - 26.0 * sin(tt * 9.0) * e, 640); P["bend_r"] = -35.0
					P["lean"] = -0.05; P["tilt"] = 0.06 * sin(tt * 5.0) * e
				3:  # wringing hands
					P["wrist_l"] = Vector2(470 + 28.0 * sin(tt * 10.0), 885); P["bend_l"] = 30.0
					P["wrist_r"] = Vector2(555 - 28.0 * sin(tt * 10.0), 870); P["bend_r"] = -30.0
					P["lean"] = 0.1
				_:  # realising: hand to forehead, then both hands clutch the head
					var k := ease_io(seg(tt, 1.0, 1.5))
					P["wrist_l"] = Vector2(300, 930).lerp(Vector2(380, 500), k); P["bend_l"] = 40.0
					P["wrist_r"] = Vector2(725, 930).lerp(Vector2(640, 490), k)
					P["bend_r"] = -40.0
					P["lean"] = -0.08 * k
	else:
		# listening: small reactions that echo the other character's line
		if who == "pip":
			P["wrist_l"] = Vector2(440, 905); P["bend_l"] = 30.0
			P["wrist_r"] = Vector2(585, 895); P["bend_r"] = -30.0
			P["lean"] = -0.04
		else:
			P["wrist_l"] = Vector2(250, 990); P["bend_l"] = 45.0
			P["wrist_r"] = Vector2(785, 990); P["bend_r"] = -45.0
	return P

func act(who: String, t: float) -> Dictionary:
	var P := act_raw(who, t)
	var L: Array = TL["lines"]
	var li := line_index(t)
	var cur: String = L[li]["who"] if li >= 0 else ""
	var tt: float = t - float(L[maxi(li, 0)]["start"])
	var mood := "neutral"
	if who == "ros":
		if cur == "ros":
			mood = "puzzled" if li == 2 else "angry"
		else:
			mood = "puzzled" if li in [1, 3] else ("surprise" if li == 5 else "neutral")
	else:
		if cur == "pip":
			mood = "worry" if li == 1 else ("joy" if li == 3 else ("surprise" if tt < 1.4 else "panic"))
		else:
			mood = "surprise" if (li == 0 and tt < 1.2) else "worry"
	P["mood"] = mood
	P["e"] = smooth_env(who)
	return smooth_pose(who, P)

func merge_into(dst: Dictionary, src: Dictionary) -> void:
	for k in src:
		dst[k] = src[k]

# ---------- shots (cut points derive from the measured audio) ----------
func clock_x_at(t: float) -> float:
	var L: Array = TL["lines"]
	var x := lerpf(320.0, 215.0, ease_io(seg(t, L[2]["start"] + 0.35, L[2]["start"] + 1.3)))
	return x

func ring_at(t: float) -> float:
	for r in TL["rings"]:
		if t >= r[0] and t < r[1]:
			return minf(1.0, minf((t - r[0]) * 6.0, (r[1] - t) * 6.0))
	return 0.0

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

func _draw() -> void:
	draw_rect(Rect2(0, 0, W, H), Color.BLACK)
	var t := frame / FPS
	POSES = {"ros": act("ros", t), "pip": act("pip", t)}
	var L: Array = TL["lines"]
	var cuts: Array = [0.0]
	for i in range(1, L.size()):
		cuts.append((float(L[i - 1]["end"]) + float(L[i]["start"])) * 0.5)
	var run0: float = float(L[5]["end"]) - 0.3
	var total: float = float(TL["total"])
	cuts.append(run0 + 0.25)           # 6: alley chase
	cuts.append(total - 1.7)           # 7: cafe
	cuts.append(total)
	var idx := 0
	for i in range(cuts.size() - 1):
		if t >= cuts[i]:
			idx = i
	var a: float = cuts[idx]
	var b: float = cuts[idx + 1]
	match idx:
		0: shot_wide(t, a, b, 0)
		1: shot_close("pip", t, a, b)
		2: shot_wide(t, a, b, 2)
		3: shot_close("pip", t, a, b)
		4: shot_close("ros", t, a, b)
		5: shot_wide(t, a, b, 5)
		6: shot_chase(t, a, b)
		_: shot_cafe(t, a, b)
	overlays(t)

func shot_wide(t: float, a: float, b: float, k: int) -> void:
	var u := seg(t, a, b)
	var zoom := lerpf(1.0, 1.08, ease_io(u))
	var ctr := Vector2(320, 560)
	if k == 2:
		zoom = lerpf(1.55, 1.45, ease_io(u)); ctr = Vector2(250, 600)
	elif k == 5:
		zoom = lerpf(1.2, 1.5, ease_io(u)); ctr = Vector2(380, 560)
	zoom *= 1.0 + 0.012 * maxf(smooth_env("ros"), smooth_env("pip"))
	var cam := cam_xf(zoom, ctr)
	draw_world(cam, t, "bg_shop", ring_at(t), clock_x_at(t))
	var R := pose("ros")
	R["cam"] = cam; R["pos"] = Vector2(165, hip_y("ros")); R["flip"] = 1.0
	draw_puppet("ros", R)
	var Q := pose("pip")
	Q["cam"] = cam; Q["flip"] = -1.0
	var enter := ease_io(seg(t, 0.0, 0.6)) if k == 0 else 1.0
	Q["pos"] = Vector2(lerpf(580.0, 465.0, enter), hip_y("pip"))
	if enter < 1.0:
		merge_into(Q, walk_pose(CH["pip"], t * 11.0, 1.0))
		Q["head_key"] = "c"
	elif k != 5:
		Q["head_key"] = "worry"
	if k == 5:
		var L: Array = TL["lines"]
		var tt: float = t - float(L[5]["start"])
		if tt > 1.55:
			var hu := seg(tt, 1.55, 2.75)
			Q["hat_world"] = Vector2(465.0 + 18.0 * hu, hip_y("pip") - 300.0 - 260.0 * sin(PI * hu * 0.5) + 360.0 * hu * hu)
			Q["hat_rot"] = hu * 8.0
			Q["hat_off"] = true
		var run0: float = float(L[5]["end"]) - 0.3
		var ant := ease_io(seg(t, run0 - 0.35, run0))
		Q["squash"] = 1.0 - 0.13 * ant
		Q["lean"] = -0.15 * ant
	draw_puppet("pip", Q)

func shot_close(who: String, t: float, a: float, b: float) -> void:
	var u := seg(t, a, b)
	var punch := ease_back(seg(t, a, a + 0.25))
	var is_pip := who == "pip"
	var e := smooth_env(who)
	var zoom := (lerpf(2.2, 2.7, ease_io(u)) if is_pip else lerpf(1.8, 2.25, ease_io(u))) * (0.95 + 0.05 * punch) * (1.0 + 0.015 * e)
	var hp := Vector2(465 if is_pip else 165, hip_y(who))
	var cam := cam_xf(zoom, Vector2(hp.x - (10.0 if is_pip else -10.0), hp.y - (170.0 if is_pip else 215.0)))
	draw_world(cam, t, "bg_shop", ring_at(t), clock_x_at(t))
	var P := pose(who)
	P["cam"] = cam; P["pos"] = hp; P["flip"] = -1.0 if is_pip else 1.0
	P["head_pop"] = 1.0 + 0.05 * e
	if is_pip:
		P["head_key"] = mouth_of("pip") if e > 0.0 else "worry"
	draw_puppet(who, P)

func shot_chase(t: float, a: float, b: float) -> void:
	var u := seg(t, a, b)
	var cam := cam_xf(1.0, Vector2(320, 560))
	var px := lerpf(-90.0, 720.0, ease_io(u))
	var cx := lerpf(-250.0, 560.0, ease_io(clampf(u * 1.08 - 0.08, 0.0, 1.0)))
	draw_world(cam, t, "bg_alley", 1.0, cx, 1.0)
	var Q := {"cam": cam, "flip": 1.0, "pos": Vector2(px, hip_y("pip")), "lean": 0.22, "head_key": "o", "hat_off": true}
	merge_into(Q, walk_pose(CH["pip"], t * 17.0, 1.6))
	Q["sweat"] = 1.0
	Q["mood"] = "panic"
	draw_puppet("pip", Q)

func shot_cafe(t: float, a: float, b: float) -> void:
	var u := seg(t, a, b)
	var cam := cam_xf(lerpf(1.1, 1.0, u), Vector2(320, 560))
	var settle := ease_io(seg(t, a, a + 0.6))
	draw_world(cam, t, "bg_cafe", 1.0 - 0.8 * ease_io(seg(t, a + 0.9, a + 1.4)), lerpf(60.0, 330.0, ease_io(seg(t, a, a + 0.7))), 1.0 - settle)
	var Q := {"cam": cam, "flip": -1.0, "pos": Vector2(lerpf(-60.0, 470.0, ease_io(seg(t, a - 0.1, a + 0.35))), hip_y("pip")), "hat_off": true, "head_key": "o"}
	var w := seg(t, a - 0.1, a + 0.35)
	Q["mood"] = "panic" if w < 1.0 else "worry"
	Q["sweat"] = 1.0
	if w < 1.0:
		merge_into(Q, walk_pose(CH["pip"], t * 17.0, 1.4))
		Q["flip"] = 1.0
		Q["lean"] = 0.2
	else:
		var pant := sin(t * 14.0)
		Q["bob"] = 2.5 * pant
		Q["wrist_l"] = Vector2(300, 930 + 20.0 * pant); Q["wrist_r"] = Vector2(725, 930 + 20.0 * pant)
		Q["head_key"] = "worry"
		Q["lean"] = 0.12
	draw_puppet("pip", Q)
	var R := {"cam": cam, "flip": 1.0, "pos": Vector2(lerpf(-120.0, 150.0, ease_io(seg(t, a + 0.6, a + 1.2))), hip_y("ros")), "head_key": "r"}
	R["mood"] = "angry"
	if seg(t, a + 0.6, a + 1.2) < 1.0:
		merge_into(R, walk_pose(CH["ros"], t * 12.0, 0.9))
	else:
		R["wrist_l"] = Vector2(300, 1080); R["bend_l"] = 80.0
		R["wrist_r"] = Vector2(735, 1080); R["bend_r"] = -80.0
		R["head_key"] = "c"
		R["lean"] = 0.06
	draw_puppet("ros", R)

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
