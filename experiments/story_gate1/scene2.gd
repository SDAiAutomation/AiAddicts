extends Node2D
# Gate 1B: same animation chain as scene.gd, but the artwork is OpenAI-generated and cut into rig parts (sprites/*.png).
# Rubber-hose arms and legs are still drawn as ink lines; head, torso, gloves, shoes, hat, clock and background are sprites.

const FPS := 24.0
const W := 540.0
const H := 960.0
const K := 0.28              # sprite native px -> world px
const FEET_Y := 800.0
const SHOTS := [0.0, 2.5, 4.3, 7.0]
const INK := Color(0.03, 0.03, 0.04)
# native anchor points (pixels of the 1024x1536 source character)
const HIP := Vector2(512, 985)
const NECK := Vector2(512, 636)
const SH_L := Vector2(405, 705)
const SH_R := Vector2(620, 705)
const HIP_L := Vector2(455, 975)
const HIP_R := Vector2(572, 975)
const WR_L := Vector2(225, 880)
const WR_R := Vector2(795, 880)
const AN_L := Vector2(445, 1240)
const AN_R := Vector2(587, 1240)

var frame := 0
var T := {}
var vignette: GradientTexture2D

func _ready() -> void:
	for n in ["hat", "torso", "glove_l", "glove_r", "shoe_l", "shoe_r", "head_neutral", "head_talk", "head_worried", "clock", "bg_alley"]:
		var img := Image.load_from_file("res://sprites/%s.png" % n)
		T[n] = ImageTexture.create_from_image(img)
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
	if frame / FPS >= SHOTS[3]:
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
	# keep the view inside the 640x960 plate
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

# draw a sprite: pivot is a point in texture pixels, placed at world position wp
func spr(cam: Transform2D, tex: Texture2D, pivot: Vector2, wp: Vector2, ang: float, sx: float, sy: float, seed_: float, alpha := 1.0) -> void:
	var j := boil(seed_, 0.55)
	var a := ang + sin(floorf(frame / 2.0) * 3.1 + seed_) * 0.006
	draw_set_transform_matrix(cam * Transform2D(a, Vector2(sx, sy), 0.0, wp + j))
	draw_texture(tex, -pivot, Color(1, 1, 1, alpha))

func hose(cam: Transform2D, a: Vector2, b: Vector2, bend: float, w: float, seed_: float) -> void:
	draw_set_transform_matrix(cam)
	var pts := bez(a, b, bend)
	for i in pts.size():
		pts[i] += boil(seed_ + i, 0.35)
	draw_polyline(pts, INK, w, true)
	draw_circle(pts[0], w * 0.5, INK)
	draw_circle(pts[pts.size() - 1], w * 0.5, INK)

# ---------- character ----------
func draw_pip(P: Dictionary) -> void:
	var cam: Transform2D = P["cam"]
	var pos: Vector2 = P["pos"]              # hip, world
	var flip: float = P.get("flip", 1.0)
	var lean: float = P.get("lean", 0.0)
	var rot: float = lean * flip
	var sqx: float = 1.0 / P.get("squash", 1.0)
	var sqy: float = P.get("squash", 1.0)
	var hipw := pos + Vector2(0, -P.get("bob", 0.0))
	var rw := func(n: Vector2) -> Vector2:   # native point on the upper body -> world
		return hipw + (Vector2((n.x - HIP.x) * flip * sqx, (n.y - HIP.y) * sqy) * K).rotated(rot)
	var fw := func(n: Vector2) -> Vector2:   # native point on the lower body (not rotated by lean)
		return hipw + Vector2((n.x - HIP.x) * flip, (n.y - HIP.y) * sqy) * K
	var ground: float = P.get("ground", FEET_Y)
	# shadow
	draw_set_transform_matrix(cam)
	var sh := PackedVector2Array()
	var sw: float = 78.0
	for i in 24:
		var an := TAU * i / 24.0
		sh.append(Vector2(pos.x + cos(an) * sw, ground + 4 + sin(an) * 10))
	draw_colored_polygon(sh, Color(0, 0, 0, 0.28))
	# legs + shoes
	var al: Vector2 = P.get("ankle_l", AN_L)
	var ar: Vector2 = P.get("ankle_r", AN_R)
	hose(cam, fw.call(HIP_L), fw.call(al), -6.0 * flip, 55.0 * K, 1.0)
	hose(cam, fw.call(HIP_R), fw.call(ar), -6.0 * flip, 55.0 * K, 2.0)
	var fa: float = P.get("foot_ang", 0.0) * flip
	spr(cam, T["shoe_l"], Vector2(210, 8), fw.call(al), fa, K * flip, K * sqy, 3.0)
	spr(cam, T["shoe_r"], Vector2(77, 8), fw.call(ar), fa, K * flip, K * sqy, 4.0)
	# arms (behind torso)
	var wl: Vector2 = P.get("wrist_l", WR_L)
	var wr: Vector2 = P.get("wrist_r", WR_R)
	var bl: float = P.get("bend_l", 10.0)
	var br: float = P.get("bend_r", -10.0)
	hose(cam, rw.call(SH_L), rw.call(wl), bl, 58.0 * K, 5.0)
	hose(cam, rw.call(SH_R), rw.call(wr), br, 58.0 * K, 6.0)
	# torso
	spr(cam, T["torso"], HIP - Vector2(385, 636), hipw, rot, K * flip * sqx, K * sqy, 7.0)
	# head
	var neck_w: Vector2 = rw.call(NECK)
	var pop: float = P.get("head_pop", 1.0)
	var hang: float = rot + P.get("tilt", 0.0) * flip
	# dome of the head (the hat hides it in the source art): white cap + ink arc, drawn under the head sprite
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
	spr(cam, T["head_" + P.get("head", "neutral")], NECK - Vector2(265, 262), neck_w, hang, K * flip * pop, K * pop, 8.0)
	# hat (on the head unless it has its own world transform)
	if P.has("hat_world"):
		var hw: Vector2 = P["hat_world"]
		spr(cam, T["hat"], Vector2(184, 183), hw, P.get("hat_rot", 0.0), K * flip, K, 9.0)
	else:
		var top := neck_w + Vector2(0, -(NECK.y - 238.0) * K * pop).rotated(hang)
		spr(cam, T["hat"], Vector2(184, 183), top + Vector2(0, P.get("hat_lift", 0.0)).rotated(hang), hang, K * flip, K, 9.0)
	# gloves on top
	for side in [0, 1]:
		var tgt: Vector2 = rw.call(wl if side == 0 else wr)
		var origin: Vector2 = rw.call(SH_L if side == 0 else SH_R)
		var bend: float = bl if side == 0 else br
		var pts := bez(origin, tgt, bend)
		var dir: Vector2 = (pts[pts.size() - 1] - pts[pts.size() - 4]).normalized()
		var ga := dir.angle() - PI * 0.5
		var pr: Vector2 = Vector2(150, 13) if side == 0 else Vector2(95, 13)
		spr(cam, T["glove_l" if side == 0 else "glove_r"], pr, tgt, ga + P.get("glove_ang", 0.0), K * flip, K, 10.0 + side)
	draw_set_transform_matrix(Transform2D.IDENTITY)

# ---------- world ----------
func draw_world(cam: Transform2D, t: float, ring: float) -> void:
	draw_set_transform_matrix(cam)
	draw_texture(T["bg_alley"], Vector2.ZERO)
	# smoke puffs from the chimneys (code, animated)
	for ci in 2:
		var cx := 560.0 + ci * 48.0
		for p in 5:
			var u := fmod(t * 0.3 + p * 0.2 + ci * 0.37, 1.0)
			var pc := Vector2(cx + u * 70.0 + sin(u * 8.0) * 8.0, 280.0 - ci * 40.0 - u * 150.0)
			draw_circle(pc + boil(p + ci * 9, 1.0), 12 + u * 26, Color(0.82, 0.82, 0.80, 0.55 * (1.0 - u)))
	# clock prop (generated sprite) on the floor, hopping and ringing
	var base := Vector2(470, FEET_Y + 6)
	var hop: float = absf(sin(frame * 0.9)) * 14.0 * ring
	var shake := sin(frame * 2.7) * 0.07 * ring
	var kc := 0.25 * (1.0 + 0.04 * ring * sin(frame * 1.7))
	spr(cam, T["clock"], Vector2(328, 780), base + Vector2(0, -hop), shake, kc, kc, 20.0)
	if ring > 0.0:
		draw_set_transform_matrix(cam)
		for k in 3:
			var rr := 105.0 + k * 16.0 + fmod(frame * 2.5, 16.0)
			draw_arc(base + Vector2(0, -105), rr, -2.45, -0.7, 10, INK, 3.0, true)
			draw_arc(base + Vector2(0, -105), rr, -2.45 + 3.14, -0.7 + 3.14 - 0.6, 10, INK, 3.0, true)
	draw_set_transform_matrix(Transform2D.IDENTITY)

func draw_foreground(cam: Transform2D) -> void:
	draw_set_transform_matrix(cam)
	draw_rect(Rect2(-30, 770, 120, 260), Color(0.06, 0.06, 0.07, 0.96))
	draw_line(Vector2(-30, 815), Vector2(90, 815), Color(0.3, 0.3, 0.3), 3.0)
	draw_set_transform_matrix(Transform2D.IDENTITY)

func overlays() -> void:
	draw_set_transform_matrix(Transform2D.IDENTITY)
	draw_texture_rect(vignette, Rect2(0, 0, W, H), false)
	var fl := 0.04 * sin(frame * 5.7) + 0.02 * sin(frame * 13.1)
	draw_rect(Rect2(0, 0, W, H), Color(0, 0, 0, clampf(0.05 + fl, 0.0, 1.0)) if fl > 0 else Color(1, 1, 1, clampf(-fl, 0.0, 1.0)))
	for i in 90:
		var k := frame * 131.0 + i * 17.0
		draw_rect(Rect2(fmod(k * 7.31, W), fmod(k * 3.77, H), 2, 2), Color(0, 0, 0, 0.16) if i % 3 else Color(1, 1, 1, 0.2))
	for i in 3:
		if fmod(frame * 0.37 + i * 3.1, 3.0) < 1.0:
			var x := fmod(frame * 53.0 + i * 211.0, W)
			draw_line(Vector2(x, 0), Vector2(x + sin(frame + i), H), Color(1, 1, 1, 0.12), 1.0)

# ---------- poses ----------
func walk_pose(ph: float, amp: float) -> Dictionary:
	var a := sin(ph)
	var b := sin(ph + PI)
	return {
		"ankle_l": Vector2(AN_L.x + a * 100.0 * amp, AN_L.y - maxf(0.0, cos(ph)) * 85.0 * amp),
		"ankle_r": Vector2(AN_R.x + b * 100.0 * amp, AN_R.y - maxf(0.0, cos(ph + PI)) * 85.0 * amp),
		"wrist_l": Vector2(WR_L.x - b * 45.0 * amp, WR_L.y - absf(b) * 30.0 * amp),
		"wrist_r": Vector2(WR_R.x + a * 45.0 * amp, WR_R.y - absf(a) * 30.0 * amp),
		"bob": absf(cos(ph)) * 4.0 * amp,
		"foot_ang": 0.12 * cos(ph) * amp,
	}

func _draw() -> void:
	draw_rect(Rect2(0, 0, W, H), Color.BLACK)
	var t := frame / FPS
	if t < SHOTS[1]:
		shot_a(t / SHOTS[1], t)
	elif t < SHOTS[2]:
		shot_b((t - SHOTS[1]) / (SHOTS[2] - SHOTS[1]), t)
	else:
		shot_c((t - SHOTS[2]) / (SHOTS[3] - SHOTS[2]), t)
	overlays()

func hipy() -> float:
	return FEET_Y - (1430.0 - HIP.y) * K

func shot_a(u: float, t: float) -> void:
	var zoom := lerpf(1.0, 1.12, ease_io(u))
	var px := lerpf(-90.0, 235.0, ease_io(seg(u, 0.0, 0.85)))
	var c := Vector2(lerpf(300.0, 330.0, u), 560.0)
	var cam := cam_xf(zoom, c)
	draw_world(cam, t, 0.0)
	var stop := seg(u, 0.78, 1.0)
	var P := walk_pose(t * 11.0, 1.0 - stop)
	P["pos"] = Vector2(px, hipy())
	P["cam"] = cam
	P["lean"] = 0.08 * (1.0 - stop)
	P["head"] = "neutral"
	P["head_pop"] = 1.0 + 0.06 * ease_back(seg(u, 0.9, 1.0))
	draw_pip(P)
	draw_foreground(cam_xf(zoom, c, 1.35))

func shot_b(u: float, t: float) -> void:
	# close-up: surprise, then worry
	var punch := ease_back(seg(u, 0.0, 0.18))
	var zoom := lerpf(2.4, 3.0, ease_io(u)) * (0.92 + 0.08 * punch)
	var hp := Vector2(235, hipy())
	var shake := Vector2(sin(frame * 3.1), cos(frame * 2.3)) * 2.0 * (1.0 - seg(u, 0.2, 0.6))
	var c := Vector2(hp.x + 10.0, hp.y - 170.0) + shake
	var cam := cam_xf(zoom, c)
	draw_world(cam, t, 0.0)
	var worry := ease_io(seg(u, 0.5, 0.9))
	var surprise := ease_back(seg(u, 0.0, 0.2))
	var P := {}
	P["pos"] = hp
	P["cam"] = cam
	P["head"] = "talk" if worry < 0.6 else "worried"
	P["head_pop"] = 1.0 + 0.16 * surprise * (1.0 - worry) + 0.03 * sin(frame * 0.8)
	P["tilt"] = 0.07 * sin(frame * 0.9) * (1.0 - seg(u, 0.3, 0.7)) - 0.08 * worry
	P["hat_lift"] = -26.0 * surprise * (1.0 - worry) / 1.0
	P["squash"] = 1.0 + 0.06 * (1.0 - surprise)
	P["wrist_l"] = WR_L + Vector2(-20, -120) * worry
	P["wrist_r"] = WR_R + Vector2(20, -120) * worry
	draw_pip(P)

func shot_c(u: float, t: float) -> void:
	var zoom := lerpf(1.45, 1.0, ease_io(u))
	var c := Vector2(lerpf(360.0, 320.0, u), 600.0)
	var ring := ease_io(seg(u, 0.08, 0.2))
	var cam := cam_xf(zoom, c)
	draw_world(cam, t, ring)
	var react := ease_back(seg(u, 0.1, 0.3))
	var run := seg(u, 0.62, 1.0)
	var px := 235.0 - 18.0 * react * (1.0 - run) - 420.0 * ease_io(run)
	var jump := 0.0
	if u > 0.1 and u < 0.36:
		jump = 62.0 * sin(PI * seg(u, 0.1, 0.36))
	var P := {}
	P["cam"] = cam
	P["head"] = "talk"
	P["head_pop"] = 1.0 + 0.1 * react * (1.0 - run)
	var hat_u := seg(u, 0.12, 0.75)
	if hat_u > 0.0:
		P["hat_world"] = Vector2(px + 10.0 - 40.0 * hat_u, hipy() - 300.0 - 230.0 * sin(PI * hat_u * 0.5) + 330.0 * hat_u * hat_u)
		P["hat_rot"] = hat_u * 9.0
	if run <= 0.0:
		P["pos"] = Vector2(px, hipy())
		P["ground"] = FEET_Y
		P["bob"] = jump
		P["wrist_l"] = Vector2(130, 600) + Vector2(0, -40) * react
		P["wrist_r"] = Vector2(1250, 600 - 70 * react)
		P["bend_r"] = -30.0
		P["ankle_l"] = Vector2(AN_L.x - 15, AN_L.y - jump * 2.5)
		P["ankle_r"] = Vector2(AN_R.x + 15, AN_R.y - jump * 2.5)
		P["squash"] = 1.0 - 0.07 * sin(PI * seg(u, 0.1, 0.36))
		P["tilt"] = -0.1 * react
		P["flip"] = 1.0
	else:
		var w := walk_pose(t * 17.0, 1.5)
		for k in w:
			P[k] = w[k]
		P["pos"] = Vector2(px, hipy())
		P["flip"] = -1.0
		P["lean"] = 0.2
		P["wrist_l"] = Vector2(130, 520 - 40 * sin(t * 17.0))
		P["wrist_r"] = Vector2(900, 560 + 40 * sin(t * 17.0))
	draw_pip(P)
	draw_foreground(cam_xf(zoom, c, 1.35))
