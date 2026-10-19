/* Vidéo vitrine « D'un téléphone à l'autre » (~60 s) — écrite à la main, référence de qualité pour les LLM (phase 2).
   Awa écrit à Léa : Dakar -> OSI en version courte -> antenne -> câble sous-marin -> data center -> Paris.
   Utilise uniquement l'API de runtime/*.js. Aucun fait chiffré : les affirmations restent générales (mécanismes). */
const DUR=60,FPS=30;
const MSG='On mange ce soir ?',CIPH='x9#Fq@7%kL2!vR8&Zt',REPLY='Oui, 20h !';
const NARRATION=[
 [0.0,'Dakar. Awa écrit à son amie Léa.'],
 [3.2,'« On mange ce soir ? » Elle appuie sur Envoyer.'],
 [8.5,'Dans le téléphone, le message est préparé en quelques étapes.'],
 [11.4,'D’abord, il est chiffré : personne ne peut le lire en chemin.'],
 [14.4,'Ensuite, il est découpé en petits morceaux numérotés.'],
 [17.4,'Chacun reçoit l’adresse de départ et d’arrivée.'],
 [20.2,'Puis tout devient des 0 et des 1.'],
 [22.0,'Une antenne capte le signal…'],
 [26.0,'… et l’envoie vers un câble qui plonge dans l’océan.'],
 [30.0,'Au fond de la mer, des câbles relient les continents.'],
 [35.0,'Les morceaux filent dans la lumière, jusqu’en Europe.'],
 [39.5,'Dans un centre de données, ils sont aiguillés vers Paris.'],
 [43.0,'Une dernière antenne, et le message arrive chez Léa.'],
 [47.0,'Le téléphone remet les morceaux dans l’ordre, déchiffre…'],
 [50.0,'… et le message s’affiche.'],
 [52.5,'Léa sourit. Elle répond.'],
 [55.5,'Un message, des océans traversés, en un clin d’œil.'],
];
const piece=n=>CIPH.slice((n-1)*6,n*6);
const AWA={s:1.25,skin:WC.skin.deep,hair:'#120b0a',style:'braids',top:LC[7],pants:'#222a55',id:1};
const LEA={s:1.25,skin:WC.skin.light,hair:'#3a2316',style:'bun',top:'#5fb3a1',pants:'#2b3566',id:2,flip:true};
const PH_K=56/1100; // le téléphone dessiné dans la main = phone() réduit à cette échelle


/* --- 1. Dakar : la maison en coupe, la personne, le téléphone, puis zoom-through dans l'écran ------------- */
const HA=houseAnchors(0,0,{});
const AWA_PHONE=personPhonePos(HA.seatX,HA.seatY,{...AWA,pose:'sitPhone'});
const ZEND=1/(PH_K*AWA.s);                       // zoom où l'écran du téléphone fait 560 px de large
const BW=measure(MSG,34,600)+64,BX=244-BW/2,BY=-110;  // bulle envoyée (repère du téléphone)
function sentUI(extra){return {contact:'Léa',avatar:LC[3],input:'',press:0,bubbles:[{edge:-244,y:-300,text:'Tu es où ?',side:'left',col:C.chip,tc:C.ink},{edge:244,y:BY,text:MSG,side:'right',col:LC[7]}],
  after:()=>T('Envoyé ✓',244,BY+72,{size:24,weight:500,color:C.dim,align:'right'}),...extra}}
function nightScene(cx,t,o){
  sky(-3200,3200,-2600,0,t,{moon:o.moon,stars:140});
  city(-1500,0,24,{far:true,seed:o.seed,minH:90,varH:260,body:'#1a2150',fog:'#070b1f'});
  ctx.fillStyle=vgrad(0,0,700,[[0,'#2a2f63'],[1,WC.land]]);ctx.fillRect(-3200,0,6400,1500);ctx.fillStyle='rgba(255,255,255,0.05)';ctx.fillRect(-3200,150,6400,6);
  city(-1300,0,7,{seed:o.seed+5,minH:120,varH:200,gap:30,body:'#222a55',warm:o.warm});city(560,0,10,{seed:o.seed+2,minH:120,varH:220,gap:26,body:'#222a55',warm:o.warm});
}
function s1(t){
  const cam=kf(t,[[0,{x:0,y:-210,z:1.0,r:0}],[4.8,{x:-40,y:-235,z:2.7,r:0}],[6.0,{x:-40,y:-235,z:2.7,r:0}],[8.5,{x:AWA_PHONE[0],y:AWA_PHONE[1],z:ZEND,r:0.25},inn]]);
  cameraR(cam);nightScene(0,t,{moon:[640,-640],seed:3});
  house(0,0,{palette:'dakar',t,dark:0.22});glowAt(0,30,520,'rgba(255,190,110,0.9)',0.16);
  const typeN=Math.floor(seg(t,1.0,4.0)*MSG.length),sent=t>=5.05,fly=out(seg(t,5.05,5.6)),press=t>4.85&&t<5.15?Math.sin(seg(t,4.85,5.15)*Math.PI):0;
  const bubbles=[{edge:-244,y:-300,text:'Tu es où ?',side:'left',col:C.chip,tc:C.ink}];
  if(sent)bubbles.push({edge:lerp(150,244,fly),y:lerp(442,BY,fly),text:MSG,side:'right',col:LC[7],s:lerp(0.6,1,fly)});
  const ui={contact:'Léa',avatar:LC[3],input:sent?'':MSG.slice(0,typeN),press,bubbles,
    after:()=>T('Envoyé ✓',244,BY+72,{size:24,weight:500,color:C.dim,align:'right',alpha:out(seg(t,5.9,6.2))})};
  person(HA.seatX,HA.seatY,{...AWA,pose:'sitPhone',t,typing:t>0.9&&t<4.9,glow:1,thumbA:1-seg(t,6.2,7.0),phoneUI:ui});
  const dim=seg(t,7.8,8.45);   // l'entourage s'éteint, seul l'écran reste : raccord avec la scène suivante
  if(dim>0){overlay(C.bg,dim);cameraR(cam);ctx.save();ctx.translate(AWA_PHONE[0],AWA_PHONE[1]);ctx.rotate(-0.25);ctx.scale(PH_K*AWA.s,PH_K*AWA.s);phone(0,0,{...ui,input:'',bubbles:[...bubbles.slice(0,1),{edge:244,y:BY,text:MSG,side:'right',col:LC[7]}]});ctx.restore()}
  screen();const tag=out(seg(t,0.2,0.7))*(1-seg(t,3.4,3.9));
  T('DAKAR',76,170,{size:30,fam:MONO,weight:700,color:LC[7],align:'left',ls:8,alpha:tag});
}

/* --- 2. Dans le téléphone : cinq étapes (version courte du modèle en couches) --------------------------- */
const PX=20;
const STAGES=[
  {n:1,name:'APPLICATION',role:'ton appli prépare le message',col:LC[7],t:0},
  {n:2,name:'CHIFFREMENT',role:'personne ne peut le lire',col:LC[6],t:1.3},
  {n:3,name:'DÉCOUPAGE',role:'des morceaux numérotés',col:LC[4],t:4.3},
  {n:4,name:'ADRESSES',role:'départ et arrivée',col:LC[3],t:7.3},
  {n:5,name:'SIGNAL',role:'des 0 et des 1',col:LC[1],t:10.1},
];
function bands(cur,camX){
  for(let i=0;i<STAGES.length;i++){const y=i*300,a=i===cur?1:0.42,col=STAGES[i].col;
    ctx.save();ctx.fillStyle=col;ctx.globalAlpha=a*0.05;ctx.fillRect(camX-700,y-140,4000,280);ctx.globalAlpha=a*0.6;ctx.fillRect(camX-700,y-140,4000,3);ctx.restore();
    T(`${STAGES[i].n}  ${STAGES[i].name}`,-500,y-104,{size:26,fam:MONO,weight:700,color:col,align:'left',ls:3,alpha:a*0.9})}
}
function s2(t){
  const l=t-8.5;
  if(l<1.6){
    const cam=kf(l,[[0,{x:0,y:0,z:1,r:0}],[1.6,{x:BX,y:BY,z:10,r:0},inn]]);
    background(cam);camera(cam);phone(0,0,sentUI());overlay(LC[7],seg(l,1.1,1.6));return;
  }
  const m=l-1.6,keys=[[0,0]];for(let i=1;i<STAGES.length;i++){keys.push([STAGES[i].t-0.6,(i-1)*300],[STAGES[i].t,i*300])}
  const py=kf(m,keys),cy=py+30;
  const cam={x:lerp(0,700,io(seg(m,10.9,11.9))),y:py-230,z:kf(m,[[0,3.2],[0.9,1,out]])};
  background(cam);camera(cam);
  let cur=0;for(let i=0;i<STAGES.length;i++)if(m>=STAGES[i].t)cur=i;bands(cur,cam.x);
  if(m<4.3){
    const enc=seg(m,1.7,2.9),label=m<1.7?MSG:scramble(MSG,CIPH,enc,m,1),col=m<2.1?LC[7]:LC[6];
    chunk(PX-280,cy,560,96,col,label,{fam:m<1.7?DISP:MONO,size:m<1.7?36:32,glow:m<0.9?0:18});
    lock(PX+300,cy-92,back(seg(m,1.7,2.2)),out(seg(m,1.7,2.0)));
  }else if(m<5.5){
    const sp=io(seg(m,4.3,5.5));
    for(let n=1;n<=3;n++){const w=lerp(186.7,220,sp),x0=PX-280+(n-1)*186.7,x=lerp(x0,PX-110,sp),y=cy+(n-2)*100*sp;
      chunk(x,y,w,lerp(96,72,sp),LC[6],piece(n),{fam:MONO,size:28,r:12})}
  }else{
    const bits=io(seg(m,10.1,11.0)),fade=1-seg(m,11.0,11.6);
    for(let n=1;n<=3;n++){const y=cy+(n-2)*100,r=n-1;
      const items=[
        {w:104,col:LC[2],label:'MAC',p:seg(m,8.6+r*0.15,9.1+r*0.15)},
        {w:160,col:LC[3],label:'IP A→B',p:seg(m,7.6+r*0.2,8.1+r*0.2)},
        {w:120,col:LC[4],label:`TCP ${n}`,p:seg(m,5.7+r*0.25,6.2+r*0.25)},
        {w:220,col:LC[6],label:piece(n),p:1,size:28},
        {w:92,col:LC[2],label:'FCS',p:seg(m,8.9+r*0.15,9.4+r*0.15),from:'right'}];
      ctx.save();ctx.globalAlpha=1-bits;row(PX,y,items,72);ctx.restore();
      if(bits>0){let b='';for(let i=0;i<34;i++)b+=hash(i+n*50,Math.floor(m*10))>0.5?'1':'0';T(b,PX,y+2,{size:30,fam:MONO,weight:700,color:LC[1],alpha:bits*fade,glow:20,ls:2})}
    }
    const wv=seg(m,11.0,12.0);
    if(wv>0){const x0=PX-380,x1=x0+2600*io(wv);ctx.save();ctx.strokeStyle=LC[1];ctx.lineWidth=7;ctx.shadowColor=LC[1];ctx.shadowBlur=30;ctx.beginPath();
      for(let x=x0;x<=x1;x+=6){const y=cy+Math.sin((x-m*900)/34)*46*clamp((x-x0)/200);x===x0?ctx.moveTo(x,y):ctx.lineTo(x,y)}ctx.stroke();ctx.restore()}
  }
  stageHud(m,STAGES,'DANS LE TÉLÉPHONE · ÉTAPE');
  overlay(LC[7],1-seg(m,0,0.35));overlay(C.bg,seg(m,11.55,11.9));
}

/* --- 3. Le voyage : antenne, câble sous-marin, data center, Paris (un seul monde continu) ---------------- */
const DC_X=5640,TOWER_A=560,TOWER_P=6150,GROUND=900;
const PATH=[],PI={};
(function(){
  const add=(n,x,y)=>{if(n)PI[n]=PATH.length;PATH.push([x,y])};
  add('phone',130,820);add('top',TOWER_A,422);add('base',TOWER_A,892);add('st',790,892);
  for(const p of cablePath(60)){if(p[0]>=1500&&PI.slopeEnd===undefined)PI.slopeEnd=PATH.length;if(p[0]>=4500&&PI.farStart===undefined)PI.farStart=PATH.length;PATH.push(p)}
  add('stP',5228,892);add('dcIn',5340,860);add('r1',5420,700);add('r2',5500,640);add('r3',5580,740);add('r4',5660,650);add('r5',5760,720);add('dcOut',5940,700);add('exitP',6020,860);add('baseP',TOWER_P,892);add('topP',TOWER_P,422);
})();
const CUM=[0];for(let i=1;i<PATH.length;i++)CUM.push(CUM[i-1]+Math.hypot(PATH[i][0]-PATH[i-1][0],PATH[i][1]-PATH[i-1][1]));
const TOT=CUM[CUM.length-1],fr=n=>CUM[PI[n]]/TOT,GAP=80/TOT;
const FRAC=[[0.3,fr('phone')],[3.0,fr('top')],[4.6,fr('base')],[6.0,fr('st')],[8.8,fr('slopeEnd')],[15.0,fr('farStart')],[17.0,fr('stP')],[18.0,fr('dcIn')],[19.8,fr('dcOut')],[20.9,fr('baseP')],[22.0,fr('topP')]];
const wrap=(x,a,b)=>a+(((x-a)%(b-a))+(b-a))%(b-a);
function packetAt(u,i){const f=kf(u,FRAC,x=>x)-i*GAP;return f<=0?PATH[0]:polyPos(PATH,Math.min(1,f))}
function s3(t){
  const u=t-22;
  const cam=kf(u,[[0,{x:330,y:640,z:1.0,r:0}],[3.0,{x:560,y:640,z:1.1,r:0}],[4.6,{x:640,y:800,z:1.0,r:0}],[6.0,{x:900,y:1000,z:0.9,r:0}],[8.8,{x:1700,y:1520,z:0.62,r:0}],
    [15.0,{x:4700,y:1480,z:0.62,r:0}],[17.0,{x:5300,y:1150,z:0.8,r:0}],[18.2,{x:5640,y:720,z:0.95,r:0}],[19.8,{x:5860,y:720,z:1.0,r:0}],[20.9,{x:6040,y:640,z:1.08,r:0}],[22,{x:6150,y:580,z:1.2,r:0}]],x=>io(x));
  cameraR(cam);
  sky(-1500,7600,-2600,GROUND,t,{stars:520,moon:[1700,-250]});
  // terres
  ctx.fillStyle=vgrad(0,GROUND,GROUND+500,[[0,'#262d5e'],[1,WC.land]]);ctx.fillRect(-1500,GROUND,2320,2800);ctx.fillRect(5200,GROUND,2400,2800);ctx.fillStyle='rgba(255,255,255,0.06)';ctx.fillRect(-1500,GROUND+70,2320,5);ctx.fillRect(5200,GROUND+70,2400,5);
  city(-1300,GROUND,22,{far:true,seed:12,minH:90,varH:240,body:'#1a2150',fog:'#070b1f'});city(-1000,GROUND,13,{seed:11,minH:120,varH:200,gap:24,body:'#222a55'});
  city(5300,GROUND,24,{far:true,seed:21,minH:90,varH:240,body:'#1a2150',fog:'#070b1f',warm:'#ffe3a8'});city(6340,GROUND,9,{seed:22,minH:120,varH:200,gap:24,body:'#222a55',warm:'#ffe3a8'});
  ocean(800,5300,t);boat(1900,t,1);boat(2950,t,1.1);boat(4150,t,0.9);
  whale(wrap(2300+t*28,1700,4700),1330,1.1,1,t);
  for(let j=0;j<6;j++){const dir=j%2?1:-1,bx=wrap(2000+j*520+t*60*dir,1500,4900),by=1180+hash(j,41)*380;
    for(let k=0;k<5;k++)fish(bx+k*38*-dir,by+Math.sin(t*2+k+j)*14+k*10,0.9,dir,t,mix('#7fd6e6','#f2c14e',hash(j,k)),k+j)}
  seaCable(800,5300,t);
  // côté Dakar
  const ringA=out(seg(u,2.4,3.0))*(1-seg(u,4.0,4.6));
  tower(TOWER_A,GROUND,470,{t,act:ringA});landingStation(790,GROUND,t);
  // radio du téléphone vers l'antenne
  const wa=1-seg(u,2.6,3.4);miniPhone(130,830,'Awa');
  if(wa>0){ctx.save();ctx.strokeStyle=LC[1];ctx.lineWidth=5;const ang=Math.atan2(422-820,TOWER_A-130);
    for(let k=0;k<4;k++){const r=((u*0.9+k/4)%1)*420;ctx.globalAlpha=wa*(1-r/420);ctx.beginPath();ctx.arc(130,800,r,ang-0.4,ang+0.4);ctx.stroke()}ctx.restore()}
  // côté Paris
  const dcr=dataCenter(DC_X,GROUND,t);landingStation(5228,GROUND,t);
  tower(TOWER_P,GROUND,470,{t,act:out(seg(u,20.6,21.2))});
  // morceaux
  const sc=clamp(1/cam.z,1,1.9);
  for(let i=2;i>=0;i--){if(u<0.25&&i>0)continue;const p=packetAt(u,i);
    if(u>0.3){ctx.save();for(let k=5;k>=1;k--){const q=kf(u,FRAC,x=>x)-i*GAP-k*0.0012;if(q<=0)continue;const [x,y]=polyPos(PATH,q);ctx.globalAlpha=0.35*(1-k/6);ctx.fillStyle=LC[3];ctx.beginPath();ctx.arc(x,y,(15-k*1.5)*sc,0,7);ctx.fill()}ctx.restore()}
    ctx.save();ctx.translate(p[0],p[1]);ctx.scale(sc,sc);chunk(-44,0,88,42,LC[3],`#${i+1}`,{size:24,glow:30,r:21});ctx.restore()}
  // marge de neige marine (espace écran, décalée par la caméra)
  screen();if(cam.y>1000){ctx.fillStyle='#cfeaff';for(let i=0;i<70;i++){const sx=((hash(i,51)*W*1.6-cam.x*cam.z*0.35+t*(8+hash(i,52)*14))%(W*1.2)+W*1.2)%(W*1.2)-W*0.1,sy=((hash(i,53)*H*1.2+t*(10+hash(i,54)*18))%H);
    ctx.globalAlpha=0.12+0.2*hash(i,55);ctx.beginPath();ctx.arc(sx,sy,1.5+hash(i,56)*2.5,0,7);ctx.fill()}ctx.globalAlpha=1}
  pill('ANTENNE → CÂBLE',540,1700,LC[1],out(seg(u,0.6,1.0))*(1-seg(u,5.0,5.4)));
  pill('AU FOND DE L’OCÉAN',540,1700,LC[3],out(seg(u,8.6,9.0))*(1-seg(u,14.4,14.8)));
  pill('CENTRE DE DONNÉES',540,1700,LC[4],out(seg(u,17.6,18.0))*(1-seg(u,20.2,20.6)));
  overlay(C.bg,1-seg(u,0,0.35));overlay(C.bg,seg(u,21.55,22));
}

/* --- 4. Paris : l'arrivée, le réassemblage, le sourire, la réponse --------------------------------------- */
const HAL=houseAnchors(0,0,{flip:true});
const LEA_PHONE=personPhonePos(HAL.seatX,HAL.seatY,{...LEA,pose:'sitPhone'});
function s4(t){
  const k=t-44,keep={x:LEA_PHONE[0],y:LEA_PHONE[1],z:ZEND,r:-0.25};
  const cam=kf(k,[[0,{x:0,y:-210,z:1.05,r:0}],[2.2,{x:-30,y:-235,z:2.0,r:0}],[3.3,keep,inn],[7.3,keep],[8.6,{x:-30,y:-250,z:2.2,r:0}],[11,{x:-20,y:-262,z:2.4,r:0}]]);
  cameraR(cam);nightScene(0,t,{moon:[-620,-640],seed:7,warm:'#ffe3a8'});
  house(0,0,{palette:'paris',flip:true,t,dark:0.2});glowAt(0,30,520,'rgba(190,210,255,0.8)',0.14);
  // morceaux qui entrent par la fenêtre
  const wx=HAL.windowX,wy=-325;
  for(let i=0;i<3;i++){const a=seg(k,0.4+i*0.25,2.2+i*0.15);if(a<=0||a>=1)continue;const e=io(a),x=lerp(wx,LEA_PHONE[0],e),y=lerp(wy,LEA_PHONE[1],e)-Math.sin(e*Math.PI)*70;
    ctx.save();ctx.translate(x,y);ctx.scale(0.8,0.8);chunk(-44,0,88,42,LC[3],`#${i+1}`,{size:24,glow:30,r:21,alpha:1-seg(a,0.85,1)});ctx.restore()}
  // interface de Léa
  const recvIn=seg(k,5.0,5.9),replyN=Math.floor(seg(k,9.0,10.2)*REPLY.length),sentR=k>=10.5,flyR=out(seg(k,10.5,11.0)),pressR=k>10.35&&k<10.65?Math.sin(seg(k,10.35,10.65)*Math.PI):0;
  const bub=[];
  if(recvIn>0)bub.push({edge:-244,y:-300,text:scramble(CIPH,MSG,recvIn,k,7),side:'left',col:C.chip,tc:C.ink,alpha:seg(k,4.9,5.2)});
  if(sentR)bub.push({edge:lerp(150,244,flyR),y:lerp(442,-170,flyR),text:REPLY,side:'right',col:LC[3],s:lerp(0.6,1,flyR)});
  const ui={contact:'Awa',avatar:LC[7],input:sentR?'':REPLY.slice(0,replyN),press:pressR,bubbles:bub};
  const happy=k>=8.6;
  person(HAL.seatX,HAL.seatY,{...LEA,pose:happy?'sitHappy':'sitPhone',t,typing:k>9.0&&k<10.3,glow:k>0.3?1:0,thumbA:1-seg(k,2.6,3.2)*(1-seg(k,8.3,9.0)),phoneUI:ui});
  // réassemblage dans l'écran (repère écran, l'écran du téléphone fait 560 px de large, centré)
  if(k>3.2&&k<5.2){
    screen();const slot=i=>300+i*190,order=[1,3,2],sw=io(seg(k,4.0,4.5)),conv=io(seg(k,4.7,5.1)),tx=540-244+BW/2,ty=960-300;
    for(let i=0;i<3;i++){const n=order[i],ap=out(seg(k,3.3+i*0.15,3.9+i*0.15));let si=i;if(n===3)si=lerp(1,2,sw);if(n===2)si=lerp(2,1,sw);
      const yy=1180+Math.sin(sw*Math.PI)*(n===3?-60:n===2?60:0),xx=lerp(1300,slot(si),ap);
      ctx.save();ctx.globalAlpha=1-conv;chunk(lerp(xx,tx-44,conv)-0,lerp(yy,ty,conv),94,56,LC[6],piece(n),{fam:MONO,size:22,r:14});ctx.restore()}
    T('arrivés dans le désordre : 1, 3, 2',540,1290,{size:26,fam:MONO,color:LC[4],alpha:out(seg(k,3.7,4.0))*(1-seg(k,4.4,4.7))});
  }
  screen();const tag=out(seg(k,0.2,0.7))*(1-seg(k,2.0,2.5));
  T('PARIS',76,170,{size:30,fam:MONO,weight:700,color:LC[3],align:'left',ls:8,alpha:tag});
  overlay(C.bg,1-seg(k,0,0.35));overlay(C.bg,seg(k,10.7,11));
}

/* --- 5. Récapitulatif ------------------------------------------------------------------------------------ */
function s5(t){
  const l=t-55;background(null);screen();
  T('DAKAR → PARIS',540,250,{size:30,fam:MONO,weight:700,color:LC[7],ls:6,alpha:out(seg(l,0.1,0.5))});
  const A=[250,860],B=[830,860];
  ctx.save();ctx.globalAlpha=0.35*out(seg(l,0.2,0.8));ctx.strokeStyle=LC[3];ctx.lineWidth=3;for(let k=0;k<4;k++){ctx.beginPath();for(let x=140;x<=940;x+=10){const y=1010+k*26+Math.sin(x/70+l*2+k)*8;x===140?ctx.moveTo(x,y):ctx.lineTo(x,y)}ctx.stroke()}ctx.restore();
  ctx.globalAlpha=out(seg(l,0.3,0.8));for(const [pt,nm] of [[A,'Awa'],[B,'Léa']]){ctx.save();ctx.translate(pt[0],pt[1]);ctx.scale(1.5,1.5);miniPhone(0,0,nm);ctx.restore()}ctx.globalAlpha=1;
  const P=[[A[0],A[1]-190],[A[0]+60,560],[B[0]-60,560],[B[0],B[1]-190]],p=io(seg(l,0.8,3.6));
  ctx.save();ctx.strokeStyle=C.line;ctx.lineWidth=4;ctx.setLineDash([12,12]);ctx.beginPath();ctx.moveTo(...P[0]);ctx.bezierCurveTo(...P[1],...P[2],...P[3]);ctx.stroke();ctx.restore();
  if(p>0&&p<1){const q=p,mt=1-q,x=mt*mt*mt*P[0][0]+3*mt*mt*q*P[1][0]+3*mt*q*q*P[2][0]+q*q*q*P[3][0],y=mt*mt*mt*P[0][1]+3*mt*mt*q*P[1][1]+3*mt*q*q*P[2][1]+q*q*q*P[3][1];
    ctx.save();ctx.fillStyle='#fff';ctx.shadowColor='#fff';ctx.shadowBlur=30;ctx.beginPath();ctx.arc(x,y,16,0,7);ctx.fill();ctx.restore()}
  const a=out(seg(l,0.9,1.4));
  T('Un message',540,1380+(1-a)*30,{size:140,weight:800,alpha:a,ls:-4});
  T('des océans traversés',540,1500,{size:60,weight:700,alpha:out(seg(l,1.5,2.0))});
  T('en un clin d’œil',540,1585,{size:46,weight:500,color:C.dim,alpha:out(seg(l,1.9,2.4))});
}

function renderAt(t){
  t=clamp(t,0,DUR);screen();ctx.globalAlpha=1;ctx.setLineDash([]);ctx.fillStyle='#000';ctx.fillRect(0,0,W,H);
  if(t<8.5)s1(t);else if(t<22)s2(t);else if(t<44)s3(t);else if(t<55)s4(t);else s5(t);
  screen();const v=ctx.createRadialGradient(W/2,H/2,H*0.32,W/2,H/2,H*0.78);v.addColorStop(0,'rgba(0,0,0,0)');v.addColorStop(1,'rgba(0,0,0,0.38)');ctx.fillStyle=v;ctx.fillRect(0,0,W,H);
}
const SFX=(()=>{const e=[];const add=(at,type,k=0)=>e.push({at,type,k});
  for(let i=0;i<MSG.length;i++)add(1.0+i*0.167,'tick');add(5.0,'pop');add(5.3,'whoosh');add(7.0,'whoosh');
  add(10.1,'impact');for(const d of [10.8,13.8,16.8,19.6])add(d,'whooshDown');add(11.8,'glitch',1);add(11.9,'clip');add(14.4,'split');
  for(let r=0;r<3;r++){add(15.8+r*0.25,'clip');add(17.7+r*0.2,'clip');add(18.9+r*0.15,'clip')}
  add(20.2,'bits',3);add(21.3,'whoosh');
  add(22.0,'whoosh');add(25.0,'ping');add(28.0,'whooshDown');add(30.8,'whoosh');for(let i=0;i<3;i++)add(31+i*1.2,'blip',i);add(35.0,'whoosh');add(39.6,'bits',4);add(41.5,'scan');add(43.0,'ping');
  add(44.4,'pop');add(46.2,'whoosh');add(47.4,'clip');add(48.2,'unclip');add(49.0,'glitch',2);add(50.0,'ping');
  for(let i=0;i<REPLY.length;i++)add(53.0+i*0.12,'tick');add(54.5,'pop');add(55.1,'hit');add(56.3,'whoosh');
  return e.sort((a,b)=>a.at-b.at)})();
window.VIDEO={duration:DUR,fps:FPS,narration:NARRATION,sfx:SFX};
window.renderAt=renderAt;
