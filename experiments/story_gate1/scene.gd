extends Node2D
# Gate 1 spike: original character "Pip", 1930s rubber-hose style, drawn from code by time.
# One deterministic function of t -> frame, so renders are reproducible (no physics, no randomness beyond hashed noise).

const FPS := 24.0
const W := 540.0
const H := 960.0
const GROUND := 700.0
const S := 2.0 # character scale in the world
const INK := Color(0.04, 0.04, 0.05)
const PAPER := Color(0.93, 0.92, 0.88)
const RED := Color(0.82, 0.08, 0.08)
const SHOTS := [0.0, 2.5, 4.3, 7.0] # A wide, B close-up, C medium

var frame := 0
var vignette: GradientTexture2D

func _ready() -> void:
	var g := Gradient.new()
	g.offsets = PackedFloat32Array([0.45, 1.0])
	g.colors = PackedColorArray([Color(0, 0, 0, 0), Color(0, 0, 0, 0.62)])
	vignette = GradientTexture2D.new()
	vignette.gradient = g
	vignette.fill = GradientTexture2D.FILL_RADIAL
	vignette.fill_from = Vector2(0.5, 0.5)
	vignette.fill_to = Vector2(1.0, 0.85)
	vignette.width = 270
	vignette.height = 480

func _process(_d: float) -> void:
	var t := frame / FPS
	if t >= SHOTS[3]:
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
	var c1 := 1.9
	var c3 := c1 + 1.0
	return 1.0 + c3 * pow(x - 1.0, 3.0) + c1 * pow(x - 1.0, 2.0)

func seg(t: float, a: float, b: float) -> float:
	return clampf((t - a) / (b - a), 0.0, 1.0)

func boil(i: float, amp := 1.0) -> Vector2:
	# film "boil": outline jitter changing 12 times per second
	var k := floorf(frame / 2.0)
	return Vector2(sin(k * 7.13 + i * 3.71), cos(k * 5.31 + i * 2.17)) * amp

func xf(zoom: float, cam_c: Vector2, par: float) -> Transform2D:
	var c := cam_c * par + Vector2(W, H) * 0.5 * (1.0 - par)
	return Transform2D(0.0, Vector2(zoom, zoom), 0.0, Vector2(W, H) * 0.5 - c * zoom)

func bez(a: Vector2, b: Vector2, bend: float, n := 14) -> PackedVector2Array:
	var d := b - a
	var perp := Vector2(-d.y, d.x).normalized()
	var c := (a + b) * 0.5 + perp * bend
	var pts := PackedVector2Array()
	for i in n + 1:
		var u := float(i) / n
		pts.append(a.lerp(c, u).lerp(c.lerp(b, u), u))
	return pts

func ell(c: Vector2, rx: float, ry: float, rot := 0.0, n := 28, jit := 0.0, seed_ := 0.0) -> PackedVector2Array:
	var pts := PackedVector2Array()
	for i in n:
		var a := TAU * i / n
		var p := Vector2(cos(a) * rx, sin(a) * ry).rotated(rot) + c
		if jit > 0.0:
			p += boil(seed_ + i, jit)
		pts.append(p)
	return pts

func blob(c: Vector2, rx: float, ry: float, fill: Color, rot := 0.0, outline := 0.0, seed_ := 0.0) -> void:
	var pts := ell(c, rx, ry, rot, 28, minf(0.45, minf(rx, ry) * 0.08), seed_)
	draw_colored_polygon(pts, fill)
	if outline > 0.0:
		var closed := pts.duplicate()
		closed.append(pts[0])
		draw_polyline(closed, INK, outline, true)

func hose(a: Vector2, b: Vector2, bend: float, w: float, col := INK, seed_ := 0.0) -> void:
	var pts := bez(a, b, bend)
	for i in pts.size():
		pts[i] += boil(seed_ + i, 0.5)
	draw_polyline(pts, col, w, true)
	draw_circle(pts[0], w * 0.5, col)
	draw_circle(pts[pts.size() - 1], w * 0.5, col)

# ---------- character ----------
func glove(p: Vector2, ang: float, pointing := false) -> void:
	blob(p, 11, 10, PAPER, ang, 2.2, p.x)
	if pointing:
		hose(p, p + Vector2(15, -2).rotated(ang), 0.0, 6.0, PAPER, 1.0)
		draw_polyline(bez(p, p + Vector2(15, -2).rotated(ang), 0.0, 4), INK, 1.0, true)
	else:
		blob(p + Vector2(-7, -8).rotated(ang), 4.5, 4, PAPER, 0.0, 1.6, p.y)

func draw_pip(P: Dictionary) -> void:
	# P: pos (hip), s, flip, bob, squash, lean, hand_l, hand_r (local), foot_l, foot_r (local),
	#    brow, eye, pup, mouth, mouth_open, look, hat (Vector2 offset or null), sweat, tilt
	var s: float = P.get("s", 1.0)
	var flip: float = P.get("flip", 1.0)
	var sq: float = P.get("squash", 1.0)
	var base := Transform2D(0.0, Vector2(s * flip / sq, s * sq), 0.0, P["pos"])
	var cam: Transform2D = P["cam"]
	draw_set_transform_matrix(cam * base)
	var bob: float = P.get("bob", 0.0)
	var lean: float = P.get("lean", 0.0)
	var hip := Vector2(0, bob)
	var chest := Vector2(lean * 0.6, -44 + bob)
	var head_c := Vector2(lean, -98 + bob)
	# shadow
	draw_colored_polygon(ell(Vector2(0, 8 - bob * 0.0), 46 - bob * 0.8, 9, 0.0, 20), Color(0, 0, 0, 0.25))
	# legs
	var fl: Vector2 = P.get("foot_l", Vector2(-16, 0))
	var fr: Vector2 = P.get("foot_r", Vector2(16, 0))
	hose(hip + Vector2(-10, -6), fl, -10, 11, INK, 1.0)
	hose(hip + Vector2(10, -6), fr, -10, 11, INK, 2.0)
	blob(fl + Vector2(5, -2), 17, 8, INK, 0.0, 0.0, 3.0)
	blob(fr + Vector2(5, -2), 17, 8, INK, 0.0, 0.0, 4.0)
	draw_rect(Rect2(fl + Vector2(-4, -14), Vector2(10, 5)), PAPER)
	draw_rect(Rect2(fr + Vector2(-4, -14), Vector2(10, 5)), PAPER)
	# back arm
	var hl: Vector2 = P.get("hand_l", Vector2(-38, -30))
	var hr: Vector2 = P.get("hand_r", Vector2(38, -30))
	hose(chest + Vector2(-18, -6), hl, 14, 11, INK, 5.0)
	glove(hl, 0.0)
	# torso (pear) + belly
	blob(Vector2(lean * 0.3, -26 + bob), 24, 31, INK, 0.0, 0.0, 7.0)
	blob(chest, 21, 21, INK, 0.0, 0.0, 8.0)
	# bow tie (red accent)
	var bt := chest + Vector2(0, -16)
	draw_colored_polygon(PackedVector2Array([bt, bt + Vector2(-17, -9), bt + Vector2(-17, 9)]), RED)
	draw_colored_polygon(PackedVector2Array([bt, bt + Vector2(17, -9), bt + Vector2(17, 9)]), RED)
	draw_circle(bt, 4.5, Color(0.55, 0.04, 0.04))
	# front arm
	hose(chest + Vector2(18, -6), hr, -14, 11, INK, 6.0)
	glove(hr, 0.0, P.get("point", false))
	# head
	var tilt: float = P.get("tilt", 0.0)
	draw_set_transform_matrix(cam * base * Transform2D(tilt, Vector2.ONE, 0.0, head_c))
	var hc := Vector2.ZERO
	# curl of hair
	draw_polyline(PackedVector2Array([Vector2(0, -34), Vector2(3, -46), Vector2(-5, -54), Vector2(4, -60), Vector2(10, -54)]), INK, 4.0, true)
	# white bean head, ears
	for sx in [-1.0, 1.0]:
		blob(Vector2(sx * 39, 4), 8, 11, PAPER, 0.0, 2.6, 30.0 + sx)
	blob(hc, 38, 41, PAPER, 0.0, 3.2, 9.0)
	# eyes inside round spectacles
	var eye: float = P.get("eye", 1.0)
	var pup: float = P.get("pup", 1.0)
	var look: Vector2 = P.get("look", Vector2.ZERO)
	for sx in [-1.0, 1.0]:
		var ec := Vector2(sx * 17, -6)
		var gr := 14.0 + 3.0 * (eye - 1.0)
		blob(ec, gr, gr, Color(1, 1, 1), 0.0, 0.0, 11.0 + sx)
		var pc := ec + Vector2(look.x, look.y) * (gr * 0.45)
		draw_circle(pc, 5.5 * pup + 1.0, INK)
		draw_circle(pc + Vector2(-1.8, -2.2) * pup, 1.6, PAPER)
		var ring := ell(ec, gr, gr, 0.0, 26)
		ring.append(ring[0])
		draw_polyline(ring, INK, 3.2, true)
	draw_line(Vector2(-4, -8), Vector2(4, -8), INK, 3.0, true)
	# brows: black strokes above the glasses; brow > 0 raised, brow < 0 worried (inner ends up)
	var brow: float = P.get("brow", 0.0)
	var raise := maxf(brow, 0.0) * 6.0
	var worry := maxf(-brow, 0.0)
	for sx in [-1.0, 1.0]:
		var by := -30.0 - 3.0 * (eye - 1.0) * 4.0
		var a := Vector2(sx * 28, by - raise + worry * 4.0)
		var b := Vector2(sx * 8, by - raise - worry * 6.0)
		hose(a, b, -3.0, 4.6, INK, 12.0 + sx)
	# nose + moustache (original silhouette: round nose, two tufts)
	blob(Vector2(0, 10), 10, 8.5, PAPER, 0.0, 2.6, 13.0)
	for sx in [-1.0, 1.0]:
		blob(Vector2(sx * 11, 22), 11, 4.6, INK, sx * 0.25, 0.0, 16.0 + sx)
	# mouth
	var m: String = P.get("mouth", "smile")
	var mo: float = P.get("mouth_open", 0.0)
	var mc := Vector2(0, 31)
	match m:
		"smile":
			draw_polyline(bez(mc + Vector2(-13, -2), mc + Vector2(13, -2), 9.0, 10), INK, 3.0, true)
		"flat":
			draw_line(mc + Vector2(-10, 2), mc + Vector2(10, 2), INK, 3.0, true)
		"frown":
			draw_polyline(bez(mc + Vector2(-12, 6), mc + Vector2(12, 6), -9.0, 10), INK, 3.0, true)
		"open":
			var mp := ell(mc + Vector2(0, 2 + mo * 2), 7 + mo * 4, 2 + mo * 6, 0.0, 22)
			draw_colored_polygon(mp, INK)
			draw_colored_polygon(ell(mc + Vector2(0, 5 + mo * 5), 4 + mo * 2, 1.5 + mo * 2.5, 0.0, 14), RED)
		"talk":
			var mp2 := ell(mc + Vector2(0, 3), 9, 2 + 8 * mo, 0.0, 18)
			draw_colored_polygon(mp2, INK)
	# sweat drops
	var sw: float = P.get("sweat", 0.0)
	if sw > 0.0:
		for i in 3:
			var d := Vector2(-48 - i * 6, -30 + i * 22 + fmod(frame * 2.0 + i * 11.0, 16.0) * sw)
			draw_colored_polygon(PackedVector2Array([d + Vector2(0, -9), d + Vector2(5, 0), d + Vector2(0, 5), d + Vector2(-5, 0)]), Color(0.75, 0.88, 0.98))
			draw_polyline(PackedVector2Array([d + Vector2(0, -9), d + Vector2(5, 0), d + Vector2(0, 5), d + Vector2(-5, 0), d + Vector2(0, -9)]), INK, 1.5, true)
	# hat
	if P.has("hat") and P["hat"] != null:
		var ho: Vector2 = P["hat"]
		var hrot: float = P.get("hat_rot", 0.0)
		draw_set_transform_matrix(cam * base * Transform2D(hrot, Vector2.ONE, 0.0, head_c + ho))
		blob(Vector2(0, -36), 26, 17, Color(0.22, 0.22, 0.24), 0.0, 2.2, 14.0)
		draw_rect(Rect2(-26, -34, 52, 6), PAPER)
		blob(Vector2(0, -28), 38, 6, Color(0.22, 0.22, 0.24), 0.0, 2.2, 15.0)
	draw_set_transform_matrix(Transform2D.IDENTITY)

# ---------- world ----------
func draw_sky(cam: Transform2D) -> void:
	draw_set_transform_matrix(cam)
	var top := Color(0.78, 0.78, 0.76)
	var bot := Color(0.93, 0.92, 0.88)
	draw_polygon(PackedVector2Array([Vector2(-900, -900), Vector2(1500, -900), Vector2(1500, GROUND), Vector2(-900, GROUND)]), PackedColorArray([top, top, bot, bot]))

func draw_skyline(cam: Transform2D) -> void:
	draw_set_transform_matrix(cam)
	var col := Color(0.58, 0.58, 0.57)
	var x := -300.0
	var i := 0
	while x < 900.0:
		var w := 70.0 + 45.0 * absf(sin(i * 2.3))
		var h := 230.0 + 150.0 * absf(sin(i * 1.7 + 1.0))
		draw_rect(Rect2(x, GROUND - 90 - h, w, h + 90), col)
		for k in 3:
			draw_rect(Rect2(x + 10 + k * 18, GROUND - 90 - h + 22, 8, 12), Color(0.82, 0.81, 0.78))
		if i % 3 == 0:
			var cx := x + w * 0.5
			draw_rect(Rect2(cx - 7, GROUND - 90 - h - 70, 14, 72), col)
			for p in 5:
				var u := fmod(frame / FPS * 0.35 + p * 0.2 + i * 0.13, 1.0)
				var pc := Vector2(cx + u * 55.0 + sin(u * 9.0) * 6.0, GROUND - 90 - h - 78 - u * 120.0)
				draw_circle(pc + boil(p + i), 10 + u * 22, Color(0.85, 0.85, 0.83, 0.8 * (1.0 - u)))
		x += w + 8
		i += 1

func draw_midground(cam: Transform2D) -> void:
	draw_set_transform_matrix(cam)
	# building wall
	draw_rect(Rect2(-100, 340, 800, GROUND - 340), Color(0.70, 0.69, 0.66))
	draw_rect(Rect2(-100, 330, 800, 14), Color(0.30, 0.30, 0.31))
	var r := 0
	var y := 352.0
	while y < GROUND:
		draw_line(Vector2(-100, y), Vector2(700, y), Color(0.45, 0.45, 0.44), 2.0)
		var off := 0.0 if r % 2 == 0 else 24.0
		var xx := -100.0 + off
		while xx < 700.0:
			draw_line(Vector2(xx, y), Vector2(xx, y + 24), Color(0.45, 0.45, 0.44), 2.0)
			xx += 48.0
		y += 24.0
		r += 1
	# door
	draw_rect(Rect2(36, 470, 120, GROUND - 470), Color(0.30, 0.30, 0.31))
	draw_rect(Rect2(46, 480, 100, GROUND - 480), Color(0.38, 0.38, 0.39))
	draw_circle(Vector2(130, 600), 5, PAPER)
	# window
	draw_rect(Rect2(205, 400, 110, 120), INK)
	draw_rect(Rect2(212, 407, 96, 106), Color(0.88, 0.88, 0.85))
	draw_line(Vector2(260, 407), Vector2(260, 513), INK, 4.0)
	draw_line(Vector2(212, 460), Vector2(308, 460), INK, 4.0)
	# floor
	draw_rect(Rect2(-100, GROUND, 800, 400), Color(0.40, 0.39, 0.38))
	for k in 9:
		var yy := GROUND + 6 + k * k * 4.5
		draw_line(Vector2(-100, yy), Vector2(700, yy), Color(0.25, 0.25, 0.25), 2.0)

func draw_clock(cam: Transform2D, c: Vector2, t: float, ring: float, look_at: Vector2) -> void:
	draw_set_transform_matrix(cam)
	var sh := Vector2(sin(frame * 2.4) * 3.0, cos(frame * 3.1) * 2.0) * ring
	var p := c + sh
	# bells
	for sx in [-1.0, 1.0]:
		var bc := p + Vector2(sx * 36, -52)
		blob(bc, 17, 14, RED, 0.0, 2.5, 20.0 + sx)
	draw_line(p + Vector2(0, -60), p + Vector2(0, -74), INK, 4.0)
	# body
	blob(p, 54, 54, INK, 0.0, 0.0, 21.0)
	blob(p, 46, 46, PAPER, 0.0, 2.0, 22.0)
	# hands
	var a1 := t * 0.8 + ring * t * 10.0
	draw_line(p, p + Vector2(0, -26).rotated(a1), INK, 4.0, true)
	draw_line(p, p + Vector2(0, -17).rotated(a1 * 0.083), INK, 5.0, true)
	# tick marks
	for i in 12:
		var d := Vector2(0, -40).rotated(TAU * i / 12.0)
		draw_circle(p + d, 2.0, INK)
	# eyes follow the character
	var dir := (look_at - p).normalized()
	for sx in [-1.0, 1.0]:
		var ec := p + Vector2(sx * 13, 6)
		var e := 8.5 + ring * 2.0
		blob(ec, e, e * 1.35, Color(1, 1, 1), 0.0, 1.8, 23.0 + sx)
		draw_circle(ec + dir * 3.2, 3.6, INK)
	# mouth
	if ring > 0.0:
		blob(p + Vector2(0, 26), 11, 7 + 3 * absf(sin(frame * 1.7)), INK, 0.0, 0.0, 24.0)
		# ring arcs
		for k in 3:
			draw_arc(p, 66 + k * 12 + fmod(frame * 3.0, 12.0), -2.5, -0.64, 10, INK, 2.5, true)
			draw_arc(p, 66 + k * 12 + fmod(frame * 3.0, 12.0), -2.5 + 3.1, -0.64 + 3.1 + 0.0, 10, INK, 2.5, true)
	else:
		draw_arc(p + Vector2(0, 26), 10, 0.3, PI - 0.3, 10, INK, 3.0, true)

func draw_foreground(cam: Transform2D) -> void:
	draw_set_transform_matrix(cam)
	# crate + barrel silhouettes
	draw_rect(Rect2(-40, 690, 130, 160), Color(0.10, 0.10, 0.11))
	draw_line(Vector2(-40, 740), Vector2(90, 740), Color(0.3, 0.3, 0.3), 3.0)
	blob(Vector2(470, 790), 55, 80, Color(0.10, 0.10, 0.11))
	draw_line(Vector2(417, 770), Vector2(523, 770), Color(0.3, 0.3, 0.3), 3.0)

func overlays(t: float) -> void:
	draw_set_transform_matrix(Transform2D.IDENTITY)
	draw_texture_rect(vignette, Rect2(0, 0, W, H), false)
	var fl := 0.04 * sin(frame * 5.7) + 0.02 * sin(frame * 13.1)
	draw_rect(Rect2(0, 0, W, H), Color(0, 0, 0, clampf(0.05 + fl, 0.0, 1.0)) if fl > 0 else Color(1, 1, 1, clampf(-fl, 0.0, 1.0)))
	for i in 90:
		var k := frame * 131.0 + i * 17.0
		draw_rect(Rect2(fmod(k * 7.31, W), fmod(k * 3.77, H), 2, 2), Color(0, 0, 0, 0.18) if i % 3 else Color(1, 1, 1, 0.22))
	for i in 3:
		if fmod(frame * 0.37 + i * 3.1, 3.0) < 1.0:
			var x := fmod(frame * 53.0 + i * 211.0, W)
			draw_line(Vector2(x, 0), Vector2(x + sin(frame + i), H), Color(1, 1, 1, 0.12), 1.0)

# ---------- shots ----------
func walk(ph: float, speed_amp: float) -> Dictionary:
	var a := sin(ph)
	var b := sin(ph + PI)
	return {
		"foot_l": Vector2(-12 + a * 26, -maxf(0.0, cos(ph)) * 14.0),
		"foot_r": Vector2(12 + b * 26, -maxf(0.0, cos(ph + PI)) * 14.0),
		"hand_l": Vector2(-34 - b * 14 * speed_amp, -26 + absf(b) * 8),
		"hand_r": Vector2(34 + a * 14 * speed_amp, -26 + absf(a) * 8),
		"bob": -absf(cos(ph)) * 7.0 * speed_amp,
	}

func _draw() -> void:
	draw_rect(Rect2(0, 0, W, H), Color.BLACK)
	var t := frame / FPS
	var clock_c := Vector2(405, 420)
	if t < SHOTS[1]:
		shot_a(t / SHOTS[1], t, clock_c)
	elif t < SHOTS[2]:
		shot_b((t - SHOTS[1]) / (SHOTS[2] - SHOTS[1]), t, clock_c)
	else:
		shot_c((t - SHOTS[2]) / (SHOTS[3] - SHOTS[2]), t, clock_c)
	overlays(t)

func scene_layers(zoom: float, c: Vector2, t: float, ring: float, look_at: Vector2) -> Transform2D:
	draw_sky(xf(zoom, c, 0.15))
	draw_skyline(xf(zoom, c, 0.45))
	draw_midground(xf(zoom, c, 1.0))
	draw_clock(xf(zoom, c, 1.0), Vector2(405, 490), t, ring, look_at)
	return xf(zoom, c, 1.0)

func shot_a(u: float, t: float, clock_c: Vector2) -> void:
	var zoom := lerpf(1.0, 1.12, ease_io(u))
	var px := lerpf(-70.0, 190.0, ease_io(seg(u, 0.0, 0.85)))
	var c := Vector2(lerpf(240.0, 270.0, u), 520.0)
	var cam := scene_layers(zoom, c, t, 0.0, Vector2(px, 600))
	var stop := seg(u, 0.78, 1.0)
	var w := walk(t * 11.0, 1.0 - stop)
	w["pos"] = Vector2(px, GROUND - 8 + 40)
	w["s"] = S
	w["cam"] = cam
	w["flip"] = 1.0
	w["look"] = Vector2(1, -0.3) * (0.3 + stop)
	w["brow"] = 0.0
	w["mouth"] = "smile"
	w["hat"] = Vector2(0, -2)
	w["lean"] = 6.0 * (1.0 - stop)
	if stop > 0.0:
		var look_t := ease_io(seg(u, 0.9, 1.0))
		w["look"] = Vector2(1, -0.5)
		w["eye"] = 1.0 + 0.4 * look_t
	draw_pip(w)
	draw_foreground(xf(zoom, c, 1.35))

func shot_b(u: float, t: float, clock_c: Vector2) -> void:
	# close-up: surprise, double take, worry
	var punch := ease_back(seg(u, 0.0, 0.18))
	var zoom := lerpf(1.9, 2.5, ease_io(u)) * (0.9 + 0.1 * punch)
	var head := Vector2(190, GROUND - 8 + 40 - 98 * S)
	var shake := Vector2(sin(frame * 3.1), cos(frame * 2.3)) * 3.0 * (1.0 - seg(u, 0.2, 0.6))
	var cam := scene_layers(zoom, head + Vector2(40, 10) + shake, t, 0.0, Vector2(190, 600))
	var surprise := ease_back(seg(u, 0.0, 0.2))
	var worry := ease_io(seg(u, 0.5, 0.9))
	var P := {}
	P["pos"] = Vector2(190, GROUND - 8 + 40)
	P["s"] = S
	P["cam"] = cam
	P["eye"] = lerpf(1.0, 1.45, surprise) - 0.2 * worry
	P["pup"] = lerpf(1.0, 0.45, surprise) + 0.4 * worry
	P["brow"] = lerpf(0.0, 1.0, surprise) - 1.6 * worry
	P["mouth"] = "open" if worry < 0.6 else "frown"
	P["mouth_open"] = surprise * (1.0 - worry)
	P["look"] = Vector2(1, -0.4).lerp(Vector2(0.2, 0.2), worry)
	P["sweat"] = worry
	P["hat"] = Vector2(0, -2 - 22 * surprise * (1.0 - worry))
	P["hat_rot"] = 0.0
	P["tilt"] = 0.06 * sin(frame * 0.9) * (1.0 - seg(u, 0.3, 0.7))
	P["squash"] = 1.0 + 0.08 * (1.0 - surprise)
	draw_pip(P)

func shot_c(u: float, t: float, clock_c: Vector2) -> void:
	var zoom := lerpf(1.45, 1.0, ease_io(u))
	var c := Vector2(lerpf(300.0, 270.0, u), 520.0)
	var ring := ease_io(seg(u, 0.08, 0.2))
	var cam := scene_layers(zoom, c, t, ring, Vector2(190, 600))
	var react := ease_back(seg(u, 0.1, 0.3))
	var run := seg(u, 0.62, 1.0)
	var px := 190.0 - 40.0 * react * (1.0 - run) - 360.0 * ease_io(run) * 1.0
	# direction: runs off to the left (door side)
	var P := {}
	var jump := 0.0
	if u > 0.1 and u < 0.36:
		jump = 70.0 * sin(PI * seg(u, 0.1, 0.36))
	P["pos"] = Vector2(px, GROUND - 8 + 40 - jump)
	P["s"] = S
	P["cam"] = cam
	P["flip"] = 1.0 if run < 0.05 else -1.0
	P["eye"] = 1.4
	P["pup"] = 0.5
	P["brow"] = 1.0
	P["mouth"] = "open"
	P["mouth_open"] = 0.6 + 0.4 * absf(sin(frame * 1.3))
	P["sweat"] = 1.0
	P["look"] = Vector2(1, -0.6)
	var hat_u := seg(u, 0.12, 0.7)
	P["hat"] = Vector2(-10 * hat_u, -2 - 260 * sin(PI * hat_u * 0.5) + 150 * hat_u * hat_u) if hat_u > 0.0 else Vector2(0, -2)
	P["hat_rot"] = hat_u * 9.0
	if run <= 0.0:
		P["foot_l"] = Vector2(-18, -jump * 0.1)
		P["foot_r"] = Vector2(18, -jump * 0.1)
		P["hand_l"] = Vector2(-44, -76 - 10 * react)
		P["hand_r"] = Vector2(48 * (1.0 + 0.6 * react), -62 - 20 * react)
		P["point"] = true
		P["squash"] = 1.0 - 0.1 * sin(PI * seg(u, 0.1, 0.36))
		P["tilt"] = -0.1 * react
	else:
		var w := walk(t * 16.0, 1.4)
		for k in w:
			P[k] = w[k]
		P["lean"] = 14.0
		P["hand_l"] = Vector2(-44, -76 - 10 * sin(t * 16.0))
		P["hand_r"] = Vector2(44, -70 + 10 * sin(t * 16.0))
	draw_pip(P)
	draw_foreground(xf(zoom, c, 1.35))
