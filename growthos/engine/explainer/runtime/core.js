/* core.js — canvas, palette, maths, keyframes, camera, texte, fond, overlay
   Extrait tel quel du prototype reference/voyage-message.html (phase 1) : aucun changement de comportement. */
const cv=document.getElementById('c'),ctx=cv.getContext('2d');
const W=1080,H=1920;
const C={bg:'#0a0f1c',panel:'#161f37',screen:'#0c1326',chip:'#18223b',ink:'#e9eefc',dim:'rgba(233,238,252,0.58)',line:'rgba(150,175,255,0.22)',dark:'#0a0f1c'};
const LC={7:'#ff8a5b',6:'#ffb547',5:'#e6d35e',4:'#6fd38a',3:'#49c6e5',2:'#7b93ff',1:'#b884ff'};
const DISP='"Bricolage Grotesque", "Inter", system-ui, sans-serif', MONO='"JetBrains Mono", "DejaVu Sans Mono", ui-monospace, monospace';

const clamp=(x,a=0,b=1)=>x<a?a:x>b?b:x;
const lerp=(a,b,p)=>a+(b-a)*p;
const seg=(t,a,b)=>clamp((t-a)/(b-a));
const io=x=>{x=clamp(x);return x<.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2};
const out=x=>1-Math.pow(1-clamp(x),3);
const inn=x=>Math.pow(clamp(x),3);
const back=x=>{x=clamp(x);const c=1.7;return 1+(c+1)*Math.pow(x-1,3)+c*Math.pow(x-1,2)};
const hash=(a,b=0)=>{let h=Math.imul((a|0)*374761393+(b|0)*668265263,1274126177);h^=h>>>13;h=Math.imul(h,1274126177);return((h^(h>>>16))>>>0)/4294967296};
/* keyframes: [[time, number|{...}, ease?]] — ease applies to the segment ending at that key */
function kf(t,keys,def=io){
  if(t<=keys[0][0])return keys[0][1];
  for(let i=1;i<keys.length;i++){const [t1,v1,e]=keys[i],[t0,v0]=keys[i-1];
    if(t<=t1){const p=(e||def)(seg(t,t0,t1));if(typeof v0==='number')return lerp(v0,v1,p);const o={};for(const k in v0)o[k]=lerp(v0[k],v1[k],p);return o}}
  return keys[keys.length-1][1];
}
const camera=c=>ctx.setTransform(c.z,0,0,c.z,W/2-c.x*c.z,H/2-c.y*c.z);
const screen=()=>ctx.setTransform(1,0,0,1,0,0);
function T(s,x,y,o={}){
  const {size=40,weight=700,fam=DISP,color=C.ink,alpha=1,align='center',base='middle',ls=0,glow=0}=o;
  if(alpha<=0.002||!s)return;ctx.save();ctx.globalAlpha*=alpha;ctx.fillStyle=color;
  ctx.font=`${weight} ${size}px ${fam}`;ctx.textAlign=align;ctx.textBaseline=base;
  if('letterSpacing' in ctx)ctx.letterSpacing=ls+'px';
  if(glow){ctx.shadowColor=color;ctx.shadowBlur=glow}
  ctx.fillText(s,x,y);ctx.restore();
}
function rr(x,y,w,h,r){ctx.beginPath();if(ctx.roundRect)ctx.roundRect(x,y,w,h,Math.min(r,h/2,w/2));else ctx.rect(x,y,w,h)}
function measure(s,size,weight=700,fam=DISP){ctx.save();ctx.font=`${weight} ${size}px ${fam}`;const w=ctx.measureText(s).width;ctx.restore();return w}
function background(cam){
  screen();ctx.fillStyle=C.bg;ctx.fillRect(0,0,W,H);
  const z=cam?cam.z:1,step=64*clamp(0.55+z*0.45,0.8,3);
  const ox=cam?-cam.x*z*0.4:0,oy=cam?-cam.y*z*0.4:0;
  const sx=((ox%step)+step)%step,sy=((oy%step)+step)%step;
  ctx.fillStyle='rgba(150,175,255,0.09)';
  for(let x=sx;x<W;x+=step)for(let y=sy;y<H;y+=step)ctx.fillRect(x-1.5,y-1.5,3,3);
  const g=ctx.createRadialGradient(W/2,H*0.42,150,W/2,H*0.5,1250);
  g.addColorStop(0,'rgba(70,100,200,0.10)');g.addColorStop(1,'rgba(0,0,0,0.5)');ctx.fillStyle=g;ctx.fillRect(0,0,W,H);
}
function overlay(color,a){if(a<=0)return;screen();ctx.save();ctx.globalAlpha=clamp(a);ctx.fillStyle=color;ctx.fillRect(0,0,W,H);ctx.restore()}

/* Point d'entree unique d'une image : repart d'un contexte 2D vierge (ctx.reset()) avant renderAt(t).
   Sans cela, un reglage laisse hors save()/restore() par une scene (ex. lineCap) fuit sur les images rendues apres,
   et renderAt(t) cesse d'etre pur. Trouve en phase 1 : le prototype fuyait lineCap='round' de la scene 3. */
function renderFrame(t){ctx.reset();renderAt(t)}
