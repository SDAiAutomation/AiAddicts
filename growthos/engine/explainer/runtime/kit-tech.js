/* kit-tech.js — primitives : blocs de protocole, telephone, bulle, antenne, routeur, pilule, cadenas
   Extrait tel quel du prototype reference/voyage-message.html (phase 1) : aucun changement de comportement. */
/* a protocol block: x = left edge, y = centre */
function chunk(x,y,w,h,col,label,o={}){
  const a=o.alpha??1;if(a<=0.002)return;ctx.save();ctx.globalAlpha*=a;
  if(o.glow){ctx.shadowColor=col;ctx.shadowBlur=o.glow}
  ctx.fillStyle=col;rr(x,y-h/2,w,h,o.r??12);ctx.fill();ctx.shadowBlur=0;
  ctx.fillStyle='rgba(255,255,255,0.18)';ctx.fillRect(x+10,y-h/2+5,w-20,2);
  ctx.restore();
  T(label,x+w/2,y+2,{size:o.size||24,weight:700,fam:o.fam||MONO,color:o.tc||C.dark,alpha:a});
}
/* a row of blocks; each item {w,col,label,p} slides in (p 0→1) or out (p 1→0) from its side */
function row(cx,cy,items,h){
  let total=-10;for(const it of items)total+=(it.w+10)*out(it.p);
  let x=cx-total/2;
  for(const it of items){if(it.p<=0.001)continue;const p=out(it.p);
    const off=(1-p)*(it.from==='right'?420:-420)+(it.dy?0:0);
    chunk(x+off,cy-(it.lift||0)*(1-p),it.w,h,it.col,it.label,{alpha:clamp(it.p*1.5),fam:it.fam,size:it.size,glow:it.glow});
    x+=(it.w+10)*p;}
}
function phone(cx,cy,o){
  const w=o.w||560,h=o.h||1100,x=cx-w/2,y=cy-h/2;
  ctx.save();ctx.shadowColor='rgba(0,0,0,0.55)';ctx.shadowBlur=70;ctx.fillStyle=C.panel;rr(x,y,w,h,74);ctx.fill();ctx.restore();
  ctx.strokeStyle='rgba(255,255,255,0.14)';ctx.lineWidth=3;rr(x,y,w,h,74);ctx.stroke();
  ctx.fillStyle=C.screen;rr(x+16,y+16,w-32,h-32,60);ctx.fill();
  ctx.fillStyle=C.panel;rr(cx-70,y+32,140,30,15);ctx.fill();
  const hy=y+130;ctx.fillStyle=o.avatar;ctx.beginPath();ctx.arc(x+82,hy,32,0,7);ctx.fill();
  T(o.contact[0],x+82,hy+2,{size:32,weight:800,color:C.dark});
  T(o.contact,x+130,hy-8,{size:36,weight:700,align:'left'});
  T(o.status||'en ligne',x+130,hy+26,{size:22,weight:500,align:'left',color:C.dim});
  ctx.fillStyle='rgba(255,255,255,0.07)';ctx.fillRect(x+16,hy+60,w-32,2);
  const iy=y+h-108;ctx.fillStyle=C.chip;rr(x+40,iy-36,w-172,72,36);ctx.fill();
  T(o.input||'Message',x+72,iy+1,{size:30,weight:500,align:'left',color:o.input?C.ink:'rgba(233,238,252,0.35)'});
  const s=1+(o.press||0)*0.22;ctx.save();ctx.translate(x+w-82,iy);ctx.scale(s,s);
  ctx.fillStyle=LC[7];ctx.beginPath();ctx.arc(0,0,38,0,7);ctx.fill();
  ctx.fillStyle=C.dark;ctx.beginPath();ctx.moveTo(-13,-16);ctx.lineTo(19,0);ctx.lineTo(-13,16);ctx.lineTo(-7,0);ctx.closePath();ctx.fill();ctx.restore();
  for(const b of o.bubbles||[])bubble(b);
  if(o.after)o.after(x,y,w,h);
}
function bubble({edge,y,text,side,alpha=1,col,tc=C.dark,s=1}){
  if(alpha<=0.002)return;const w=measure(text,34,600)+64,h=88,x=side==='right'?edge-w:edge;
  ctx.save();ctx.globalAlpha*=alpha;ctx.translate(x+w/2,y);ctx.scale(s,s);
  ctx.fillStyle=col;rr(-w/2,-h/2,w,h,34);ctx.fill();ctx.restore();
  ctx.save();ctx.globalAlpha*=alpha;ctx.translate(x+w/2,y);ctx.scale(s,s);T(text,0,2,{size:34,weight:600,color:tc});ctx.restore();
}
function miniPhone(x,y,label,glow=0){
  ctx.save();if(glow){ctx.shadowColor=LC[3];ctx.shadowBlur=60*glow}
  ctx.fillStyle=C.panel;rr(x-62,y-112,124,224,26);ctx.fill();ctx.restore();
  ctx.fillStyle=C.screen;rr(x-52,y-100,104,200,18);ctx.fill();
  ctx.fillStyle=LC[7];rr(x-30,y-30,70,28,12);ctx.fill();
  T(label,x,y+150,{size:28,weight:700,color:C.dim});
}
function antenna(x,y,act=0,t=0){
  ctx.save();ctx.strokeStyle='rgba(233,238,252,0.75)';ctx.lineWidth=5;ctx.lineCap='round';
  ctx.beginPath();ctx.moveTo(x,y-90);ctx.lineTo(x-42,y+70);ctx.moveTo(x,y-90);ctx.lineTo(x+42,y+70);
  ctx.moveTo(x-28,y+18);ctx.lineTo(x+28,y+18);ctx.moveTo(x-16,y-30);ctx.lineTo(x+16,y-30);ctx.stroke();
  ctx.fillStyle=LC[1];ctx.beginPath();ctx.arc(x,y-96,11,0,7);ctx.fill();
  if(act>0){ctx.strokeStyle=LC[1];ctx.lineWidth=4;for(let k=0;k<3;k++){const r=((t*1.6+k/3)%1);ctx.globalAlpha=act*(1-r);
    ctx.beginPath();ctx.arc(x,y-96,24+r*90,-2.4,-0.74);ctx.stroke();}}
  ctx.restore();
}
function router(x,y,hot=0){
  ctx.save();ctx.shadowColor=LC[3];ctx.shadowBlur=40*hot;ctx.fillStyle='#101a30';ctx.beginPath();ctx.arc(x,y,44,0,7);ctx.fill();ctx.restore();
  ctx.strokeStyle=hot>0?LC[3]:'rgba(73,198,229,0.55)';ctx.lineWidth=4;ctx.beginPath();ctx.arc(x,y,44,0,7);ctx.stroke();
  ctx.strokeStyle='rgba(233,238,252,0.8)';ctx.lineWidth=4;ctx.lineCap='round';
  for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]){ctx.beginPath();ctx.moveTo(x+dx*8,y+dy*8);ctx.lineTo(x+dx*24,y+dy*24);ctx.stroke();
    ctx.beginPath();ctx.moveTo(x+dx*24+dy*7,y+dy*24-dx*7);ctx.lineTo(x+dx*30,y+dy*30);ctx.lineTo(x+dx*24-dy*7,y+dy*24+dx*7);ctx.stroke();}
}
function polyPos(pts,p){
  let L=0;const d=[];for(let i=1;i<pts.length;i++){const l=Math.hypot(pts[i][0]-pts[i-1][0],pts[i][1]-pts[i-1][1]);d.push(l);L+=l}
  let s=clamp(p)*L;for(let i=0;i<d.length;i++){if(s<=d[i]){const q=s/d[i];return[lerp(pts[i][0],pts[i+1][0],q),lerp(pts[i][1],pts[i+1][1],q)]}s-=d[i]}
  return pts[pts.length-1];
}
function pill(s,x,y,col,a){
  if(a<=0.002)return;const w=measure(s,36,700)+70;ctx.save();ctx.globalAlpha*=a;
  ctx.fillStyle='rgba(16,24,44,0.9)';rr(x-w/2,y-38,w,76,38);ctx.fill();ctx.strokeStyle=col;ctx.lineWidth=3;rr(x-w/2,y-38,w,76,38);ctx.stroke();ctx.restore();
  T(s,x,y+2,{size:36,weight:700,alpha:a});
}
function lock(x,y,s,a){
  if(a<=0)return;ctx.save();ctx.globalAlpha*=a;ctx.translate(x,y);ctx.scale(s,s);
  ctx.strokeStyle=LC[6];ctx.lineWidth=9;ctx.beginPath();ctx.arc(0,-14,22,Math.PI,0);ctx.lineTo(22,4);ctx.moveTo(-22,4);ctx.lineTo(-22,-14);ctx.stroke();
  ctx.fillStyle=LC[6];rr(-34,0,68,52,10);ctx.fill();ctx.fillStyle=C.dark;ctx.beginPath();ctx.arc(0,22,8,0,7);ctx.fill();ctx.restore();
}


/* Remplace progressivement src par dst en passant par des glyphes qui clignotent (chiffrement / dechiffrement). */
function scramble(src,dst,p,l,k){
  const G='#%&@$*+=?!<>0123456789ABCDEFxzq';let s='';const n=src.length;
  for(let i=0;i<n;i++){const c=i/n;if(p>=1||p>c+0.18)s+=dst[i];else if(p>c)s+=G[Math.floor(hash(i,Math.floor(l*16)+k)*G.length)];else s+=src[i]}
  return s;
}
/* En-tete d'etapes : grand numero, nom, role, pastilles a droite. stages=[{n,name,role,col,t}] ; l = temps local. */
function stageHud(l,stages,eyebrow){
  screen();const g=ctx.createLinearGradient(0,0,0,640);g.addColorStop(0,'rgba(10,15,28,0.96)');g.addColorStop(0.7,'rgba(10,15,28,0.75)');g.addColorStop(1,'rgba(10,15,28,0)');
  ctx.fillStyle=g;ctx.fillRect(0,0,W,640);T(eyebrow,76,168,{size:26,fam:MONO,weight:700,color:C.dim,align:'left',ls:6});
  for(let i=0;i<stages.length;i++){const s=stages[i],e=s.t,ne=i+1<stages.length?stages[i+1].t:999;
    const a=out(seg(l,e,e+0.45))*(1-seg(l,ne-0.45,ne-0.05));if(a<=0)continue;const dy=(1-a)*36;
    T(String(s.n),66,330+dy,{size:250,weight:800,color:s.col,align:'left',alpha:a,glow:30});
    T(s.name,250,282+dy,{size:72,weight:800,align:'left',alpha:a,ls:-1});T(s.role,252,366+dy,{size:40,weight:500,color:C.dim,align:'left',alpha:a});}
  let cur=0;for(let i=0;i<stages.length;i++)if(l>=stages[i].t)cur=i;
  for(let i=0;i<stages.length;i++){const y=600+i*120,on=i===cur;ctx.fillStyle=stages[i].col;ctx.globalAlpha=on?1:0.28;ctx.beginPath();ctx.arc(1024,y,on?15:9,0,7);ctx.fill();ctx.globalAlpha=1;
    if(on){ctx.strokeStyle=stages[i].col;ctx.lineWidth=3;ctx.beginPath();ctx.arc(1024,y,26,0,7);ctx.stroke()}}
}
