extends Node2D

# Offline visual review only. Full-body references are not cutout rig assets.
const W := 1080.0
const H := 1920.0
const FRAMES := 144

var people: Array[Texture2D] = []
var frame := 0

func _ready() -> void:
	var args := {}
	for item in OS.get_cmdline_user_args():
		var arg: String = item
		if arg.begins_with("--pip="):
			args["pip"] = arg.trim_prefix("--pip=")
		if arg.begins_with("--rosette="):
			args["rosette"] = arg.trim_prefix("--rosette=")
	for id in ["pip", "rosette"]:
		if not args.has(id):
			push_error("missing approved local reference")
			get_tree().quit(2)
			return
		var picture := Image.load_from_file(args[id])
		if picture.is_empty():
			push_error("reference image cannot be loaded")
			get_tree().quit(2)
			return
		people.append(ImageTexture.create_from_image(picture))
	queue_redraw()

func _process(_delta: float) -> void:
	frame += 1
	if frame >= FRAMES:
		get_tree().quit()
	else:
		queue_redraw()

func _draw() -> void:
	if people.size() != 2:
		return
	draw_rect(Rect2(0, 0, W, H), Color(0.82, 0.77, 0.67))
	draw_rect(Rect2(35, 180, 1010, 1190), Color(0.45, 0.39, 0.37))
	for i in 5:
		draw_rect(Rect2(65 + i * 205, 260, 130, 550), Color(0.74, 0.65, 0.49))
	draw_rect(Rect2(0, 1420, W, 500), Color(0.46, 0.40, 0.36))
	var progress := float(frame) / float(FRAMES - 1)
	var scale_factor := 0.52 + progress * 0.04
	for i in 2:
		var texture := people[i]
		var size := texture.get_size() * scale_factor
		var center_x := 280.0 if i == 0 else 800.0
		draw_texture_rect(texture, Rect2(center_x - size.x * 0.5, 1530.0 - size.y, size.x, size.y), false)
	var font := ThemeDB.fallback_font
	var caption := "APERCU VISUEL — PERSONNAGES NON RIGGES"
	var width := font.get_string_size(caption, HORIZONTAL_ALIGNMENT_LEFT, -1, 33).x
	draw_rect(Rect2((W - width) * 0.5 - 24, 1720, width + 48, 56), Color(0.1, 0.1, 0.12, 0.82))
	draw_string(font, Vector2((W - width) * 0.5, 1760), caption, HORIZONTAL_ALIGNMENT_LEFT, -1, 33, Color.WHITE)
