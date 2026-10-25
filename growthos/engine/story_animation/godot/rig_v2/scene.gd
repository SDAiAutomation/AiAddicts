extends Node2D
# Pure deterministic cutout compositor. All anatomy, sprites and face anchors come from validated rig.json files.
# The Python boundary validates every character id, asset hash and frame instruction before starting this process.

const FPS := 24.0
const W := 1080.0
const H := 1920.0
const INK := Color(0.12, 0.10, 0.13)
var frame := 0
var timeline: Dictionary = {}
var rigs: Dictionary = {}
var textures: Dictionary = {}

func _fail(message: String) -> void:
	push_error(message)
	get_tree().quit(3)

func _ready() -> void:
	var pack_dir := ""
	var timeline_file := ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--pack="):
			pack_dir = arg.substr(7)
		elif arg.begins_with("--timeline="):
			timeline_file = arg.substr(11)
	if pack_dir == "" or timeline_file == "":
		_fail("missing validated pack or timeline")
		return
	var data = JSON.parse_string(FileAccess.get_file_as_string(timeline_file))
	if typeof(data) != TYPE_DICTIONARY or data.get("rig_schema_version", 0) != 1:
		_fail("invalid generic rig timeline")
		return
	timeline = data
	for id in timeline["characters"]:
		var directory := pack_dir.path_join(String(id))
		var manifest = JSON.parse_string(FileAccess.get_file_as_string(directory.path_join("rig.json")))
		if typeof(manifest) != TYPE_DICTIONARY:
			_fail("invalid validated rig manifest")
			return
		rigs[id] = manifest
		var sprites: Dictionary = manifest["sprites"]
		var parts: Dictionary = {}
		for sprite_id in sprites.values():
			var picture := Image.load_from_file(directory.path_join(String(sprite_id) + ".png"))
			if picture == null or picture.is_empty():
				_fail("missing validated rig asset")
				return
			parts[sprite_id] = ImageTexture.create_from_image(picture)
		textures[id] = parts

func _process(_delta: float) -> void:
	if timeline.is_empty():
		return
	if frame >= int(timeline["total_frames"]):
		get_tree().quit()
		return
	queue_redraw()
	frame += 1

func _point(value: Array) -> Vector2:
	return Vector2(float(value[0]), float(value[1]))

func _shot() -> Dictionary:
	for shot in timeline["shots"]:
		if frame >= int(shot["start_frame"]) and frame < int(shot["end_frame"]):
			return shot
	return timeline["shots"].back()

func _image(id: String, role: String) -> Texture2D:
	return textures[id][rigs[id]["sprites"][role]]

func _sprite(texture: Texture2D, center: Vector2, size: Vector2) -> void:
	draw_texture_rect(texture, Rect2(center - size * 0.5, size), false)

func _body(id: String, actor: Dictionary, shot: Dictionary, cam: Transform2D) -> void:
	var rig: Dictionary = rigs[id]
	var anchors: Dictionary = rig["anchors"]
	var hip := _point(anchors["hip"])
	var neck := _point(anchors["neck"])
	var shoulder_l := _point(anchors["shoulder_l"])
	var shoulder_r := _point(anchors["shoulder_r"])
	var wrist_l := _point(anchors["wrist_l"])
	var wrist_r := _point(anchors["wrist_r"])
	var ankle_l := _point(anchors["ankle_l"])
	var ankle_r := _point(anchors["ankle_r"])
	var action: String = actor["action"]
	var phase := float(frame - int(shot["start_frame"])) / FPS
	var breath := sin(phase * 2.5 + float(id.hash() % 7)) * 3.0
	var stride := 0.0
	if action == "walk":
		stride = sin(phase * 7.0) * 36.0
	elif action == "run" or action == "run_away":
		stride = sin(phase * 12.0) * 70.0
	if stride != 0.0:
		ankle_l.x += stride
		ankle_r.x -= stride
		wrist_l.x -= stride * 0.6
		wrist_r.x += stride * 0.6
	if action == "point":
		wrist_r = shoulder_r + Vector2(170, -90)
	elif action == "accuse":
		wrist_r = shoulder_r + Vector2(230, -65)
		wrist_l = hip + Vector2(-110, -60)
	elif action == "defend":
		wrist_l = neck + Vector2(-135, -30)
		wrist_r = neck + Vector2(135, -30)
	elif action == "wring":
		wrist_l = hip + Vector2(-30, -65)
		wrist_r = hip + Vector2(30, -65)
	elif action == "indignant":
		wrist_l = shoulder_l + Vector2(-190, 0)
		wrist_r = shoulder_r + Vector2(190, 0)
	elif action == "clutch_head":
		wrist_l = neck + Vector2(-70, -125)
		wrist_r = neck + Vector2(70, -125)
	elif action == "hands_on_hips":
		wrist_l = hip + Vector2(-95, -35)
		wrist_r = hip + Vector2(95, -35)
	elif action == "shrug":
		wrist_l = shoulder_l + Vector2(-120, -65)
		wrist_r = shoulder_r + Vector2(120, -65)
	elif action == "wave":
		wrist_r = neck + Vector2(135 + 22.0 * sin(phase * 7.0), -170)
	elif action == "react":
		wrist_l = neck + Vector2(-100, -70)
		wrist_r = neck + Vector2(100, -70)
	elif action == "talk":
		wrist_r += Vector2(22.0 * sin(phase * 6.0), -30.0 * absf(sin(phase * 6.0)))
	neck.y += breath
	var scale_ := 0.72
	var flip := -1.0 if actor["facing"] == "left" else 1.0
	var ground := 1510.0
	var ankles := (ankle_l.y + ankle_r.y) * 0.5
	var origin := Vector2(float(actor["x"]) * W - hip.x * scale_ * flip, ground - (ankles - hip.y) * scale_ - hip.y * scale_)
	var transform_ := Transform2D(0.0, Vector2(scale_ * flip, scale_), 0.0, origin)
	draw_set_transform_matrix(cam * transform_)
	draw_line(_point(anchors["hip_l"]), ankle_l, INK, 35.0, true)
	draw_line(_point(anchors["hip_r"]), ankle_r, INK, 35.0, true)
	draw_line(shoulder_l, wrist_l, INK, 32.0, true)
	draw_line(shoulder_r, wrist_r, INK, 32.0, true)
	_sprite(_image(id, "foot_l"), ankle_l, _image(id, "foot_l").get_size())
	_sprite(_image(id, "foot_r"), ankle_r, _image(id, "foot_r").get_size())
	_sprite(_image(id, "torso"), (hip + neck) * 0.5, _image(id, "torso").get_size())
	var head := _image(id, "head")
	var head_size := head.get_size()
	var head_top := neck - Vector2(head_size.x * 0.5, head_size.y)
	draw_texture_rect(head, Rect2(head_top, head_size), false)
	var face: Dictionary = rig["face"]
	var mood: String = actor["expression"]
	for key in ["eye_l", "eye_r"]:
		var eye := head_top + _point(face[key])
		if mood == "happy" or mood == "joy":
			draw_arc(eye, 14, 0.1, PI - 0.1, 12, INK, 5.0, true)
		else:
			draw_circle(eye, 16.0 if mood == "surprised" or mood == "surprise" or mood == "panic" else 11.0, INK)
		if mood == "angry":
			draw_line(eye + Vector2(-18, -26), eye + Vector2(18, -15), INK, 5.0, true)
		elif mood == "worry" or mood == "puzzled":
			draw_line(eye + Vector2(-18, -20), eye + Vector2(18, -28), INK, 4.0, true)
	var mouth := head_top + _point(face["mouth"])
	var cue: String = actor["mouth_track"]
	var mouth_frame := mini(frame - int(shot["start_frame"]), cue.length() - 1)
	var mouth_shape := cue[mouth_frame]
	if mouth_shape == "o" or mouth_shape == "r" or mood == "surprised" or mood == "surprise" or mood == "panic":
		draw_circle(mouth, 13.0 if mouth_shape == "o" else 8.0 if mouth_shape == "r" else 18.0, INK)
	else:
		draw_arc(mouth + Vector2(0, -8 if mood == "sad" or mood == "worry" else 0), 18.0, 0.1 if mood != "sad" and mood != "worry" else PI + 0.1, PI - 0.1 if mood != "sad" and mood != "worry" else TAU - 0.1, 12, INK, 4.0, true)
	_sprite(_image(id, "hand_l"), wrist_l, _image(id, "hand_l").get_size())
	_sprite(_image(id, "hand_r"), wrist_r, _image(id, "hand_r").get_size())
	draw_set_transform_matrix(Transform2D.IDENTITY)

func _draw() -> void:
	if timeline.is_empty():
		return
	var shot := _shot()
	draw_rect(Rect2(0, 0, W, H), Color(0.87, 0.88, 0.77))
	var camera: Dictionary = shot["camera"]
	var progress := float(frame - int(shot["start_frame"])) / maxf(1.0, float(int(shot["end_frame"]) - int(shot["start_frame"])))
	var zoom := lerpf(float(camera["zoom_from"]), float(camera["zoom_to"]), progress)
	var focus := Vector2(W * 0.5, 1020)
	if camera["move"] == "pan_left":
		focus.x -= 100.0 * (progress - 0.5)
	elif camera["move"] == "pan_right":
		focus.x += 100.0 * (progress - 0.5)
	var cam := Transform2D(0.0, Vector2(zoom, zoom), 0.0, Vector2(W, H) * 0.5 - focus * zoom)
	draw_set_transform_matrix(cam)
	var setting: String = shot["setting"]
	if setting == "clock_shop" or setting == "clock_shop_closed":
		draw_rect(Rect2(0, 0, W, H), Color(0.78, 0.73, 0.65) if setting == "clock_shop" else Color(0.34, 0.36, 0.43))
		for i in 4:
			draw_rect(Rect2(65 + i * 270, 670, 180, 540), Color(0.49, 0.33, 0.26))
			draw_rect(Rect2(88 + i * 270, 720, 135, 180), Color(0.88, 0.78, 0.55))
		draw_rect(Rect2(0, 1400, W, 520), Color(0.43, 0.35, 0.31))
	elif setting == "forest":
		for i in 7:
			var tree_x := -100.0 + float(i) * 220.0
			var tree_h := 470.0 + float((i * 67) % 170)
			draw_rect(Rect2(tree_x - 22, 1430.0 - tree_h, 44, tree_h), Color(0.37, 0.42, 0.36))
			draw_circle(Vector2(tree_x, 1430.0 - tree_h), 130.0, Color(0.59, 0.68, 0.52))
			draw_circle(Vector2(tree_x - 55, 1480.0 - tree_h), 95.0, Color(0.62, 0.70, 0.55))
		draw_rect(Rect2(0, 1400, W, 520), Color(0.36, 0.50, 0.39))
	else:
		var city := Color(0.69, 0.72, 0.72) if setting != "street_rain" else Color(0.42, 0.49, 0.57)
		for i in 5:
			var building_h := 460.0 + float((i * 97) % 220)
			draw_rect(Rect2(i * 230 - 20, 1430 - building_h, 190, building_h), city)
		for i in 6:
			draw_rect(Rect2(10 + i * 190, 1420, 130, 18), Color(0.40, 0.42, 0.41))
		draw_rect(Rect2(0, 1440, W, 480), Color(0.48, 0.50, 0.47))
	for actor in shot["actors"]:
		_body(String(actor["character_id"]), actor, shot, cam)
	draw_set_transform_matrix(Transform2D.IDENTITY)
	var subtitle: String = shot["subtitle"]
	if timeline.has("subs"):
		subtitle = ""
		for sub in timeline["subs"]:
			if frame >= int(sub["start_frame"]) and frame < int(sub["end_frame"]):
				subtitle = String(sub["text"])
				break
	if subtitle != "":
		var font := ThemeDB.fallback_font
		var width := font.get_string_size(subtitle, HORIZONTAL_ALIGNMENT_LEFT, -1, 48).x
		draw_rect(Rect2((W - width) * 0.5 - 22, 1700, width + 44, 75), Color(0.08, 0.08, 0.08, 0.85))
		draw_string(font, Vector2((W - width) * 0.5, 1753), subtitle, HORIZONTAL_ALIGNMENT_LEFT, -1, 48, Color.WHITE)
	if shot["transition"] == "fade":
		var fade := 1.0 - clampf(float(frame - int(shot["start_frame"])) / 9.0, 0.0, 1.0)
		draw_rect(Rect2(0, 0, W, H), Color(0, 0, 0, fade))
