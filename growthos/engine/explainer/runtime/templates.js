/* templates.js — gabarits de scène : des compositions DÉJÀ bien dessinées (centrées, grandes, animées) que l'animateur
   instancie avec des paramètres et des temps (S.template('equation', {...})). Ils remplissent le cadre et évitent les
   défauts récurrents des plans composés à la main (contenu petit, collé en haut, moitié basse vide).
   Tous les temps sont LOCAUX au plan. Un élément prévu pour t <= 0,05 est visible dès la première image. */
(()=>{
const reg=Faceloop.registerTemplate;
const enter=(h,t,how='up',dur=0.45)=>{if((t??0)<=0.05)return h;return h.appear(t,dur,how)};
const need=(p,key,type)=>{if(type==='array'?!Array.isArray(p[key])||!p[key].length:typeof p[key]!==type)throw new Error(`paramètre « ${key} » (${type==='array'?'tableau non vide':type}) manquant`);};
const clampI=(v,a,b)=>Math.max(a,Math.min(b,v));

/* Carte titre : {text, sub?, t=0, color='ink', subColor='dim', y=820, hide?} */
reg('title',(S,p)=>{need(p,'text','string');
  const a=enter(S.add('text',{text:p.text,x:540,y:p.y??820,size:p.size??140,weight:800,color:p.color||'ink',maxW:900,glow:p.glow??18,lh:1.1}),p.t??0,'pop');
  const out=[a];
  const fx=S.add('particles',{x:540,y:960,n:70,seed:5,w:1080,h:1920,speed:18,diry:-1,size:3.5,color:p.color==='accent'?'warm':'primary',alpha:0.45,layer:-2});out.push(fx);
  const bar=S.add('line',{x:300,y:(p.y??820)+(p.sub?96:118),dx:480,dy:0,w:10,color:'accent',glow:14,draw:0});bar.to(Math.max(0.1,(p.t??0)+0.3),(p.t??0)+0.9,{draw:1},'out');out.push(bar);
  if(p.sub){const b=enter(S.add('text',{text:p.sub,x:540,y:(p.y??820)+(p.subDy??190),size:64,weight:600,color:p.subColor||'dim',maxW:880}),(p.t??0)+0.4,'up');out.push(b)}
  if(p.hide!==undefined)out.forEach(h=>h.hide(p.hide));
  return out});

/* Équation par étapes : {lines:[{text, t, note?, color?}], size=120} — la ligne courante est vive, les précédentes s'estompent,
   la dernière est encadrée. */
reg('equation',(S,p)=>{need(p,'lines','array');
  const n=p.lines.length,gap=Math.min(250,1000/n),y0=960-(n-1)*gap/2,size=p.size??(n>5?96:120),hs=[];
  p.lines.forEach((l,i)=>{need(l,'text','string');const y=y0+i*gap,last=i===n-1;
    const h=enter(S.add('text',{text:l.text,x:540,y,size,weight:800,mono:true,color:l.color||(last?'good':'ink'),maxW:880}),l.t??0,'up');hs.push(h);
    if(l.note){const nt=enter(S.add('text',{text:l.note,x:540,y:y-gap*0.5-6,size:48,weight:600,color:'warm',maxW:860}),(l.t??0)-0.1,'up');nt.hide((l.t??0)+1.6)}
    if(i>0){hs[i-1].to(l.t??0,(l.t??0)+0.4,{a:last?0.45:0.6})}
    if(l.sfx!==false)S.sfx(l.t??0,'pop')});
  const lt=p.lines[n-1].t??0;
  const frame=S.add('box',{x:540,y:y0+(n-1)*gap,w:Math.min(980,measure(p.lines[n-1].text,size,800,MONO)+120),h:size*1.5,color:'bg',stroke:'good',sw:6,corner:30,a:0,layer:-1});
  frame.to(lt+0.3,lt+0.7,{a:1},'out');S.sfx(lt+0.3,'ping');
  return hs});

/* Gros nombre animé : {from, to, t0, t1, prefix?, suffix?, decimals=0, label?, labelT?, color='ink'} */
reg('bignumber',(S,p)=>{need(p,'to','number');
  const from=p.from??0,dec=p.decimals||0,ints=String(Math.floor(Math.max(Math.abs(from),Math.abs(p.to)))).length,
    chars=ints+Math.floor((ints-1)/3)+(dec?dec+1:0)+(p.suffix||'').length+(p.prefix||'').length+(Math.min(from,p.to)<0?1:0),
    size=clampI(900/(chars*0.64),70,260);   // le texte réel (séparateurs et décimales compris) tient dans 900 px
  const c=S.add('counter',{x:540,y:p.y??800,value:from,size,color:p.color||'ink',glow:22,prefix:p.prefix||'',suffix:p.suffix||'',decimals:p.decimals||0});
  c.to(p.t0??0,p.t1??((p.t0??0)+2),{value:p.to},'io');   // visible dès la première image (valeur de départ)
  S.add('particles',{x:540,y:960,n:60,seed:9,w:1080,h:1920,speed:16,diry:-1,size:3.5,color:'primary',alpha:0.4,layer:-2});
  S.add('line',{x:140,y:(p.y??800)+size*0.55,dx:800,dy:0,w:14,color:'line'});
  const prog=S.add('line',{x:140,y:(p.y??800)+size*0.55,dx:800,dy:0,w:14,color:p.color==='accent'?'accent':'primary',glow:14,draw:0});prog.to(p.t0??0,p.t1??((p.t0??0)+2),{draw:1},'io');
  if(p.label){const l=enter(S.add('text',{text:p.label,x:540,y:(p.y??800)+size*0.8,size:72,weight:700,color:'dim',maxW:900}),p.labelT??p.t1??1,'up');return [c,l]}
  return [c]});

/* Histogramme : {values, labels?, t0, t1, title?, readout?, readoutT?, color='primary'} */
reg('bars',(S,p)=>{need(p,'values','array');
  const out=[];
  if(p.title)out.push(enter(S.add('text',{text:p.title,x:540,y:430,size:76,weight:800,color:'ink',maxW:900}),0,'up'));
  const b=S.add('bars',{x:540,y:1450,w:900,h:760,values:p.values,labels:p.labels||p.values.map((_,i)=>String(i+1)),grow:0,color:p.color||'primary',size:34});
  enter(b,Math.max(0,(p.t0??0)-0.2),'up');b.to(p.t0??0.2,p.t1??2.5,{grow:1},'out');out.push(b);
  if(p.readout)out.push(enter(S.add('text',{text:p.readout,x:540,y:1590,size:80,weight:800,color:'warm',maxW:900}),p.readoutT??p.t1??2.5,'up'));
  return out});

/* Courbe : {values, t0, t1, title?, xlabel?, ylabel?, ref?: {value,label}} — axes + tracé progressif. */
reg('linechart',(S,p)=>{need(p,'values','array');
  const W0=860,H0=700,ox=110,oy=1500,vs=p.values,mn=Math.min(...vs,p.ref?p.ref.value:Infinity),mx=Math.max(...vs,p.ref?p.ref.value:-Infinity),span=(mx-mn)||1;
  const pt=(v,i)=>[i/(vs.length-1)*W0,-(v-mn)/span*H0];
  const out=[];
  if(p.title)out.push(enter(S.add('text',{text:p.title,x:540,y:430,size:76,weight:800,color:'ink',maxW:900}),0,'up'));
  out.push(enter(S.add('line',{x:ox,y:oy,dx:0,dy:-H0-30,w:5,color:'dim'}),0,'up'));
  out.push(enter(S.add('line',{x:ox,y:oy,dx:W0+30,dy:0,w:5,color:'dim'}),0,'up'));
  if(p.ref){const ry=oy+pt(p.ref.value,0)[1];out.push(enter(S.add('line',{x:ox,y:ry,dx:W0,dy:0,w:4,color:'warm',dash:[16,14]}),p.t0??0,'up'));
    out.push(enter(S.add('text',{text:p.ref.label||'',x:ox+W0-80,y:ry-48,size:56,weight:800,color:'warm',maxW:300}),p.t0??0,'up'))}
  const line=S.add('polyline',{x:ox,y:oy,points:vs.map(pt),w:10,color:'primary',glow:16,draw:0,fill:'primary'});line.to(p.t0??0.3,p.t1??3,{draw:1},'io');out.push(line);
  if(p.xlabel)out.push(S.add('text',{text:p.xlabel,x:540,y:oy+80,size:46,weight:600,color:'dim',maxW:800}));
  if(p.ylabel)out.push(S.add('text',{text:p.ylabel,x:ox+300,y:oy-H0-80,size:46,weight:600,color:'dim',maxW:600}));
  return out});

/* Liste révélée : {items:[{text, t}], title?} — cartes empilées, une par idée, au moment où la voix la dit. */
reg('bullets',(S,p)=>{need(p,'items','array');
  const n=p.items.length,gap=Math.min(240,(p.title?1000:1150)/n),y0=(p.title?980:960)-(n-1)*gap/2,out=[];
  if(p.title)out.push(enter(S.add('text',{text:p.title,x:540,y:380,size:80,weight:800,color:'ink',maxW:900}),0,'up'));
  p.items.forEach((it,i)=>{need(it,'text','string');const y=y0+i*gap,t=it.t??0.4+i*0.8;
    const card=enter(S.add('box',{x:540,y,w:920,h:Math.min(200,gap-26),color:'panel',stroke:['primary','warm','good','violet','accent'][i%5],sw:4,corner:36}),t,'right');
    const num=enter(S.add('circle',{x:150,y,rad:44,color:['primary','warm','good','violet','accent'][i%5]}),t,'pop');
    const nt=enter(S.add('text',{text:String(i+1),x:150,y:y+2,size:56,weight:800,color:'dark'}),t,'pop');
    const tx=enter(S.add('text',{text:it.text,x:580,y,size:58,weight:700,color:'ink',maxW:700}),t+0.1,'right');
    S.sfx(t,'pop');out.push(card,num,nt,tx)});
  return out});

/* Comparaison à deux colonnes : {left:{title,items}, right:{title,items}, t?, step=0.7} */
reg('compare',(S,p)=>{need(p,'left','object');need(p,'right','object');
  const out=[],t0=p.t??0,step=p.step??0.7;
  out.push(enter(S.add('line',{x:540,y:430,dx:0,dy:1100,w:5,color:'line'}),t0,'up'));
  [[p.left,290,'primary'],[p.right,790,'accent']].forEach(([side,x,color],c)=>{
    out.push(enter(S.add('text',{text:side.title||'',x,y:520,size:76,weight:800,color,maxW:440}),t0+c*0.2,'up'));
    (side.items||[]).forEach((txt,i)=>{const t=(side.times&&side.times[i]!==undefined)?side.times[i]:t0+0.5+(i*2+c)*step/1.4;
      out.push(enter(S.add('box',{x,y:720+i*210,w:440,h:170,color:'panel',stroke:color,sw:4,corner:28}),t,'up'));
      out.push(enter(S.add('text',{text:txt,x,y:720+i*210,size:50,weight:700,color:'ink',maxW:390}),t+0.1,'up'));S.sfx(t,'pop')})});
  return out});

/* Schéma de flux vertical : {nodes:[{label, t, color?}]} — blocs reliés par des flèches qui se tracent. */
reg('flow',(S,p)=>{need(p,'nodes','array');
  const n=p.nodes.length,gap=Math.min(260,1150/n),y0=960-(n-1)*gap/2,out=[];
  p.nodes.forEach((nd,i)=>{need(nd,'label','string');const y=y0+i*gap,t=nd.t??0.3+i*0.8,color=nd.color||['accent','warm','good','primary','violet','blue'][i%6];
    const b=enter(S.add('chunk',{x:540,y,w:780,h:Math.min(130,gap-80),color,label:nd.label,size:52,mono:false,glow:14}),i===0?0:t,'pop');out.push(b);
    if(i>0){const a=S.add('line',{x:540,y:y0+(i-1)*gap+Math.min(130,gap-80)/2+10,dx:0,dy:gap-Math.min(130,gap-80)-20,w:8,color:'dim',head:true,draw:0});a.to(t-0.3,t,{draw:1},'out');out.push(a)}
    S.sfx(t,'clip')});
  return out});

/* Segment coupé en deux (nombre d'or) : {tCut, ratio=0.618, aLabel='a', bLabel='b', tLabels?} */
reg('segment',(S,p)=>{
  const L=880,x0=100,y=960,r=p.ratio??0.618,xc=x0+L*r,tc=p.tCut??1.2,tl=p.tLabels??tc+0.5,out=[];
  out.push(S.add('line',{x:x0,y,dx:L,dy:0,w:22,color:'white',glow:10}));
  out.push(enter(S.add('text',{text:(p.aLabel||'a')+' + '+(p.bLabel||'b'),x:540,y:y-210,size:96,weight:800,color:'ink'}),Math.max(0,tc-0.6),'up'));
  out.push(enter(S.add('line',{x:x0,y:y-110,dx:L,dy:0,w:8,color:'dim'}),Math.max(0,tc-0.6),'up'));
  const a=S.add('line',{x:x0,y,dx:L*r,dy:0,w:22,color:'warm',glow:14,draw:0});a.to(tc,tc+0.5,{draw:1},'out');out.push(a);
  out.push(enter(S.add('line',{x:xc,y:y-70,dx:0,dy:140,w:10,color:'accent'}),tc,'pop'));
  out.push(enter(S.add('text',{text:p.aLabel||'a',x:x0+L*r/2,y:y+140,size:110,weight:800,color:'warm'}),tl,'up'));
  out.push(enter(S.add('text',{text:p.bLabel||'b',x:xc+L*(1-r)/2,y:y+140,size:110,weight:800,color:'white'}),tl+0.3,'up'));
  S.sfx(tc,'clip');return out});

/* Carrés de Fibonacci : {t0, t1, n=8} — pavage numéroté qui se construit carré par carré. */
reg('fibonacci',(S,p)=>{
  const n=clampI(p.n??8,3,10),f=[1,1];for(let i=2;i<n;i++)f.push(f[i-1]+f[i-2]);
  const sq=[{x:0,y:0,s:1,v:1}];let minx=0,maxx=1,miny=0,maxy=1;
  for(let i=1;i<n;i++){const s=f[i],dir=(i-1)%4;let x,y;
    if(dir===0){x=maxx;y=miny}else if(dir===1){x=minx;y=miny-s}else if(dir===2){x=minx-s;y=miny}else{x=minx;y=maxy}
    sq.push({x,y,s,v:s});minx=Math.min(minx,x);maxx=Math.max(maxx,x+s);miny=Math.min(miny,y);maxy=Math.max(maxy,y+s)}
  const k=Math.min(900/(maxx-minx),1100/(maxy-miny)),cx=(minx+maxx)/2,cy=(miny+maxy)/2,t0=p.t0??0,t1=p.t1??t0+4,out=[];
  // cadre du pavage final, visible dès la première image : le spectateur voit où la figure va se construire
  out.push(S.add('box',{x:540,y:960,w:(maxx-minx)*k+16,h:(maxy-miny)*k+16,color:'bg',stroke:'dim',sw:4,corner:6,layer:-1}));
  out.push(S.add('text',{text:f.join(' · '),x:540,y:960-(maxy-miny)*k/2-90,size:60,weight:800,mono:true,color:'warm',maxW:960}));
  sq.forEach((q,i)=>{const t=t0+(t1-t0)*i/Math.max(1,n-1),px=540+(q.x+q.s/2-cx)*k,py=960+(q.y+q.s/2-cy)*k,w=q.s*k;
    const b=enter(S.add('box',{x:px,y:py,w,h:w,color:i===n-1?'panel':'bg',stroke:['warm','primary','good','accent','violet'][i%5],sw:Math.max(3,w*0.03),corner:0}),i===0?0:t,'pop');out.push(b);
    if(w>=56)out.push(enter(S.add('text',{text:String(q.v),x:px,y:py,size:clampI(w*0.42,28,150),weight:800,mono:true,color:'ink'}),t+0.1,'pop'));
    S.sfx(t,'tick')});
  return out});
})();
