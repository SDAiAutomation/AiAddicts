"""Make faceless head bases so expressions can be drawn in code (any gaze, blink, brow, mouth) without the generated face drifting.
Pip: lens pupils painted out. Rosette: eyes, brows, nose, cheek marks and mouth painted out. Native pixels of the head crops."""
import os
from PIL import Image, ImageDraw

S = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sprites")

pip = Image.open(os.path.join(S, "head_neutral.png")).convert("RGBA")
d = ImageDraw.Draw(pip)
for cx in (176, 315):
    d.ellipse((cx - 34, 136 - 46, cx + 34, 136 + 46), fill=(255, 255, 255, 255))
pip.save(os.path.join(S, "head_blank_pip.png"))

ros = Image.open(os.path.join(S, "ros_head_blank.png")).convert("RGBA")
d = ImageDraw.Draw(ros)
d.polygon([(185, 236), (455, 236), (470, 300), (482, 447), (166, 447), (150, 380), (170, 300)], fill=(255, 255, 250, 255))
ros.save(os.path.join(S, "ros_head_blank2.png"))
print("ok")
