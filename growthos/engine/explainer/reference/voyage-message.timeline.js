/* Timeline du prototype OSI (ecrite a la main, sert de golden). Utilise l'API de runtime/*.js. */
const DUR=58,FPS=30;
const MSG='On mange ce soir ?',CIPH='x9#Fq@7%kL2!vR8&Zt';
const LN={7:'APPLICATION',6:'PRÉSENTATION',5:'SESSION',4:'TRANSPORT',3:'RÉSEAU',2:'LIAISON',1:'PHYSIQUE'};
const NARRATION=[
 [0.0,'Tu appuies sur « Envoyer ».'],
 [2.2,'En une fraction de seconde, ton message va traverser sept couches… et des centaines de kilomètres.'],
 [6.0,'Couche 7, Application : ton appli prépare le message.'],
 [9.0,'Couche 6, Présentation : il est chiffré. Personne en chemin ne peut le lire.'],
 [12.5,'Couche 5, Session : la conversation reste ouverte entre les deux téléphones.'],
 [15.5,'Couche 4, Transport : le message est découpé en morceaux, numérotés pour être remis dans l’ordre.'],
 [20.0,'Couche 3, Réseau : chaque morceau reçoit l’adresse IP de départ et d’arrivée.'],
 [24.0,'Couche 2, Liaison : on ajoute l’adresse du prochain appareil sur la route.'],
 [27.5,'Couche 1, Physique : tout devient des 0 et des 1, envoyés par ondes radio.'],
 [31.0,'Direction l’antenne, puis les routeurs d’Internet.'],
 [34.5,'Chaque routeur ne lit que l’adresse IP, et choisit par où envoyer le morceau.'],
 [38.5,'Les morceaux ne prennent pas forcément la même route.'],
 [42.5,'À l’arrivée, le téléphone fait le chemin inverse : il retire chaque couche.'],
 [47.0,'Il remet les morceaux dans l’ordre, déchiffre…'],
 [50.5,'… et le message s’affiche.'],
 [53.0,'Sept couches, à l’aller comme au retour, en un clin d’œil.'],
];
const fy=L=>(7-L)*300, PX=20;
const piece=n=>CIPH.slice((n-1)*6,n*6);
function scramble(src,dst,p,l,k){ // progressively turns src into dst with flickering glyphs
  const G='#%&@$*+=?!<>0123456789ABCDEFxzq';let s='';const n=src.length;
  for(let i=0;i<n;i++){const c=i/n;if(p>=1||p>c+0.18)s+=dst[i];else if(p>c)s+=G[Math.floor(hash(i,Math.floor(l*16)+k)*G.length)];else s+=src[i]}
  return s;
}
function layerHud(l,sched,roles,eyebrow){
  screen();const g=ctx.createLinearGradient(0,0,0,640);g.addColorStop(0,'rgba(10,15,28,0.96)');g.addColorStop(0.7,'rgba(10,15,28,0.75)');g.addColorStop(1,'rgba(10,15,28,0)');
  ctx.fillStyle=g;ctx.fillRect(0,0,W,640);
  T(eyebrow,76,168,{size:26,fam:MONO,weight:700,color:C.dim,align:'left',ls:6});
  for(let i=0;i<sched.length;i++){const [L,e]=sched[i],ne=i+1<sched.length?sched[i+1][1]:999;
    const a=out(seg(l,e,e+0.45))*(1-seg(l,ne-0.45,ne-0.05));if(a<=0)continue;const dy=(1-a)*36;
    T(String(L),66,330+dy,{size:250,weight:800,color:LC[L],align:'left',alpha:a,glow:30});
    T(LN[L],250,282+dy,{size:72,weight:800,align:'left',alpha:a,ls:-1});
    T(roles[L],252,366+dy,{size:40,weight:500,color:C.dim,align:'left',alpha:a});}
  let cur=sched[0][0];for(const [L,e] of sched)if(l>=e)cur=L;
  for(let L=7;L>=1;L--){const y=600+(7-L)*120,on=L===cur;
    ctx.fillStyle=LC[L];ctx.globalAlpha=on?1:0.28;ctx.beginPath();ctx.arc(1024,y,on?15:9,0,7);ctx.fill();ctx.globalAlpha=1;
    if(on){ctx.strokeStyle=LC[L];ctx.lineWidth=3;ctx.beginPath();ctx.arc(1024,y,26,0,7);ctx.stroke()}}
}
function floors(cur,camX){
  for(let L=7;L>=1;L--){const y=fy(L),a=L===cur?1:0.42;
    ctx.save();ctx.globalAlpha=a;ctx.fillStyle=LC[L];ctx.globalAlpha=a*0.05;ctx.fillRect(camX-700,y-140,4000,280);
    ctx.globalAlpha=a*0.6;ctx.fillRect(camX-700,y-140,4000,3);ctx.restore();
    T(`${L}  ${LN[L]}`,-500,y-104,{size:26,fam:MONO,weight:700,color:LC[L],align:'left',ls:3,alpha:a*0.9});}
}

/* --- 1. Phone A: the tap ---------------------------------------------- */
function s1(t){
  const bw=measure(MSG,34,600)+64,BX=244-bw/2,BY=-110;
  const cam=kf(t,[[0,{x:0,y:40,z:1.06}],[4.7,{x:0,y:0,z:1}],[6,{x:BX,y:BY,z:10},inn]]);
  background(cam);camera(cam);
  const n=Math.floor(seg(t,0.25,1.5)*MSG.length),fly=out(seg(t,1.9,2.45));
  const bubbles=[{edge:-244,y:-300,text:'Tu es où ?',side:'left',col:C.chip,tc:C.ink}];
  if(t>=1.9)bubbles.push({edge:lerp(150,244,fly),y:lerp(442,BY,fly),text:MSG,side:'right',col:LC[7],s:lerp(0.6,1,fly)});
  phone(0,0,{contact:'Awa',avatar:LC[3],input:t<1.9?MSG.slice(0,n):'',press:t>1.65&&t<1.95?Math.sin(seg(t,1.65,1.95)*Math.PI):0,bubbles});
  T('Envoyé ✓',244,BY+72,{size:24,weight:500,color:C.dim,align:'right',alpha:out(seg(t,2.6,2.9))});
  screen();const a=out(seg(t,2.3,2.8))*(1-seg(t,4.5,4.9));
  T('7 couches',540,250+(1-a)*30,{size:150,weight:800,alpha:a,ls:-4});
  for(let i=0;i<7;i++){const ai=out(seg(t,2.5+i*0.08,2.8+i*0.08))*(1-seg(t,4.5,4.9));
    ctx.globalAlpha=ai;ctx.fillStyle=LC[7-i];rr(540-217+i*62,345,50,14,7);ctx.fill();ctx.globalAlpha=1;}
  const b=out(seg(t,3.2,3.6))*(1-seg(t,4.5,4.9));
  T('des centaines de kilomètres',540,1690+(1-b)*20,{size:56,weight:600,color:C.dim,alpha:b});
  overlay(LC[7],seg(t,5.5,6));
}

/* --- 2. Down the stack: encapsulation ------------------------------- */
const ENC=[[7,0],[6,3.0],[5,6.5],[4,9.5],[3,14],[2,18],[1,21.5]];
const ROLE_ENC={7:'ton appli prépare le message',6:'le message est chiffré',5:'la conversation reste ouverte',4:'découpé en morceaux numérotés',3:'adresse IP de départ et d’arrivée',2:'adresse du prochain appareil',1:'des 0 et des 1, en ondes radio'};
function s2(t){
  const l=t-6;const keys=[[0,fy(7)]];for(let i=1;i<ENC.length;i++){const [L,e]=ENC[i];keys.push([e-0.6,fy(L+1)],[e,fy(L)])}
  const py=kf(l,keys),cy=py+30;
  const cam={x:lerp(0,700,io(seg(l,23.2,25))),y:py-230,z:kf(l,[[0,3.2],[0.9,1,out]])};
  background(cam);camera(cam);
  let cur=7;for(const [L,e] of ENC)if(l>=e)cur=L;floors(cur,cam.x);
  // L7–L5: one block
  if(l<10.2){
    const enc=seg(l,3.6,4.8),label=l<3.6?MSG:scramble(MSG,CIPH,enc,l,1);
    const col=l<4.2?LC[7]:LC[6];
    chunk(PX-280,cy,560,96,col,label,{fam:l<3.6?DISP:MONO,size:l<3.6?36:32,glow:l<0.9?0:18});
    lock(PX+300,cy-92,back(seg(l,3.6,4.1)),out(seg(l,3.6,3.9)));
    // session: a live link to the other phone
    const sa=out(seg(l,6.9,7.4))*(1-seg(l,9.3,9.8));
    if(sa>0){ctx.save();ctx.globalAlpha=sa;ctx.strokeStyle=LC[5];ctx.lineWidth=5;ctx.setLineDash([16,14]);ctx.lineDashOffset=-l*60;
      ctx.beginPath();ctx.moveTo(PX+290,cy);ctx.bezierCurveTo(PX+420,cy,PX+420,cy-230,PX+430,cy-260);ctx.stroke();ctx.restore();
      miniPhone(PX+430,cy-380,'',0);T('Awa · session ouverte',PX+430,cy-230,{size:24,fam:MONO,color:LC[5],alpha:sa,align:'right'});}
  } else if(l<11.4){
    const sp=io(seg(l,10.2,11.4));
    for(let n=1;n<=3;n++){const w=lerp(186.7,220,sp),x0=PX-280+(n-1)*186.7;
      const x=lerp(x0,PX-110+0,sp),y=cy+(n-2)*100*sp;
      chunk(x+lerp(0,(n-2)*0,sp),y,w-lerp(0,0,sp),lerp(96,72,sp),LC[6],piece(n),{fam:MONO,size:28,r:12});}
  } else {
    const bits=io(seg(l,22,23)),fade=1-seg(l,23.2,23.8);
    for(let n=1;n<=3;n++){const y=cy+(n-2)*100,r=n-1;
      const items=[
        {w:104,col:LC[2],label:'MAC',p:seg(l,18.6+r*0.15,19.1+r*0.15)},
        {w:160,col:LC[3],label:'IP A→B',p:seg(l,14.6+r*0.2,15.1+r*0.2)},
        {w:120,col:LC[4],label:`TCP ${n}`,p:seg(l,11.7+r*0.25,12.2+r*0.25)},
        {w:220,col:LC[6],label:piece(n),p:1,size:28},
        {w:92,col:LC[2],label:'FCS',p:seg(l,18.9+r*0.15,19.4+r*0.15),from:'right'}];
      ctx.save();ctx.globalAlpha=1-bits;row(PX,y,items,72);ctx.restore();
      if(bits>0){let s='';for(let i=0;i<34;i++)s+=hash(i+n*50,Math.floor(l*10))>0.5?'1':'0';
        T(s,PX,y+2,{size:30,fam:MONO,weight:700,color:LC[1],alpha:bits*fade,glow:20,ls:2});}
    }
    const wv=seg(l,23.2,25);
    if(wv>0){const x0=PX-380,x1=x0+2600*io(wv);ctx.save();ctx.strokeStyle=LC[1];ctx.lineWidth=7;ctx.shadowColor=LC[1];ctx.shadowBlur=30;ctx.beginPath();
      for(let x=x0;x<=x1;x+=6){const y=cy+Math.sin((x-l*900)/34)*46*clamp((x-x0)/200);x===x0?ctx.moveTo(x,y):ctx.lineTo(x,y)}ctx.stroke();ctx.restore();}
  }
  layerHud(l,ENC,ROLE_ENC,'DÉPART · COUCHE');
  overlay(LC[7],1-seg(l,0,0.35));
}

/* --- 3. Across the network ------------------------------------------ */
const N={A:[190,1640],a1:[330,1330],R1:[300,1040],R2:[650,1160],R3:[480,800],R4:[870,900],R5:[700,560],R6:[290,540],a2:[830,330],B:[960,140]};
const EDGES=[['a1','R1'],['R1','R2'],['R1','R3'],['R2','R4'],['R3','R5'],['R3','R6'],['R6','R5'],['R4','R5'],['R5','a2'],['R2','R3']];
const ROUTES=[{n:1,path:['a1','R1','R3','R5','a2','B'],s:2.6,d:6.0},{n:2,path:['a1','R1','R2','R4','R5','a2','B'],s:2.8,d:8.3},{n:3,path:['a1','R1','R3','R6','R5','a2','B'],s:3.0,d:6.9}];
function s3(t){
  const l=t-31;
  const cam=kf(l,[[0,{x:300,y:1450,z:1.9}],[1.6,{x:300,y:1450,z:1.9}],[2.9,{x:540,y:900,z:1}],[3.8,{x:540,y:900,z:1}],[4.6,{x:500,y:760,z:1.85}],[7.1,{x:500,y:760,z:1.85}],[8.0,{x:540,y:900,z:1}]]);
  background(cam);camera(cam);
  ctx.lineCap='round';
  for(const [a,b] of EDGES){ctx.strokeStyle=C.line;ctx.lineWidth=4;ctx.beginPath();ctx.moveTo(...N[a]);ctx.lineTo(...N[b]);ctx.stroke()}
  // radio from phone A to antenna
  const wa=1-seg(l,2.6,3.2);
  if(wa>0){ctx.save();ctx.strokeStyle=LC[1];ctx.lineWidth=5;const [ax,ay]=N.A,[bx,by]=N.a1,ang=Math.atan2(by-ay,bx-ax);
    for(let k=0;k<4;k++){const r=((l*0.9+k/4)%1)*330;ctx.globalAlpha=wa*(1-r/330);ctx.beginPath();ctx.arc(ax,ay-80,r,ang-0.45,ang+0.45);ctx.stroke()}ctx.restore();}
  const pts=r=>r.path.map(k=>N[k]);
  for(const r of ROUTES){const p=seg(l,r.s,r.s+r.d);if(p<=0)continue;
    // lit trail along the route
    ctx.save();ctx.strokeStyle=LC[3];ctx.globalAlpha=0.35;ctx.lineWidth=6;ctx.beginPath();const P=pts(r);ctx.moveTo(...P[0]);
    for(let q=0;q<=p;q+=0.01)ctx.lineTo(...polyPos(P,q));ctx.lineTo(...polyPos(P,p));ctx.stroke();ctx.restore();}
  for(const k of ['R1','R2','R3','R4','R5','R6']){let hot=0;for(const r of ROUTES){const P=pts(r),p=seg(l,r.s,r.s+r.d),[px,py]=polyPos(P,p);
    if(p>0&&p<1)hot=Math.max(hot,clamp(1-Math.hypot(px-N[k][0],py-N[k][1])/120))}router(...N[k],hot)}
  antenna(...N.a1,clamp(1-seg(l,3.4,4)),l);antenna(...N.a2,seg(l,8.2,8.6)*(1-seg(l,11,11.4)),l);
  miniPhone(...N.A,'toi');
  let glowB=0;for(const r of ROUTES){const e=r.s+r.d;glowB=Math.max(glowB,1-clamp(Math.abs(l-e)/0.5))}
  miniPhone(...N.B,'Awa',glowB);
  for(const r of ROUTES){const p=seg(l,r.s,r.s+r.d);if(p<=0||p>=1)continue;const P=pts(r);
    for(let k=6;k>=1;k--){const [x,y]=polyPos(P,p-k*0.012);ctx.globalAlpha=0.35*(1-k/7);ctx.fillStyle=LC[3];ctx.beginPath();ctx.arc(x,y,14-k,0,7);ctx.fill()}
    ctx.globalAlpha=1;const [x,y]=polyPos(P,p);chunk(x-44,y,88,42,LC[3],`#${r.n}`,{size:24,glow:30,r:21});}
  // router reads only the IP header
  const ca=out(seg(l,4.7,5.1))*(1-seg(l,6.9,7.3));
  if(ca>0){const [rx,ry]=N.R3,cx0=rx+90,cyc=ry+178;ctx.save();ctx.globalAlpha=ca;
    ctx.fillStyle='rgba(16,24,44,0.95)';rr(cx0-210,cyc-70,420,140,22);ctx.fill();ctx.strokeStyle=LC[3];ctx.lineWidth=3;rr(cx0-210,cyc-70,420,140,22);ctx.stroke();ctx.restore();
    T('LE ROUTEUR LIT',cx0,cyc-40,{size:18,fam:MONO,color:C.dim,alpha:ca,ls:3});
    const sc=0.6;ctx.save();ctx.translate(cx0,cyc+18);ctx.scale(sc,sc);
    row(0,0,[{w:160,col:LC[3],label:'IP A→B',p:1,glow:30},{w:120,col:'#3a4560',label:'TCP',p:1},{w:220,col:'#3a4560',label:'██████',p:1}],72);ctx.restore();
    const pr=out(seg(l,5.4,6.2));ctx.save();ctx.globalAlpha=ca;ctx.strokeStyle=LC[4];ctx.lineWidth=8;ctx.shadowColor=LC[4];ctx.shadowBlur=20;
    ctx.beginPath();ctx.moveTo(rx+30,ry-34);ctx.lineTo(lerp(rx+30,N.R5[0]-34,pr),lerp(ry-34,N.R5[1]+34,pr));ctx.stroke();
    ctx.shadowBlur=0;ctx.setLineDash([10,12]);ctx.strokeStyle='rgba(233,238,252,0.3)';ctx.lineWidth=4;ctx.beginPath();ctx.moveTo(rx-36,ry-26);ctx.lineTo(lerp(rx-36,N.R6[0]+36,pr),lerp(ry-26,N.R6[1]+30,pr));ctx.stroke();ctx.restore();
    T('vers B',lerp(rx,N.R5[0],0.5)+60,lerp(ry,N.R5[1],0.5)+10,{size:26,fam:MONO,color:LC[4],alpha:ca*pr,align:'left'});}
  screen();
  pill('ANTENNE → INTERNET',620,1800,LC[1],out(seg(l,0.4,0.8))*(1-seg(l,3.2,3.6)));
  pill('IL LIT SEULEMENT L’IP',620,1800,LC[3],out(seg(l,3.7,4.1))*(1-seg(l,7.2,7.6)));
  pill('3 MORCEAUX, 3 CHEMINS',620,1800,LC[4],out(seg(l,7.7,8.1))*(1-seg(l,11.1,11.5)));
}

/* --- 4. Up the stack on the other phone ------------------------------ */
const DEC=[[1,0],[2,2.0],[3,3.1],[4,4.2],[6,7.0],[7,8.5]];
const ROLE_DEC={1:'les ondes redeviennent des bits',2:'retire l’adresse MAC',3:'retire l’adresse IP',4:'remet les morceaux dans l’ordre',6:'déchiffre le message',7:'l’appli affiche le message'};
function s4(t){
  const l=t-42.5;
  if(l<8.9){
    const py=kf(l,[[0,fy(1)],[1.5,fy(1)],[2.0,fy(2)],[2.6,fy(2)],[3.1,fy(3)],[3.7,fy(3)],[4.2,fy(4)],[6.2,fy(4)],[7.0,fy(6)],[8.0,fy(6)],[8.5,fy(7)]]),cy=py+30;
    const cam={x:0,y:py-230,z:kf(l,[[0,1],[8.3,1],[8.9,7,inn]])};
    background(cam);camera(cam);
    let cur=1;for(const [L,e] of DEC)if(l>=e)cur=L;floors(cur,0);
    if(l<5.5){
      const sw=io(seg(l,4.3,5.0)),bits=1-io(seg(l,0.5,1.4));
      for(const n of [1,3,2]){const r=n-1;const slot=n===1?0:n===3?lerp(1,2,sw):lerp(2,1,sw);
        const app=out(seg(l,0.05+[0,0,0.5,0.25][n],0.4+[0,0,0.5,0.25][n]));
        const y=cy+(slot-1)*100+(1-app)*220,xo=Math.sin(sw*Math.PI)*(n===3?150:n===2?-150:0);
        const items=[
          {w:104,col:LC[2],label:'MAC',p:1-seg(l,2.0+r*0.1,2.5+r*0.1)},
          {w:160,col:LC[3],label:'IP A→B',p:1-seg(l,3.15+r*0.1,3.6+r*0.1)},
          {w:120,col:LC[4],label:`TCP ${n}`,p:1-seg(l,5.0+r*0.08,5.4+r*0.08),glow:l>4.2&&l<5.0?24:0},
          {w:220,col:LC[6],label:piece(n),p:1,size:28},
          {w:92,col:LC[2],label:'FCS',p:1-seg(l,2.0+r*0.1,2.5+r*0.1),from:'right'}];
        ctx.save();ctx.globalAlpha=app*(1-bits);row(PX+xo,y,items,72);ctx.restore();
        if(bits>0){let s='';for(let i=0;i<34;i++)s+=hash(i+n*50,Math.floor(l*10)+3)>0.5?'1':'0';
          T(s,PX+xo,y+2,{size:30,fam:MONO,weight:700,color:LC[1],alpha:bits*app,glow:20,ls:2});}
      }
      T('arrivés dans le désordre : 1, 3, 2',PX,cy+215,{size:26,fam:MONO,color:LC[4],alpha:out(seg(l,4.2,4.5))*(1-seg(l,5.2,5.5))});
    } else if(l<6.2){
      const sp=1-io(seg(l,5.5,6.2));
      for(let n=1;n<=3;n++){const w=lerp(186.7,220,sp),x0=PX-280+(n-1)*186.7;
        chunk(lerp(x0,PX-110,sp),cy+(n-2)*100*sp,w,lerp(96,72,sp),LC[6],piece(n),{fam:MONO,size:28});}
    } else {
      const d=seg(l,7.1,8.0),label=scramble(CIPH,MSG,d,l,5),col=l<7.6?LC[6]:LC[7];
      chunk(PX-280,cy,560,96,col,label,{fam:d>=1?DISP:MONO,size:d>=1?36:32,glow:18});
      lock(PX+300,cy-92,1-0.4*seg(l,7.1,7.5),1-seg(l,7.1,7.5));
    }
    layerHud(l,DEC,ROLE_DEC,'ARRIVÉE · COUCHE');
    overlay(C.bg,seg(l,8.55,8.9));
  } else {
    const k=l-8.9,cam=kf(k,[[0,{x:0,y:20,z:1.25}],[0.9,{x:0,y:0,z:1},out]]);
    background(cam);camera(cam);
    const pop=back(seg(k,0.1,0.5)),typed='Oui, 20h !',n=Math.floor(seg(k,0.7,1.5)*typed.length);
    phone(0,0,{contact:'Moussa',avatar:LC[7],status:n>0&&k<1.6?'écrit…':'en ligne',input:typed.slice(0,n),bubbles:[{edge:-244,y:-110,text:MSG,side:'left',col:C.chip,tc:C.ink,s:pop,alpha:clamp(pop)}]});
    screen();const a=out(seg(k,0.2,0.6));
    T('Reçu',540,260+(1-a)*30,{size:140,weight:800,alpha:a,ls:-3});
    T('le téléphone d’Awa',540,1690,{size:50,weight:600,color:C.dim,alpha:out(seg(k,0.4,0.8))});
    overlay(C.bg,1-seg(k,0,0.3));
  }
}

/* --- 5. Recap ---------------------------------------------------------- */
function s5(t){
  const l=t-53;background(null);screen();
  T('LE VOYAGE D’UN MESSAGE',540,250,{size:30,fam:MONO,weight:700,color:LC[7],ls:6,alpha:out(seg(l,0.1,0.5))});
  const top=420,step=112,bh=90;
  for(let L=7;L>=1;L--){const i=7-L,y=top+i*step;
    for(const side of [0,1]){const a=out(seg(l,0.15+i*0.07+side*0.12,0.5+i*0.07+side*0.12));const x=side?600:90,w=390;
      ctx.save();ctx.globalAlpha=a;ctx.fillStyle=LC[L];rr(x+(1-a)*(side?60:-60),y,w,bh,16);ctx.fill();ctx.restore();
      T(side?String(L):`${L}  ${LN[L]}`,x+(side?w/2:24)+(1-a)*(side?60:-60),y+bh/2+2,{size:side?40:26,fam:MONO,weight:700,color:C.dark,align:side?'center':'left',alpha:a});}}
  T('toi',285,top-50,{size:34,weight:700,color:C.dim,alpha:out(seg(l,0.5,0.9))});
  T('Awa',795,top-50,{size:34,weight:700,color:C.dim,alpha:out(seg(l,0.6,1.0))});
  const base=top+7*step+40;ctx.strokeStyle=C.line;ctx.lineWidth=4;ctx.setLineDash([12,12]);ctx.beginPath();ctx.moveTo(285,base);ctx.lineTo(795,base);ctx.stroke();ctx.setLineDash([]);
  T('Internet',540,base+40,{size:26,fam:MONO,color:C.dim,alpha:out(seg(l,0.9,1.3))});
  const P=[[285,top-10],[285,base],[795,base],[795,top-10]],p=io(seg(l,1.0,4.0));
  if(p>0&&p<1){const [x,y]=polyPos(P,p);ctx.save();ctx.fillStyle='#fff';ctx.shadowColor='#fff';ctx.shadowBlur=30;ctx.beginPath();ctx.arc(x,y,16,0,7);ctx.fill();ctx.restore()}
  const a=out(seg(l,1.2,1.7));
  T('7 couches',540,1500+(1-a)*30,{size:140,weight:800,alpha:a,ls:-4});
  T('à l’aller comme au retour',540,1615,{size:60,weight:700,alpha:out(seg(l,1.6,2.1))});
  T('en un clin d’œil',540,1700,{size:46,weight:500,color:C.dim,alpha:out(seg(l,2.0,2.5))});
}

/* scene dispatch + cuts */
function renderAt(t){
  t=clamp(t,0,DUR);screen();ctx.globalAlpha=1;ctx.setLineDash([]);
  if(t<6)s1(t);else if(t<31)s2(t);else if(t<42.5)s3(t);else if(t<53)s4(t);else s5(t);
  let cut=0;for(const b of [31,42.5,53])cut=Math.max(cut,1-Math.abs(t-b)/0.28);overlay(C.bg,cut*0.97);
}
const SFX=(()=>{const e=[];const add=(at,type,k=0)=>e.push({at,type,k});
  for(let i=0;i<MSG.length;i++)add(0.25+i*0.069,'tick');add(1.72,'pop');add(1.95,'whoosh');add(2.35,'hit');
  add(4.85,'whoosh');add(6.0,'impact');
  for(const [L,e2] of ENC.slice(1))add(6+e2-0.55,'whooshDown');
  add(9.6,'glitch',1);add(9.65,'clip');add(13.0,'blip',2);add(16.2,'split');
  for(let r=0;r<3;r++){add(6+11.8+r*0.25,'clip');add(6+14.7+r*0.2,'clip');add(6+18.7+r*0.15,'clip')}
  add(28.0,'bits',3);add(29.2,'whoosh');add(31.0,'whoosh');
  for(const r of ROUTES){add(31+r.s,'blip',r.n);add(31+r.s+r.d,'blip',r.n+3)}add(35.6,'scan');add(36.4,'pop');
  add(42.5,'whoosh');add(43.0,'bits',4);for(const [L,e2] of DEC.slice(1))add(42.5+e2-0.5,'whooshDown');
  for(let r=0;r<3;r++){add(42.5+2.05+r*0.1,'unclip');add(42.5+3.2+r*0.1,'unclip');add(42.5+5.05+r*0.08,'unclip')}
  add(46.8,'whoosh');add(48.0,'impact');add(49.6,'glitch',2);add(51.5,'ping');
  for(let i=0;i<10;i++)add(52.1+i*0.08,'tick');add(53.0,'hit');add(54.3,'whoosh');
  return e.sort((a,b)=>a.at-b.at)})();
window.VIDEO={duration:DUR,fps:FPS,narration:NARRATION,sfx:SFX};
window.renderAt=renderAt;
