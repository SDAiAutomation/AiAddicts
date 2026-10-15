/* scene.js — graphe de scène déclaratif : l'API que l'animateur (LLM) utilise. Il ne touche jamais au canvas.
   Un plan = une fonction build(S) qui déclare des éléments (S.add), leurs mouvements (h.to / h.set / h.appear),
   la caméra (S.cam), les bruitages (S.sfx). Tout est évalué à partir du temps `t` : renderAt reste pur.
   Coordonnées : celles du canevas à zoom 1 (0..1080 x 0..1920), centre de l'écran = (540, 960). */
const Faceloop=(()=>{
const EASE={lin:x=>x,io,out,inn,back};
const TOKEN={ink:C.ink,dim:C.dim,bg:C.bg,panel:C.panel,chip:C.chip,dark:C.dark,primary:LC[3],accent:LC[7],warm:LC[6],good:LC[4],violet:LC[1],blue:LC[2],yellow:LC[5],line:C.line,white:'#ffffff'};
const RUNTIME_ERRORS=[];
const COLOR_RE=/^(#[0-9a-f]{3,8}|rgba?\([^)]*\)|hsla?\([^)]*\))$/i;
/* Un jeton connu ou une couleur CSS valide. Une valeur invalide serait IGNOREE par le canvas (la couleur precedente
   reste active : c'est ainsi qu'un rectangle vert est apparu) : on la signale et on retombe sur 'ink'. */
const col=c=>{if(TOKEN[c])return TOKEN[c];if(typeof c==='string'&&COLOR_RE.test(c))return c;
  const m='couleur invalide : '+JSON.stringify(c);if(!RUNTIME_ERRORS.includes(m))RUNTIME_ERRORS.push(m);return TOKEN.ink};
const SKY={night:{top:'#070b1f',mid:'#18204f',low:'#3a2a66',stars:140},dusk:{top:'#1a1740',mid:'#6a3a7a',low:'#f08a5b',stars:40},day:{top:'#4aa3e8',mid:'#8cc9f5',low:'#dff1ff',stars:0},void:{top:C.bg,mid:C.bg,low:C.bg,stars:0}};

/* ---- éléments ----------------------------------------------------------------------------------------------- */
const COMMON={x:540,y:960,s:1,a:1,r:0,hud:false,par:1,layer:0};
const DEFAULTS={
  text:{text:'',size:64,weight:700,color:'ink',mono:false,glow:0,ls:0,maxW:0,lh:1.15},
  box:{w:200,h:100,r:16,color:'panel',stroke:'',sw:3},
  circle:{rad:40,color:'primary',stroke:'',sw:3,glow:0},
  line:{dx:200,dy:0,w:6,color:'primary',draw:1,dash:null,glow:0,head:false},
  polyline:{points:[],w:6,color:'primary',draw:1,glow:0,fill:''},
  chunk:{w:200,h:72,color:'accent',label:'',size:28,mono:true,glow:0,tc:''},
  bubble:{text:'',color:'accent',tc:'dark',size:40},
  phone:{contact:'Awa',avatar:'primary',input:'',press:0,bubbles:[]},
  miniphone:{label:'',glow:0},
  person:{pose:'sitPhone',skin:'#9a6240',hair:'#150e0c',style:'short',top:'#ff8a5b',pants:'#222a55',flip:false,typing:false,glow:0,pid:1},
  house:{palette:'dakar',flip:false,dark:0.25},
  tower:{h:470,act:0},
  city:{count:12,seed:1,far:false,minH:140,varH:280},
  router:{hot:0},
  antenna:{act:0},
  lock:{},
  datacenter:{w:620,h:440},
  water:{w:2000,h:1200},
  fish:{color:'#7fd6e6',dir:1},
  whale:{dir:1},
  boat:{},
  particles:{n:40,seed:1,w:1080,h:1920,speed:30,dirx:0,diry:-1,size:3,color:'white',alpha:0.5},
  counter:{value:0,decimals:0,prefix:'',suffix:'',size:120,color:'ink',sep:' ',glow:0},
  bars:{values:[],labels:[],w:600,h:400,color:'primary',grow:1,size:28},
  golden:{base:600,n:8,draw:8,color:'warm',w:4},
};
const NUMERIC_NONTWEEN=new Set(['pid','seed','count','n','decimals']);

function makeHandle(S,kind,props){
  if(!DEFAULTS[kind])throw new Error('element inconnu : '+kind);
  const BASE=Object.assign({},COMMON,DEFAULTS[kind]);
  const check=(k,v,where)=>{
    if(!(k in BASE)){S.errors.push(`propriété inconnue « ${k} » pour l'élément ${kind}${where}`);return undefined}
    const d=BASE[k];
    if(typeof d==='number'&&typeof v!=='number'){S.errors.push(`${kind}.${k} doit être un nombre (reçu ${JSON.stringify(v)})`);return undefined}
    if(typeof d==='boolean'&&typeof v!=='boolean'){S.errors.push(`${kind}.${k} doit être un booléen (reçu ${JSON.stringify(v)})`);return undefined}
    if(typeof d==='number'&&!isFinite(v)){S.errors.push(`${kind}.${k} n'est pas un nombre fini`);return undefined}
    return v};
  const clean={};for(const k in props||{}){const v=check(k,props[k],'');if(v!==undefined)clean[k]=v}
  const init=Object.assign({},BASE,clean);
  const h={kind,init,tl:{},order:S.items.length};
  const val=(p,t)=>{const L=h.tl[p];let v=init[p];if(!L)return v;
    for(const g of L){if(t>=g.t1)v=g.v1;else if(t>=g.t0){return typeof g.v0==='number'&&typeof g.v1==='number'?lerp(g.v0,g.v1,EASE[g.e](clamp((t-g.t0)/(g.t1-g.t0)))):g.v0}else break}return v};
  h.val=val;
  h.props=t=>{const o={};for(const k in init)o[k]=val(k,t);return o};
  const push=(p,g)=>{const L=h.tl[p]||(h.tl[p]=[]);L.push(g);L.sort((a,b)=>a.t0-b.t0)};
  h.set=(t,props)=>{for(const p in props){const v=check(p,props[p],' (set)');if(v===undefined)continue;push(p,{t0:t,t1:t,v0:v,v1:v,e:'lin'})}return h};
  h.to=(t0,t1,props,ease='io')=>{if(!(t1>t0))t1=t0+0.001;if(!EASE[ease])ease='io';
    for(const p in props){const v1=check(p,props[p],' (to)');if(v1===undefined)continue;const tween=typeof v1==='number'&&!NUMERIC_NONTWEEN.has(p);
      if(tween)push(p,{t0,t1,v0:val(p,t0),v1,e:ease});else push(p,{t0,t1:t0,v0:v1,v1,e:'lin'})}return h};
  h.appear=(t,dur=0.4,how='pop')=>{const x=init.x,y=init.y,s=init.s;init.a=0;
    h.to(t,t+dur,{a:1},'out');
    if(how==='pop'){init.s=s*0.7;h.to(t,t+dur,{s},'back')}
    else if(how==='up'){init.y=y+60;h.to(t,t+dur,{y},'out')}
    else if(how==='left'){init.x=x-90;h.to(t,t+dur,{x},'out')}
    else if(how==='right'){init.x=x+90;h.to(t,t+dur,{x},'out')}
    return h};
  h.hide=(t,dur=0.3)=>h.to(t,t+dur,{a:0},'inn');
  h.pulse=(t,amount=0.18,dur=0.35)=>{const s=val('s',t);h.to(t,t+dur*0.4,{s:s*(1+amount)},'out');h.to(t+dur*0.4,t+dur,{s},'io');return h};
  h.follow=(points,t0,t1,ease='io')=>{const q=EASE[ease]||io;h.pathFollow={points,t0,t1,q};return h};
  S.items.push(h);return h;
}

/* ---- dessin des éléments (autour de l'origine locale) ---------------------------------------------------------- */
function wrapLines(s){return String(s).split('\n')}
function fmtNum(v,p){const n=Math.abs(v).toFixed(p.decimals),[i,d]=n.split('.');const g=i.replace(/\B(?=(\d{3})+(?!\d))/g,p.sep);return (v<0?'-':'')+p.prefix+g+(d?','+d:'')+p.suffix}
const DRAW={
  text(p,t){const lines=wrapLines(p.text);let size=p.size;if(p.maxW){const w=Math.max(...lines.map(l=>measure(l,size,p.weight,p.mono?MONO:DISP)));if(w>p.maxW)size*=p.maxW/w}
    lines.forEach((l,i)=>T(l,0,(i-(lines.length-1)/2)*size*p.lh,{size,weight:p.weight,fam:p.mono?MONO:DISP,color:col(p.color),glow:p.glow,ls:p.ls}))},
  box(p){ctx.fillStyle=col(p.color);rr(-p.w/2,-p.h/2,p.w,p.h,p.r);ctx.fill();if(p.stroke){ctx.strokeStyle=col(p.stroke);ctx.lineWidth=p.sw;ctx.stroke()}},
  circle(p){ctx.save();if(p.glow){ctx.shadowColor=col(p.color);ctx.shadowBlur=p.glow}ctx.fillStyle=col(p.color);ctx.beginPath();ctx.arc(0,0,p.rad,0,7);ctx.fill();ctx.restore();
    if(p.stroke){ctx.strokeStyle=col(p.stroke);ctx.lineWidth=p.sw;ctx.beginPath();ctx.arc(0,0,p.rad,0,7);ctx.stroke()}},
  line(p){const e=clamp(p.draw),x=p.dx*e,y=p.dy*e;ctx.save();ctx.strokeStyle=col(p.color);ctx.lineWidth=p.w;ctx.lineCap='round';if(p.glow){ctx.shadowColor=col(p.color);ctx.shadowBlur=p.glow}
    if(p.dash)ctx.setLineDash(p.dash);ctx.beginPath();ctx.moveTo(0,0);ctx.lineTo(x,y);ctx.stroke();ctx.setLineDash([]);
    if(p.head&&e>0.02){const a=Math.atan2(p.dy,p.dx),L=p.w*3.2;ctx.fillStyle=col(p.color);ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x-L*Math.cos(a-0.45),y-L*Math.sin(a-0.45));ctx.lineTo(x-L*Math.cos(a+0.45),y-L*Math.sin(a+0.45));ctx.fill()}ctx.restore()},
  polyline(p){const pts=p.points;if(!pts||pts.length<2)return;const e=clamp(p.draw),n=(pts.length-1)*e,k=Math.floor(n),f=n-k,drawn=pts.slice(0,k+1);
    if(k+1<pts.length&&f>0)drawn.push([lerp(pts[k][0],pts[k+1][0],f),lerp(pts[k][1],pts[k+1][1],f)]);if(drawn.length<2)return;
    ctx.save();ctx.lineCap='round';ctx.lineJoin='round';
    if(p.fill){ctx.beginPath();ctx.moveTo(drawn[0][0],0);for(const q of drawn)ctx.lineTo(q[0],q[1]);ctx.lineTo(drawn[drawn.length-1][0],0);ctx.closePath();ctx.globalAlpha*=0.22;ctx.fillStyle=col(p.fill);ctx.fill();ctx.globalAlpha/=0.22}
    ctx.strokeStyle=col(p.color);ctx.lineWidth=p.w;if(p.glow){ctx.shadowColor=col(p.color);ctx.shadowBlur=p.glow}
    ctx.beginPath();ctx.moveTo(drawn[0][0],drawn[0][1]);for(const q of drawn)ctx.lineTo(q[0],q[1]);ctx.stroke();ctx.restore()},
  chunk(p){chunk(-p.w/2,0,p.w,p.h,col(p.color),p.label,{size:p.size,fam:p.mono?MONO:DISP,glow:p.glow,tc:p.tc?col(p.tc):undefined})},
  bubble(p){const w=measure(p.text,p.size,600)+p.size*1.9,h=p.size*2.5;ctx.fillStyle=col(p.color);rr(-w/2,-h/2,w,h,h*0.4);ctx.fill();T(p.text,0,2,{size:p.size,weight:600,color:col(p.tc)})},
  phone(p){phone(0,0,{contact:p.contact,avatar:col(p.avatar),input:p.input,press:p.press,bubbles:(p.bubbles||[]).map(b=>({...b,col:col(b.col||'chip'),tc:col(b.tc||'ink')}))})},
  miniphone(p){miniPhone(0,0,p.label,p.glow)},
  person(p,t){person(0,0,{s:1,skin:col(p.skin),hair:col(p.hair),style:p.style,top:col(p.top),pants:col(p.pants),pose:p.pose,flip:p.flip,typing:p.typing,glow:p.glow,id:p.pid,t})},
  house(p,t){house(0,0,{palette:p.palette,flip:p.flip,dark:p.dark,t})},
  tower(p,t){tower(0,0,p.h,{t,act:p.act})},
  city(p){city(0,0,p.count,{seed:p.seed,far:p.far,minH:p.minH,varH:p.varH})},
  router(p){router(0,0,p.hot)},
  antenna(p,t){antenna(0,0,p.act,t)},
  lock(){lock(0,0,1,1)},
  datacenter(p,t){dataCenter(0,0,t,{w:p.w,h:p.h})},
  water(p,t){const x0=-p.w/2;ctx.fillStyle=vgrad(0,0,p.h,[[0,WC.sea0],[0.4,'#0a4a78'],[1,WC.sea1]]);ctx.fillRect(x0,0,p.w,p.h);
    ctx.save();ctx.globalCompositeOperation='lighter';for(let i=0;i<8;i++){const bx=x0+hash(i,21)*p.w,w=50+hash(i,22)*100,sw=Math.sin(t*0.35+i)*30;ctx.globalAlpha=0.06;ctx.fillStyle=vgrad(0,0,p.h*0.8,[[0,'#bfeaff'],[1,'rgba(0,0,0,0)']]);ctx.beginPath();ctx.moveTo(bx+sw,0);ctx.lineTo(bx+w+sw,0);ctx.lineTo(bx+w*2.2+sw*2,p.h*0.8);ctx.lineTo(bx-w*0.4+sw*2,p.h*0.8);ctx.fill()}ctx.restore();
    ctx.fillStyle='rgba(190,235,255,0.65)';ctx.beginPath();ctx.moveTo(x0,0);for(let x=x0;x<=x0+p.w;x+=16)ctx.lineTo(x,Math.sin(x/90+t*1.6)*5);ctx.lineTo(x0+p.w,12);ctx.lineTo(x0,12);ctx.fill()},
  fish(p,t){fish(0,0,1,p.dir,t,col(p.color),0)},
  whale(p,t){whale(0,0,1,p.dir,t)},
  boat(p,t){const y=SEA.surface;ctx.translate(0,-y);boat(0,t,1)},
  particles(p,t){ctx.fillStyle=col(p.color);const a=p.alpha;for(let i=0;i<Math.min(p.n,400);i++){const x=(((hash(i,61)*p.w+t*p.speed*p.dirx*(0.5+hash(i,62)))%p.w)+p.w)%p.w,y=(((hash(i,63)*p.h+t*p.speed*p.diry*(0.5+hash(i,62)))%p.h)+p.h)%p.h;
    ctx.globalAlpha=a*(0.3+0.7*hash(i,64));ctx.beginPath();ctx.arc(x-p.w/2,y-p.h/2,p.size*(0.5+hash(i,65)),0,7);ctx.fill()}ctx.globalAlpha=1},
  counter(p){T(fmtNum(p.value,p),0,0,{size:p.size,weight:800,color:col(p.color),fam:MONO,glow:p.glow})},
  bars(p){const n=p.values.length;if(!n)return;const mx=Math.max(...p.values,1e-9),bw=p.w/n*0.62,gap=p.w/n;
    for(let i=0;i<n;i++){const hh=p.h*(p.values[i]/mx)*clamp(p.grow*1.0),x=-p.w/2+gap*i+(gap-bw)/2;ctx.fillStyle=col(p.color);rr(x,-hh,bw,Math.max(hh,1),Math.min(10,bw/2));ctx.fill();
      if(p.labels[i])T(String(p.labels[i]),x+bw/2,26,{size:p.size,weight:600,color:C.dim,fam:MONO})}},
  golden(p){const PHI=1.6180339887,n=Math.floor(p.draw),f=p.draw-n;let x=-p.base/2,y=-p.base/PHI/2,w=p.base,h=p.base/PHI;ctx.save();ctx.lineWidth=p.w;ctx.strokeStyle=col(p.color);ctx.lineCap='round';
    for(let i=0;i<Math.min(p.n,10);i++){const side=Math.min(w,h),k=(i<n)?1:(i===n?f:0);if(k<=0)break;const dir=i%4;let cx,cy,a0;
      if(dir===0){cx=x+side;cy=y+side;a0=Math.PI;x+=side;w-=side}else if(dir===1){cx=x;cy=y+side;a0=1.5*Math.PI;y+=side;h-=side}else if(dir===2){cx=x+w-side;cy=y;a0=0;w-=side}else{cx=x+side;cy=y+h-side;a0=0.5*Math.PI;h-=side}
      ctx.globalAlpha=0.3;ctx.strokeRect(dir===0?x-side:dir===2?x+w:x,dir===1?y-side:dir===3?y+h:y,side,side);ctx.globalAlpha=1;ctx.beginPath();ctx.arc(cx,cy,side,a0,a0+Math.PI/2*k);ctx.stroke()}ctx.restore()},
};

/* ---- scène d'un plan ----------------------------------------------------------------------------------------- */
function makeScene(plan){
  const S={dur:plan.duration,items:[],sounds:[],skyKind:'void',gridOn:false,fades:[],anchors:plan.anchors||{},errors:[]};
  const camInit={x:540,y:960,z:1,r:0},ctl={};
  S.cam={init:camInit,tl:{}};
  const cval=(p,t)=>{const L=S.cam.tl[p];let v=camInit[p];if(!L)return v;for(const g of L){if(t>=g.t1)v=g.v1;else if(t>=g.t0)return lerp(g.v0,g.v1,EASE[g.e](clamp((t-g.t0)/(g.t1-g.t0))));else break}return v};
  S.cam.at=t=>({x:cval('x',t),y:cval('y',t),z:cval('z',t),r:cval('r',t)});
  S.cam.set=(t,o)=>{for(const p in o){(S.cam.tl[p]||(S.cam.tl[p]=[])).push({t0:t,t1:t,v0:o[p],v1:o[p],e:'lin'});S.cam.tl[p].sort((a,b)=>a.t0-b.t0)}return S.cam};
  S.cam.to=(t0,t1,o,ease='io')=>{if(!(t1>t0))t1=t0+0.001;if(!EASE[ease])ease='io';for(const p in o){const L=S.cam.tl[p]||(S.cam.tl[p]=[]);L.push({t0,t1,v0:cval(p,t0),v1:o[p],e:ease});L.sort((a,b)=>a.t0-b.t0)}return S.cam};
  S.t=id=>{if(!(id in S.anchors)){S.errors.push('ancre inconnue : '+id);return 0}return S.anchors[id]};
  S.sky=k=>{S.skyKind=SKY[k]?k:'void'};
  S.grid=on=>{S.gridOn=!!on};
  S.add=(kind,props)=>makeHandle(S,kind,props);
  S.sfx=(t,type)=>{S.sounds.push({at:t,type})};
  S.fade=(t0,t1,color='bg',dir='in')=>{S.fades.push({t0,t1,color,dir})};
  return S;
}
function posOf(h,t){const p=h.props(t);if(h.pathFollow){const f=h.pathFollow,q=f.q(clamp((t-f.t0)/(f.t1-f.t0)));const [x,y]=polyPos(f.points,q);p.x=x;p.y=y}return p}
function drawScene(S,t){
  const cam=S.cam.at(t),sk=SKY[S.skyKind];
  screen();
  if(S.skyKind==='void'&&S.gridOn)background(null);
  else{ctx.fillStyle=vgrad(0,0,H,[[0,sk.top],[0.7,sk.mid],[1,sk.low]]);ctx.fillRect(0,0,W,H);
    for(let i=0;i<sk.stars;i++){const tw=0.5+0.5*Math.sin(t*(1+hash(i,13)*2)+i);ctx.globalAlpha=0.2+0.5*tw*hash(i,14);ctx.fillStyle='#fff';ctx.fillRect(hash(i,11)*W,hash(i,12)*H*0.7,2.5,2.5)}ctx.globalAlpha=1}
  const list=S.items.slice().sort((a,b)=>(a.init.layer-b.init.layer)||(a.order-b.order));
  for(const h of list){const p=posOf(h,t);if(p.a<=0.003)continue;
    ctx.save();
    if(p.hud){screen()}else{const z=lerp(1,cam.z,p.par),cx=540+(cam.x-540)*p.par;cameraR({x:cx,y:960+(cam.y-960)*p.par,z,r:(cam.r||0)*p.par});}
    ctx.translate(p.x,p.y);if(p.r)ctx.rotate(p.r);if(p.s!==1)ctx.scale(p.s,p.s);ctx.globalAlpha*=clamp(p.a);
    try{DRAW[h.kind](p,t)}catch(e){const m=h.kind+' : '+e.message;if(!RUNTIME_ERRORS.includes(m))RUNTIME_ERRORS.push(m)}
    ctx.restore();}
  screen();for(const f of S.fades){const a=f.dir==='in'?1-seg(t,f.t0,f.t1):seg(t,f.t0,f.t1);overlay(col(f.color),a)}
}

/* ---- vidéo : plans mis bout à bout ---------------------------------------------------------------------------- */
function define(spec){
  const fps=spec.fps||30,plans=[];let cursor=0;window.__buildErrors=[];
  for(const pl of spec.plans){const start=pl.start??cursor,P={id:pl.id,start,duration:pl.duration,anchors:pl.anchors||{},transition:pl.transition||{}};cursor=start+pl.duration;
    const S=makeScene(P);try{pl.build(S)}catch(e){window.__buildErrors.push({plan:pl.id,message:String(e&&e.message||e)})}
    for(const m of S.errors)window.__buildErrors.push({plan:pl.id,message:m});
    plans.push({P,S})}
  const duration=spec.duration||cursor,sfx=[];
  for(const {P,S} of plans)for(const s of S.sounds)sfx.push({at:P.start+s.at,type:s.type,k:s.k||0});
  sfx.sort((a,b)=>a.at-b.at);
  window.__runtimeErrors=RUNTIME_ERRORS;
  window.VIDEO={duration,fps,narration:spec.narration||[],sfx,plans:plans.map(({P})=>({id:P.id,start:P.start,duration:P.duration}))};
  window.renderAt=t=>{t=clamp(t,0,duration);screen();ctx.globalAlpha=1;ctx.setLineDash([]);ctx.fillStyle='#000';ctx.fillRect(0,0,W,H);
    let cur=plans[plans.length-1];for(const q of plans)if(t<q.P.start+q.P.duration){cur=q;break}
    const lt=t-cur.P.start;drawScene(cur.S,lt);
    const tr=cur.P.transition,dIn=tr.in??0,dOut=tr.out??0;   // fondus aux raccords : { in: 0.3, out: 0.3 }
    if(dIn>0)overlay(col(tr.color||'bg'),1-seg(lt,0,dIn));if(dOut>0)overlay(col(tr.color||'bg'),seg(lt,cur.P.duration-dOut,cur.P.duration));
    screen();const v=ctx.createRadialGradient(W/2,H/2,H*0.32,W/2,H/2,H*0.78);v.addColorStop(0,'rgba(0,0,0,0)');v.addColorStop(1,'rgba(0,0,0,0.34)');ctx.fillStyle=v;ctx.fillRect(0,0,W,H)};
}
return {define,EASE,TOKEN,DEFAULTS};
})();
