"""Standalone, zero-network Faceloop WOW animation experiment. Not wired to production."""
from __future__ import annotations
import argparse
import math
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT, FPS, DURATION = 540, 960, 15, 15
SCENES = ((0, 5, 'The offer'), (5, 10, 'The doubt'), (10, 15, 'The choice'))


def character(draw, x, y, scale, color, speaking, blink, phase):
    r = 84 * scale
    y += math.sin(phase * 2.5) * 4 * scale
    draw.ellipse((x-r*.8,y+r*.6,x+r*.8,y+r*2.3),fill=color)
    draw.polygon(((x-r*.72,y-r*.36),(x-r*.65,y-r*1.55),(x-r*.05,y-r*.8)),fill=color)
    draw.polygon(((x+r*.72,y-r*.36),(x+r*.65,y-r*1.55),(x+r*.05,y-r*.8)),fill=color)
    draw.ellipse((x-r,y-r,x+r,y+r),fill=color)
    for side in (-1,1):
        ex=x+side*r*.38
        if blink: draw.line((ex-r*.13,y-r*.15,ex+r*.13,y-r*.15),fill='#172337',width=4)
        else:
            draw.ellipse((ex-r*.11,y-r*.28,ex+r*.11,y-r*.02),fill='#fff8e8')
            draw.ellipse((ex-r*.04,y-r*.2,ex+r*.05,y-r*.08),fill='#172337')
    if speaking: draw.ellipse((x-r*.14,y+r*.35,x+r*.14,y+r*.62),fill='#3b1932')
    else: draw.arc((x-r*.18,y+r*.31,x+r*.18,y+r*.55),0,180,fill='#3b1932',width=4)
    sway=math.sin(phase*3)*10*scale
    draw.line((x-r*.72,y+r,x-r*1.05,y+r*1.45+sway),fill=color,width=15)
    draw.line((x+r*.72,y+r,x+r*1.05,y+r*1.45-sway),fill=color,width=15)


def frame_at(index, fps=FPS):
    t=index/fps
    scene=next((i for i,(start,end,_) in enumerate(SCENES) if start<=t<end),2)
    image=Image.new('RGB',(WIDTH,HEIGHT),'#0b1324')
    d=ImageDraw.Draw(image)
    for j in range(12):
        offset=int((t*5*(j%3+1))%HEIGHT)
        d.line((j*53-30,0,j*53-30+offset//12,HEIGHT),fill='#15243a',width=2)
    d.rounded_rectangle((24,110,WIDTH-24,760),radius=25,fill='#17243b',outline='#34455f',width=3)
    d.rectangle((60,160,WIDTH-60,390),fill='#213b54')
    d.ellipse((310,195,430,315),fill='#f2bd73')
    d.rectangle((60,385,WIDTH-60,395),fill='#33465d')
    zoom=1+.025*math.sin(t*.7)
    character(d,170,535,.82*zoom,'#d18a57',scene==0 and int(t*4)%2==0,index%83<3,t*2.3)
    character(d,385,540,.92*zoom,'#7da7c4',scene==1 and int(t*4)%2==0,index%71<3,t*2.3+.8)
    d.rounded_rectangle((25,785,WIDTH-25,917),radius=20,fill='#0a1020')
    lines=('One small promise can change everything.','But not every promise is meant to be kept.','Choose the truth, even when it is hard.')
    d.text((45,802),SCENES[scene][2],fill='#ffcc80',font=ImageFont.load_default(size=27))
    d.text((45,858),lines[scene],fill='#ffffff',font=ImageFont.load_default(size=15))
    d.text((32,32),'FACELOOP  /  WOW LAB',fill='#d9e5f5',font=ImageFont.load_default(size=18))
    d.text((32,64),'OFFLINE ANIMATION PROTOTYPE',fill='#8aa2bc',font=ImageFont.load_default(size=13))
    return image


def render(output: Path, duration: int = DURATION, fps: int = FPS) -> Path:
    if not (0 < fps <= 60 and 0 < duration <= 90): raise ValueError('Invalid duration or FPS')
    output=output.resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s',f'{WIDTH}x{HEIGHT}','-r',str(fps),'-i','-','-an','-c:v','libx264','-preset','ultrafast','-crf','26','-pix_fmt','yuv420p','-movflags','+faststart',str(output)]
    with subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE) as p:
        try:
            for i in range(fps*duration): p.stdin.write(frame_at(i,fps).tobytes())
            p.stdin.close()
            err=p.stderr.read()
            status=p.wait()
        except Exception:
            p.kill(); p.wait(); raise
    if status or not output.exists() or not output.stat().st_size: raise RuntimeError(err.decode(errors='replace')[-1000:])
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('wow_pilot.mp4'))
    parser.add_argument('--duration',type=int,default=DURATION)
    parser.add_argument('--fps',type=int,default=FPS)
    args=parser.parse_args()
    print(render(args.output,args.duration,args.fps))
