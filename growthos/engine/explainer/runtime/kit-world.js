/* kit-world.js — illustration du monde réel, en formes plates (aucune image, tout est procédural et déterministe).
   Personnages, maison en coupe, ville de nuit, tour d'antenne, océan avec câble sous-marin, data center.
   Toutes les fonctions dessinent dans le repère courant (monde) ; aucune n'utilise Math.random (hasard seedé via hash). */
const WC={
  night0:'#070b1f',night1:'#18204f',dusk:'#3a2a66',glow:'#ffcf7a',
  sea0:'#117aa8',sea1:'#041a33',sand:'#d7b57a',sand2:'#8f6f3f',land:'#141a38',land2:'#222a55',
  skin:{deep:'#6b4128',brown:'#9a6240',tan:'#d79b6d',light:'#f1c9a5'},
};
const vgrad=(x,y0,y1,stops)=>{const g=ctx.createLinearGradient(x,y0,x,y1);for(const [p,c] of stops)g.addColorStop(p,c);return g};
const glowAt=(x,y,r,col,a)=>{if(a<=0)return;const g=ctx.createRadialGradient(x,y,0,x,y,r);g.addColorStop(0,col);g.addColorStop(1,'rgba(0,0,0,0)');
  ctx.save();ctx.globalAlpha*=a;ctx.globalCompositeOperation='lighter';ctx.fillStyle=g;ctx.fillRect(x-r,y-r,2*r,2*r);ctx.restore()};
const mix=(c0,c1,p)=>{const a=parseInt(c0.slice(1),16),b=parseInt(c1.slice(1),16);const ch=s=>Math.round(lerp((a>>s)&255,(b>>s)&255,p));
  return '#'+((1<<24)|(ch(16)<<16)|(ch(8)<<8)|ch(0)).toString(16).slice(1)};

/* ---- ciel et ville ------------------------------------------------------------------------------------------ */
function sky(x0,x1,y0,y1,t,o={}){
  ctx.fillStyle=vgrad(0,y0,y1,[[0,o.top||WC.night0],[0.7,o.mid||WC.night1],[1,o.low||WC.dusk]]);ctx.fillRect(x0,y0,x1-x0,y1-y0);
  const n=o.stars??90;
  for(let i=0;i<n;i++){const x=lerp(x0,x1,hash(i,11)),y=lerp(y0,y1-(y1-y0)*0.35,hash(i,12)),tw=0.35+0.65*(0.5+0.5*Math.sin(t*(1+hash(i,13)*2)+i));
    ctx.globalAlpha=0.25+0.55*tw*hash(i,14);ctx.fillStyle='#fff';ctx.fillRect(x,y,2+hash(i,15)*2,2+hash(i,15)*2)}
  ctx.globalAlpha=1;
  if(o.moon){const [mx,my]=o.moon;glowAt(mx,my,260,'rgba(255,240,200,0.5)',0.7);ctx.fillStyle='#fff3d6';ctx.beginPath();ctx.arc(mx,my,46,0,7);ctx.fill();
    ctx.fillStyle='rgba(180,160,120,0.35)';ctx.beginPath();ctx.arc(mx-14,my-6,10,0,7);ctx.arc(mx+12,my+14,7,0,7);ctx.fill()}
}
/* skyline : bâtiments seedés avec fenêtres allumées. x0 = bord gauche, baseY = sol. */
function city(x0,baseY,count,o={}){
  const seed=o.seed||1,warm=o.warm||'#ffd27a',cool=o.cool||'#8fd3ff';let x=x0;
  for(let i=0;i<count;i++){
    const w=64+hash(i,seed)*70,h=(o.minH||140)+hash(i,seed+1)*(o.varH||280),far=o.far?0.55:1;
    ctx.fillStyle=mix(o.body||'#1b2350',o.fog||'#0a1030',o.far?0.55:0);ctx.fillRect(x,baseY-h,w,h);
    ctx.fillStyle='rgba(255,255,255,0.05)';ctx.fillRect(x,baseY-h,w,5);
    const cols=Math.max(2,Math.floor(w/22)),rows=Math.floor(h/30);
    for(let r=1;r<rows;r++)for(let c=0;c<cols;c++){const lit=hash(i*97+r*7+c,seed+2);if(lit<0.45)continue;
      ctx.globalAlpha=(0.35+0.65*hash(i+c,r+seed))*(o.far?0.5:1);ctx.fillStyle=lit>0.8?cool:warm;ctx.fillRect(x+8+c*(w-16)/cols,baseY-h+14+r*30,10,14)}
    ctx.globalAlpha=1;x+=w+(o.gap??10);
  }
  return x;
}
/* tour d'antenne en treillis. act (0..1) : anneaux radio. */
function tower(x,baseY,h,o={}){
  const t=o.t||0,w=h*0.16;ctx.save();ctx.strokeStyle='#cfd8f5';ctx.lineWidth=h*0.012;ctx.lineCap='round';ctx.lineJoin='round';
  ctx.beginPath();ctx.moveTo(x-w,baseY);ctx.lineTo(x-4,baseY-h);ctx.moveTo(x+w,baseY);ctx.lineTo(x+4,baseY-h);ctx.stroke();
  ctx.lineWidth=h*0.007;ctx.beginPath();const n=9;
  for(let i=0;i<n;i++){const p0=i/n,p1=(i+1)/n,xl0=lerp(-w,-4,p0),xr0=lerp(w,4,p0),xl1=lerp(-w,-4,p1),xr1=lerp(w,4,p1),y0=baseY-h*p0,y1=baseY-h*p1;
    ctx.moveTo(x+xl0,y0);ctx.lineTo(x+xr1,y1);ctx.moveTo(x+xr0,y0);ctx.lineTo(x+xl1,y1);ctx.moveTo(x+xl1,y1);ctx.lineTo(x+xr1,y1)}
  ctx.stroke();
  ctx.fillStyle='#e9eefc';ctx.fillRect(x-h*0.05,baseY-h*0.78,h*0.1,h*0.05);ctx.fillRect(x-h*0.05,baseY-h*0.6,h*0.1,h*0.05);
  const blink=0.5+0.5*Math.sin(t*5);ctx.fillStyle='#ff4a4a';glowAt(x,baseY-h-8,70,'rgba(255,60,60,0.9)',0.5*blink);
  ctx.beginPath();ctx.arc(x,baseY-h-8,Math.max(5,h*0.014),0,7);ctx.fill();ctx.restore();
  const act=o.act||0;
  if(act>0){ctx.save();ctx.strokeStyle=o.ring||LC[1];ctx.lineWidth=Math.max(3,h*0.008);for(let k=0;k<3;k++){const r=((t*1.3+k/3)%1);
    ctx.globalAlpha=act*(1-r);ctx.beginPath();ctx.arc(x,baseY-h-8,h*0.05+r*h*0.42,-2.5,-0.64);ctx.stroke();ctx.beginPath();ctx.arc(x,baseY-h-8,h*0.05+r*h*0.42,Math.PI+0.64,Math.PI+2.5);ctx.stroke()}ctx.restore()}
}

/* ---- personnage ----------------------------------------------------------------------------------------------- */
/* Géométrie locale (origine = hanche, visage vers +x). `pose` : 'sitPhone' | 'sitHappy' | 'sitRead'. */
function personGeom(o){
  const pose=o.pose||'sitPhone',lean=pose==='sitHappy'?0.04:pose==='sitRead'?0.1:0.16,t=o.t||0;
  const S=[110*Math.sin(lean)-6,-110*Math.cos(lean)],head=[S[0]+10+lean*30,S[1]-58];
  const hand=pose==='sitHappy'?[S[0]+62,S[1]+24]:[S[0]+66,S[1]+36],elbow=[S[0]+26,S[1]+56];
  return {pose,S,head,hand,elbow,phone:[hand[0]+8,hand[1]-12],phoneAngle:-0.25,lean};
}
function localToWorld(x,y,s,flip,p){return [x+(flip?-p[0]:p[0])*s,y+p[1]*s]}
function personPhonePos(x,y,o){const g=personGeom(o);return localToWorld(x,y,o.s||1,!!o.flip,g.phone)}
function person(x,y,o={}){
  const {s=1,skin=WC.skin.brown,hair='#150e0c',style='short',top='#ff8a5b',pants='#222a55',t=0,flip=false,id=0,typing=false,glow=0,phoneUI=null}=o;
  const g=personGeom(o),{S,head,hand,elbow}=g,pose=g.pose;
  ctx.save();ctx.translate(x,y);ctx.scale(flip?-s:s,s);
  const line=(a,b,w,c)=>{ctx.strokeStyle=c;ctx.lineWidth=w;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke()};
  // ombre de contact
  ctx.fillStyle='rgba(0,0,0,0.18)';ctx.beginPath();ctx.ellipse(40,70,70,9,0,0,7);ctx.fill();
  // jambes
  line([0,0],[72,-2],36,pants);line([72,-2],[80,60],30,pants);
  ctx.fillStyle='#f2f2f2';ctx.beginPath();ctx.ellipse(98,68,24,11,0,0,7);ctx.fill();ctx.fillStyle='#d8d8d8';ctx.fillRect(78,70,40,5);
  // cheveux de derrière
  const hx=head[0],hy=head[1];ctx.fillStyle=hair;
  if(style==='curly'){for(let k=0;k<11;k++){const a=Math.PI*(0.85+k*0.13);ctx.beginPath();ctx.arc(hx-4+Math.cos(a)*40,hy-4+Math.sin(a)*38,22,0,7);ctx.fill()}}
  else if(style==='braids'){ctx.beginPath();ctx.ellipse(hx-8,hy-6,41,40,0,0,7);ctx.fill();for(let k=0;k<5;k++){line([hx-30+k*6,hy+10],[hx-46+k*8,hy+86+k*3],8,hair)}}
  else if(style==='bun'){ctx.beginPath();ctx.ellipse(hx-6,hy-4,40,40,0,0,7);ctx.fill();ctx.beginPath();ctx.arc(hx-18,hy-52,20,0,7);ctx.fill()}
  else{ctx.beginPath();ctx.ellipse(hx-6,hy-6,40,40,0,0,7);ctx.fill()}
  // torse
  line([0,2],S,66,top);ctx.fillStyle=mix(top,'#000000',0.18);ctx.beginPath();ctx.arc(S[0],S[1]+6,33,Math.PI,0);ctx.fill();
  // cou + tête
  line([S[0]+2,S[1]-8],[hx-2,hy+30],24,skin);ctx.fillStyle=skin;ctx.beginPath();ctx.arc(hx,hy,38,0,7);ctx.fill();
  ctx.fillStyle=mix(skin,'#000000',0.12);ctx.beginPath();ctx.arc(hx-14,hy+6,9,0,7);ctx.fill();   // oreille
  // frange
  ctx.fillStyle=hair;ctx.beginPath();ctx.arc(hx-2,hy-4,40,Math.PI*1.02,Math.PI*1.82);ctx.lineTo(hx+30,hy-18);ctx.quadraticCurveTo(hx+8,hy-26,hx-34,hy-6);ctx.fill();
  // visage
  const bp=(t+id*1.3)%3.4,closed=bp<0.13||pose==='sitHappy';
  const ex=hx+17+(pose==='sitPhone'?2:0),ey=hy+(pose==='sitPhone'?4:0);
  ctx.strokeStyle='#1a0f0b';ctx.lineWidth=4;ctx.lineCap='round';
  if(closed){ctx.beginPath();ctx.arc(ex,ey+(pose==='sitHappy'?4:0),6,Math.PI*1.1,Math.PI*1.9);ctx.stroke()}
  else{ctx.fillStyle='#1a0f0b';ctx.beginPath();ctx.ellipse(ex+(pose==='sitPhone'?1.5:0),ey+(pose==='sitPhone'?2:0),4.2,5.6,0,0,7);ctx.fill();ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(ex+2.5,ey,1.5,0,7);ctx.fill()}
  ctx.beginPath();ctx.moveTo(ex-9,ey-14);ctx.lineTo(ex+8,ey-14-(pose==='sitHappy'?3:0));ctx.stroke();
  ctx.lineWidth=3.5;ctx.beginPath();
  if(pose==='sitHappy'){ctx.arc(hx+16,hy+16,13,0.15,Math.PI-0.55);ctx.stroke();ctx.fillStyle='rgba(255,120,110,0.28)';ctx.beginPath();ctx.arc(hx+8,hy+14,8,0,7);ctx.fill()}
  else{ctx.moveTo(hx+9,hy+22);ctx.quadraticCurveTo(hx+17,hy+25,hx+24,hy+21);ctx.stroke()}
  // bras + téléphone
  line([S[0]+2,S[1]+6],elbow,28,top);line(elbow,hand,20,skin);ctx.fillStyle=skin;ctx.beginPath();ctx.arc(hand[0]+6,hand[1]-4,13,0,7);ctx.fill();   // main derriere le telephone
  const [px,py]=g.phone,k=56/1100;
  if(glow>0)glowAt(px+6,py,130,'rgba(255,214,150,0.9)',glow*0.35);
  ctx.save();ctx.translate(px,py);ctx.rotate(g.phoneAngle);
  if(phoneUI){ctx.save();if(flip)ctx.scale(-1,1);ctx.scale(k,k);phone(0,0,phoneUI);ctx.restore()}
  else{ctx.fillStyle='#161f37';rr(-14,-28,28,56,6);ctx.fill();ctx.fillStyle='#0c1326';rr(-12,-26,24,52,4);ctx.fill()}
  ctx.restore();
  // pouce
  const th=typing?[hand[0]-2+Math.sin(t*15+id)*3,hand[1]+(-1)+Math.cos(t*19)*2]:[hand[0]-3,hand[1]];
  const ta=o.thumbA??1;if(ta>0){ctx.save();ctx.globalAlpha*=ta;ctx.fillStyle=skin;ctx.beginPath();ctx.arc(th[0]+8,th[1]-10,5,0,7);ctx.fill();line([th[0]+8,th[1]-10],[hand[0]-2,hand[1]+6],8,skin);ctx.restore()}
  ctx.restore();
}

/* ---- maison en coupe -------------------------------------------------------------------------------------------- */
/* cx = centre, baseY = bas du bâtiment. Palette 'dakar' (chaude) ou 'paris' (froide). Renvoie les ancres utiles. */
function houseAnchors(cx,baseY,o={}){
  const floorY=baseY-40,w=o.w||720,h=o.h||500;
  return {floorY,left:cx-w/2,right:cx+w/2,top:baseY-h,w,h,seatX:cx+(o.flip?110:-120),seatY:floorY-66,windowX:cx+(o.flip?-200:200)};
}
function house(cx,baseY,o={}){
  const a=houseAnchors(cx,baseY,o),p=o.palette==='paris',t=o.t||0;
  const wall=p?'#c9d4e6':'#e0b88a',wall2=p?'#b4c2da':'#cfa073',floor=p?'#5a4a42':'#7b5642',shell=p?'#2e3a66':'#3a2a5c',sofa=p?'#3f8c78':'#4b5fa8',sofa2=p?'#2e6c5c':'#39498a';
  const dark=o.dark??0.25;
  // volume extérieur
  ctx.fillStyle=shell;rr(a.left-18,a.top-30,a.w+36,a.h+30,6);ctx.fill();
  ctx.fillStyle=mix(shell,'#ffffff',0.12);ctx.fillRect(a.left-30,a.top-46,a.w+60,22);
  // intérieur
  ctx.save();ctx.beginPath();ctx.rect(a.left,a.top,a.w,a.h-40);ctx.clip();
  ctx.fillStyle=vgrad(0,a.top,a.floorY,[[0,wall],[1,wall2]]);ctx.fillRect(a.left,a.top,a.w,a.h);
  // fenêtre + vue
  const wx=a.windowX,wy=a.top+70,ww=150,wh=210;
  ctx.fillStyle=vgrad(0,wy,wy+wh,[[0,'#0b1230'],[1,'#3a2a66']]);rr(wx-ww/2,wy,ww,wh,10);ctx.fill();
  ctx.save();rr(wx-ww/2,wy,ww,wh,10);ctx.clip();
  if(p){ctx.strokeStyle='#8fa0c9';ctx.lineWidth=5;ctx.beginPath();ctx.moveTo(wx-4,wy+30);ctx.lineTo(wx-26,wy+wh);ctx.moveTo(wx+4,wy+30);ctx.lineTo(wx+26,wy+wh);ctx.moveTo(wx-14,wy+110);ctx.lineTo(wx+14,wy+110);ctx.moveTo(wx-20,wy+160);ctx.lineTo(wx+20,wy+160);ctx.stroke();
    ctx.beginPath();ctx.moveTo(wx,wy+6);ctx.lineTo(wx,wy+34);ctx.stroke();ctx.fillStyle='#ffd27a';for(let i=0;i<7;i++){ctx.fillRect(wx-ww/2+10+i*20,wy+wh-30+hash(i,3)*10,10,10)}}
  else{ctx.fillStyle='#0a0e22';ctx.fillRect(wx-ww/2,wy+wh-40,ww,40);ctx.beginPath();ctx.rect(wx-8,wy+wh-90,16,60);ctx.fill();
    for(let i=0;i<6;i++){ctx.beginPath();ctx.arc(wx-36+i*14,wy+wh-96-hash(i,5)*20,20,0,7);ctx.fill()}}
  ctx.fillStyle='#fff3d6';ctx.beginPath();ctx.arc(wx+(p?-42:38),wy+40,12,0,7);ctx.fill();ctx.restore();
  ctx.strokeStyle=mix(wall2,'#000000',0.35);ctx.lineWidth=8;rr(wx-ww/2,wy,ww,wh,10);ctx.stroke();ctx.lineWidth=4;ctx.beginPath();ctx.moveTo(wx,wy);ctx.lineTo(wx,wy+wh);ctx.moveTo(wx-ww/2,wy+wh*0.55);ctx.lineTo(wx+ww/2,wy+wh*0.55);ctx.stroke();
  // rideau
  ctx.fillStyle=p?'#e8d7c3':'#d9604a';ctx.fillRect(wx-ww/2-20,wy-12,22,wh+30);ctx.fillRect(wx+ww/2-2,wy-12,22,wh+30);
  // étagère + cadre
  const sx=a.left+(o.flip?a.w-250:40);ctx.fillStyle=mix(floor,'#000000',0.1);ctx.fillRect(sx,a.top+170,190,10);
  for(let i=0;i<6;i++){ctx.fillStyle=['#e4572e','#29a0b1','#f2c14e','#5e7ce2','#ef8354','#58b368'][i];ctx.fillRect(sx+10+i*16,a.top+130+hash(i,9)*8,12,40-hash(i,9)*8)}
  ctx.fillStyle=mix(wall2,'#000000',0.45);rr(sx+30,a.top+30,120,76,4);ctx.fill();ctx.fillStyle=p?'#f6d7a7':'#7cc4c8';rr(sx+38,a.top+38,104,60,2);ctx.fill();
  ctx.fillStyle=p?'#d9604a':'#f2c14e';ctx.beginPath();ctx.arc(sx+110,a.top+62,12,0,7);ctx.fill();
  // sol + plinthe + tapis
  ctx.fillStyle=floor;ctx.fillRect(a.left,a.floorY-8,a.w,48);ctx.fillStyle=mix(floor,'#000000',0.3);ctx.fillRect(a.left,a.floorY-8,a.w,6);
  ctx.fillStyle=p?'#5b6fa8':'#c4553b';rr(cx-250,a.floorY-2,420,14,7);ctx.fill();
  // canapé (assise sous le personnage)
  const sofaL=o.flip?cx-20:cx-300,sofaW=330;
  ctx.fillStyle=sofa2;rr(sofaL,a.floorY-140,sofaW,130,22);ctx.fill();ctx.fillStyle=sofa;rr(sofaL+(o.flip?0:-14),a.floorY-76,sofaW+14,60,18);ctx.fill();
  ctx.fillStyle=mix(sofa,'#ffffff',0.1);rr(sofaL+(o.flip?sofaW-110:30),a.floorY-92,80,50,14);ctx.fill();
  // lampe
  const lx=o.flip?a.right-70:a.left+60;ctx.strokeStyle='#2a2a3a';ctx.lineWidth=6;ctx.beginPath();ctx.moveTo(lx,a.floorY-8);ctx.lineTo(lx,a.floorY-250);ctx.stroke();
  ctx.fillStyle='#fff0c4';ctx.beginPath();ctx.moveTo(lx-36,a.floorY-250);ctx.lineTo(lx+36,a.floorY-250);ctx.lineTo(lx+24,a.floorY-300);ctx.lineTo(lx-24,a.floorY-300);ctx.fill();
  glowAt(lx,a.floorY-260,420,'rgba(255,200,120,0.8)',0.45);
  // plante
  const px=o.flip?a.left+50:a.right-60;ctx.fillStyle='#b5523b';ctx.beginPath();ctx.moveTo(px-24,a.floorY-60);ctx.lineTo(px+24,a.floorY-60);ctx.lineTo(px+16,a.floorY-8);ctx.lineTo(px-16,a.floorY-8);ctx.fill();
  ctx.fillStyle='#2f9e5e';for(let i=0;i<6;i++){const sw=Math.sin(t*1.2+i)*3;ctx.beginPath();ctx.ellipse(px+(i-2.5)*12+sw,a.floorY-100-hash(i,2)*28,10,34,(i-2.5)*0.25,0,7);ctx.fill()}
  // pénombre de la nuit
  ctx.fillStyle=`rgba(12,10,40,${dark})`;ctx.fillRect(a.left,a.top,a.w,a.h);
  ctx.restore();
  return a;
}

/* ---- océan et câble sous-marin ------------------------------------------------------------------------------------ */
const SEA={surface:900,landEnd:820,shoreEnd:1500,farShore:4500,parisShore:5200,deep:1850};
function seabed(x){
  if(x<SEA.landEnd)return SEA.surface;
  const a=seg(x,SEA.landEnd,SEA.shoreEnd),b=seg(x,SEA.farShore,SEA.parisShore);
  const base=lerp(SEA.surface,SEA.deep,io(a)),wob=(a>=1?1:a)*(1-b)*(46*Math.sin(x/430)+26*Math.sin(x/150+1));
  return lerp(base+wob,SEA.surface,io(b));
}
function cablePath(step=60){const pts=[];for(let x=SEA.landEnd;x<=SEA.parisShore;x+=step)pts.push([x,seabed(x)-10]);return pts}
function ocean(x0,x1,t,o={}){
  const s=SEA.surface;
  ctx.fillStyle=vgrad(0,s,2500,[[0,WC.sea0],[0.35,'#0a4a78'],[1,WC.sea1]]);ctx.fillRect(x0,s,x1-x0,2800);
  // rayons de lumière
  ctx.save();ctx.globalCompositeOperation='lighter';
  for(let i=0;i<14;i++){const bx=lerp(x0,x1,hash(i,21)),w=60+hash(i,22)*140,sway=Math.sin(t*0.35+i)*40;ctx.globalAlpha=0.05+0.04*hash(i,23);
    ctx.fillStyle=vgrad(0,s,s+1000,[[0,'#bfeaff'],[1,'rgba(0,0,0,0)']]);ctx.beginPath();ctx.moveTo(bx+sway,s);ctx.lineTo(bx+w+sway,s);ctx.lineTo(bx+w*2.4+sway*2,s+1000);ctx.lineTo(bx-w*0.4+sway*2,s+1000);ctx.fill()}
  ctx.restore();
  // fond marin
  ctx.beginPath();ctx.moveTo(x0,3600);for(let x=x0;x<=x1;x+=40)ctx.lineTo(x,seabed(x));ctx.lineTo(x1,3600);ctx.closePath();
  ctx.fillStyle=vgrad(0,1000,3000,[[0,WC.sand],[0.5,WC.sand2],[1,'#3a2c18']]);ctx.fill();
  ctx.fillStyle='rgba(4,26,51,0.45)';ctx.beginPath();ctx.moveTo(x0,3600);for(let x=x0;x<=x1;x+=40)ctx.lineTo(x,seabed(x)+30);ctx.lineTo(x1,3600);ctx.closePath();ctx.fill();
  // rochers + algues (seedés)
  for(let i=0;i<46;i++){const x=lerp(SEA.landEnd+300,SEA.parisShore-300,hash(i,31));if(x<x0-80||x>x1+80)continue;const y=seabed(x);
    if(hash(i,32)>0.5){ctx.fillStyle=mix('#4a5a6a','#0a1630',0.3+0.4*hash(i,33));ctx.beginPath();ctx.ellipse(x,y+6,26+hash(i,34)*40,16+hash(i,35)*20,0,Math.PI,0);ctx.fill()}
    else{ctx.strokeStyle='#2e9e6a';ctx.lineWidth=7;ctx.lineCap='round';for(let k=0;k<3;k++){const sw=Math.sin(t*1.4+i+k)*10;ctx.beginPath();ctx.moveTo(x+k*12,y+4);ctx.quadraticCurveTo(x+k*12+sw,y-40,x+k*12+sw*1.6,y-80-hash(i,k)*40);ctx.stroke()}}}
  // surface
  ctx.fillStyle='rgba(190,235,255,0.65)';ctx.beginPath();ctx.moveTo(x0,s);for(let x=x0;x<=x1;x+=20)ctx.lineTo(x,s+Math.sin(x/90+t*1.6)*5+Math.sin(x/37+t*2.3)*2.5);ctx.lineTo(x1,s+14);ctx.lineTo(x0,s+14);ctx.fill();
}
function seaCable(x0,x1,t,o={}){
  const pts=cablePath(40).filter(p=>p[0]>=x0-80&&p[0]<=x1+80);if(pts.length<2)return;
  const path=()=>{ctx.beginPath();ctx.moveTo(pts[0][0],pts[0][1]);for(const p of pts)ctx.lineTo(p[0],p[1])};
  ctx.save();ctx.lineCap='round';ctx.lineJoin='round';
  ctx.strokeStyle='#0b1220';ctx.lineWidth=14;path();ctx.stroke();
  ctx.strokeStyle=o.col||LC[3];ctx.lineWidth=4;ctx.shadowColor=o.col||LC[3];ctx.shadowBlur=22;ctx.globalAlpha=0.55+0.25*Math.sin(t*3);path();ctx.stroke();
  ctx.shadowBlur=0;ctx.globalAlpha=0.9;ctx.strokeStyle='#e9fbff';ctx.lineWidth=2;ctx.setLineDash([26,150]);ctx.lineDashOffset=-t*220;path();ctx.stroke();
  ctx.restore();
}
function fish(x,y,s,dir,t,col,id=0){
  ctx.save();ctx.translate(x,y);ctx.scale(dir*s,s);const wag=Math.sin(t*7+id*2)*0.35;ctx.fillStyle=col;
  ctx.beginPath();ctx.ellipse(0,0,26,12,0,0,7);ctx.fill();ctx.save();ctx.translate(-22,0);ctx.rotate(wag);ctx.beginPath();ctx.moveTo(0,0);ctx.lineTo(-20,-13);ctx.lineTo(-20,13);ctx.fill();ctx.restore();
  ctx.fillStyle='rgba(255,255,255,0.65)';ctx.beginPath();ctx.arc(14,-3,2.4,0,7);ctx.fill();ctx.restore();
}
function whale(x,y,s,dir,t,col='#173a5e'){
  ctx.save();ctx.translate(x,y);ctx.scale(dir*s,s);ctx.fillStyle=col;const w=Math.sin(t*1.1)*0.1;
  ctx.beginPath();ctx.moveTo(150,0);ctx.bezierCurveTo(120,-70,-40,-80,-140,-18);ctx.lineTo(-170,-46+w*60);ctx.lineTo(-196,-10);ctx.lineTo(-170,24+w*60);ctx.lineTo(-136,10);ctx.bezierCurveTo(-30,56,100,60,150,0);ctx.fill();
  ctx.fillStyle='rgba(255,255,255,0.12)';ctx.beginPath();ctx.moveTo(130,14);ctx.bezierCurveTo(60,50,-20,44,-90,26);ctx.bezierCurveTo(-10,30,70,26,130,14);ctx.fill();
  ctx.fillStyle='#bfd7ea';ctx.beginPath();ctx.arc(104,-14,3.6,0,7);ctx.fill();ctx.restore();
}
function boat(x,t,s=1){
  const y=SEA.surface+Math.sin(t*1.5+x)*4;ctx.save();ctx.translate(x,y);ctx.scale(s,s);ctx.rotate(Math.sin(t*1.2+x)*0.03);
  ctx.fillStyle='#3a2f55';ctx.beginPath();ctx.moveTo(-90,-26);ctx.lineTo(100,-26);ctx.lineTo(70,10);ctx.lineTo(-70,10);ctx.fill();
  ctx.fillStyle='#e9eefc';ctx.fillRect(-30,-70,60,44);ctx.fillStyle='#ffd27a';ctx.fillRect(-20,-60,14,14);ctx.fillRect(2,-60,14,14);
  ctx.fillStyle='#ff4a4a';ctx.fillRect(40,-100,6,74);glowAt(43,-104,60,'rgba(255,255,200,0.9)',0.5);ctx.restore();
}
/* petite station côtière où le câble sort de l'eau */
function landingStation(x,baseY,t){
  ctx.fillStyle='#2a3566';rr(x-70,baseY-86,140,86,6);ctx.fill();ctx.fillStyle='#394681';ctx.fillRect(x-80,baseY-96,160,16);
  ctx.fillStyle='#ffd27a';ctx.fillRect(x-50,baseY-62,20,22);ctx.fillRect(x-10,baseY-62,20,22);ctx.fillRect(x+30,baseY-62,20,22);
  for(let i=0;i<3;i++){ctx.fillStyle=hash(Math.floor(t*4),i)>0.5?LC[4]:'#1f3a2b';ctx.beginPath();ctx.arc(x-40+i*40,baseY-100,3.5,0,7);ctx.fill()}
}

/* ---- data center en coupe ---------------------------------------------------------------------------------------- */
function dataCenter(cx,baseY,t,o={}){
  const w=o.w||620,h=o.h||440,l=cx-w/2,top=baseY-h;
  ctx.fillStyle='#1a2350';rr(l-16,top-24,w+32,h+24,6);ctx.fill();
  ctx.fillStyle=vgrad(0,top,baseY,[[0,'#0d1430'],[1,'#141c42']]);ctx.fillRect(l,top,w,h-30);
  ctx.fillStyle='#0a0f26';ctx.fillRect(l,baseY-40,w,40);
  // plafond + chemin de câbles
  ctx.fillStyle='#2a3566';ctx.fillRect(l,top+10,w,18);for(let i=0;i<5;i++){ctx.fillStyle=[LC[3],LC[4],LC[6],LC[2],LC[7]][i];ctx.fillRect(l,top+30+i*5,w,3)}
  for(let i=0;i<4;i++)glowAt(l+80+i*150,top+30,120,'rgba(180,210,255,0.8)',0.18);
  // baies
  const n=5,rw=84,gap=(w-n*rw)/(n+1);
  for(let r=0;r<n;r++){const rx=l+gap+r*(rw+gap),ry=top+80,rh=h-130;
    ctx.fillStyle='#1c274f';rr(rx,ry,rw,rh,6);ctx.fill();ctx.fillStyle='#0b1230';rr(rx+6,ry+8,rw-12,rh-16,4);ctx.fill();
    const units=Math.floor((rh-24)/22);
    for(let u=0;u<units;u++){const uy=ry+14+u*22;ctx.fillStyle='#232f5e';ctx.fillRect(rx+10,uy,rw-20,17);
      for(let k=0;k<3;k++){const on=hash(Math.floor(t*(2+k))+u*3+r*17,k+5)>0.55;ctx.fillStyle=on?[LC[4],LC[3],LC[6]][k]:'#18203f';ctx.beginPath();ctx.arc(rx+18+k*9,uy+8.5,2.6,0,7);ctx.fill()}
      ctx.fillStyle='rgba(255,255,255,0.08)';ctx.fillRect(rx+rw-36,uy+5,22,2);ctx.fillRect(rx+rw-36,uy+10,22,2)}}
  ctx.fillStyle='rgba(180,210,255,0.08)';ctx.fillRect(l,baseY-44,w,4);
  return {left:l,right:l+w,top,baseY,mid:cx,racksY:top+80+(h-130)/2};
}


/* ---- personnage debout (le « guide ») ------------------------------------------------------------------------------ */
/* Origine = sol, entre les pieds ; visage vers +x. pose : 'stand' | 'wave' | 'point' | 'think' | 'cheer'. */
function personStand(x,y,o={}){
  const {s=1,skin=WC.skin.brown,hair='#150e0c',style='short',top='#ff8a5b',pants='#222a55',t=0,flip=false,id=0,pose='stand'}=o;
  ctx.save();ctx.translate(x,y);ctx.scale(flip?-s:s,s);
  const line=(a,b,w,c)=>{ctx.strokeStyle=c;ctx.lineWidth=w;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke()};
  const breathe=Math.sin(t*1.6+id)*1.6,sh=[0,-236+breathe],hd=[6,-298+breathe],hx=hd[0],hy=hd[1];
  ctx.fillStyle='rgba(0,0,0,0.2)';ctx.beginPath();ctx.ellipse(0,4,74,10,0,0,7);ctx.fill();
  // jambes + chaussures
  line([-14,-128],[-18,-16],32,pants);line([14,-128],[18,-16],32,pants);
  ctx.fillStyle='#f2f2f2';for(const fx of [-18,18]){ctx.beginPath();ctx.ellipse(fx+10,-7,27,11,0,0,7);ctx.fill()}
  // cheveux de derriere
  ctx.fillStyle=hair;
  if(style==='curly'){for(let k=0;k<11;k++){const a=Math.PI*(0.85+k*0.13);ctx.beginPath();ctx.arc(hx-4+Math.cos(a)*40,hy-4+Math.sin(a)*38,22,0,7);ctx.fill()}}
  else if(style==='braids'){ctx.beginPath();ctx.ellipse(hx-8,hy-6,41,40,0,0,7);ctx.fill();for(let k=0;k<5;k++)line([hx-30+k*6,hy+10],[hx-46+k*8,hy+96+k*3],8,hair)}
  else if(style==='bun'){ctx.beginPath();ctx.ellipse(hx-6,hy-4,40,40,0,0,7);ctx.fill();ctx.beginPath();ctx.arc(hx-18,hy-52,20,0,7);ctx.fill()}
  else{ctx.beginPath();ctx.ellipse(hx-6,hy-6,40,40,0,0,7);ctx.fill()}
  // bras lointain (derriere le torse), puis torse
  const arm=(sho,elb,hand,col,sleeve=26,fore=20)=>{line(sho,elb,sleeve,col);line(elb,hand,fore,skin);ctx.fillStyle=skin;ctx.beginPath();ctx.arc(hand[0],hand[1],12,0,7);ctx.fill()};
  const dark=mix(top,'#000000',0.18);
  const far=pose==='cheer'?[[-30,-340],[-28,-292]]:[[-16,-140],[-14,-190]];
  arm([-8,sh[1]+12],far[1],far[0],dark);
  line([0,-124],[0,sh[1]+4],66,top);ctx.fillStyle=dark;ctx.beginPath();ctx.arc(0,sh[1]+10,33,Math.PI,0);ctx.fill();
  // cou + tete + oreille + frange
  line([2,sh[1]-8],[hx-2,hy+30],24,skin);ctx.fillStyle=skin;ctx.beginPath();ctx.arc(hx,hy,38,0,7);ctx.fill();
  ctx.fillStyle=mix(skin,'#000000',0.12);ctx.beginPath();ctx.arc(hx-14,hy+6,9,0,7);ctx.fill();
  ctx.fillStyle=hair;ctx.beginPath();ctx.arc(hx-2,hy-4,40,Math.PI*1.02,Math.PI*1.82);ctx.lineTo(hx+30,hy-18);ctx.quadraticCurveTo(hx+8,hy-26,hx-34,hy-6);ctx.fill();
  // visage
  const bp=(t+id*1.3)%3.4,happy=pose==='cheer'||pose==='wave',closed=bp<0.13||pose==='cheer',ex=hx+17,ey=hy+(pose==='think'?-2:2);
  ctx.strokeStyle='#1a0f0b';ctx.lineWidth=4;ctx.lineCap='round';
  if(closed){ctx.beginPath();ctx.arc(ex,ey+(pose==='cheer'?4:0),6,Math.PI*1.1,Math.PI*1.9);ctx.stroke()}
  else{ctx.fillStyle='#1a0f0b';ctx.beginPath();ctx.ellipse(ex+(pose==='think'?2:0),ey-(pose==='think'?3:0),4.2,5.6,0,0,7);ctx.fill();ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(ex+2.5,ey-2,1.5,0,7);ctx.fill()}
  ctx.beginPath();ctx.moveTo(ex-9,ey-14);ctx.lineTo(ex+8,ey-14-(happy||pose==='think'?3:0));ctx.stroke();
  ctx.lineWidth=3.5;ctx.beginPath();
  if(happy){ctx.arc(hx+16,hy+16,13,0.15,Math.PI-0.55);ctx.stroke();ctx.fillStyle='rgba(255,120,110,0.28)';ctx.beginPath();ctx.arc(hx+8,hy+14,8,0,7);ctx.fill()}
  else if(pose==='think'){ctx.arc(hx+17,hy+24,5,0,7);ctx.stroke()}
  else{ctx.moveTo(hx+9,hy+22);ctx.quadraticCurveTo(hx+17,hy+25,hx+24,hy+21);ctx.stroke()}
  // bras proche selon la pose
  const nsh=[8,sh[1]+12];
  if(pose==='wave'){const el=[46,-252+breathe],a=-1.25+0.5*Math.sin(t*10),hand=[el[0]+58*Math.cos(a),el[1]+58*Math.sin(a)];arm(nsh,el,hand,top)}
  else if(pose==='point'){arm(nsh,[48,-216+breathe],[110,-226+breathe],top)}
  else if(pose==='think'){arm(nsh,[36,-186+breathe],[18,-262+breathe],top)}
  else if(pose==='cheer'){arm(nsh,[36,-292+breathe],[44,-342+breathe],top)}
  else{arm(nsh,[16,-190+breathe],[18,-140+breathe],top)}
  ctx.restore();
}
