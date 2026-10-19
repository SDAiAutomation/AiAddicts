/* scenes.js — scènes types : des séquences ILLUSTRÉES complètes, extraites de la vitrine « Dakar → Paris » écrite à la main
   (décor plein cadre, personnage, téléphone, caméra). L'animateur les choisit et les règle avec des temps (S.template) au lieu
   de dessiner lui-même ces mondes. Temps LOCAUX au plan, comme les gabarits de templates.js. */
(()=>{
const F=Faceloop,reg=F.registerTemplate;
const PHK=56/1100;                                   // le téléphone tenu en main = phone() réduit à cette échelle
const PRESETS={
  awa:{skin:'#6b4128',hair:'#150e0c',style:'braids',top:'accent',pants:'#222a55',pid:1},
  lea:{skin:'#f1c9a5',hair:'#3a2316',style:'bun',top:'#5fb3a1',pants:'#2b3566',pid:2},
  malik:{skin:'#9a6240',hair:'#1a1210',style:'short',top:'#3fd0c9',pants:'#1b1f3a',pid:3},
  sam:{skin:'#d79b6d',hair:'#2a1a10',style:'curly',top:'#f2c14e',pants:'#222a55',pid:4},
};
const CIPH='x9#Fq@7%kL2!vR8&Zt';
const cipherOf=n=>{let s='';while(s.length<n)s+=CIPH;return s.slice(0,n)};
const enter=(h,t,how='up',dur=0.45)=>{if((t??0)<=0.05)return h;return h.appear(t,dur,how)};

/* ---- le guide : un personnage debout, en bas d'un coin, qui réagit à ce que dit la voix (salue, montre, réfléchit, applaudit) ---- */
/* À ajouter À CÔTÉ d'un autre gabarit (equation, bars, bullets...) : il donne de la vie aux infographies.
   params : {who:'awa'|'lea'|'malik'|'sam'|{...}, side:'left'|'right', size?:0.7-1.1, y?, t?, poses:[{t, pose}], say:[{t, text, until?}]}
   poses : stand | wave | point | think | cheer. Garde-le petit (size <= 0.9) pour ne pas couvrir le contenu. */
F.registerKind('guide',{pose:'stand',skin:'#9a6240',hair:'#150e0c',style:'short',top:'#ff8a5b',pants:'#222a55',flip:false,pid:1,bubble:''},(p,t)=>{
  personStand(0,0,{s:1,skin:F.col(p.skin),hair:F.col(p.hair),style:p.style,top:F.col(p.top),pants:F.col(p.pants),t,flip:p.flip,id:p.pid,pose:p.pose});
  if(p.bubble){const size=36,w=Math.min(520,measure(p.bubble,size,700)+56),h=size*2.1,d=p.flip?-1:1,bx=d*(w/2+10),by=-405;
    ctx.fillStyle=F.col('white');rr(bx-w/2,by-h/2,w,h,h*0.42);ctx.fill();
    ctx.beginPath();ctx.moveTo(d*10,by+h/2-2);ctx.lineTo(d*34,by+h/2-2);ctx.lineTo(d*16,by+h/2+24);ctx.fill();
    T(p.bubble,bx,by+2,{size,weight:700,color:F.col('dark'),maxW:w-40})}
});
reg('guide',(S,p)=>{
  const who=typeof p.who==='object'?Object.assign({},PRESETS.awa,p.who):Object.assign({},PRESETS[p.who||'awa']||PRESETS.awa);
  const right=p.side==='right',size=p.size??0.9,g=S.add('guide',{x:right?900:180,y:p.y??1620,s:1.25*size,flip:right,...who,pose:(p.poses&&p.poses[0]&&p.poses[0].pose)||'stand'});
  enter(g,p.t??0,'up');
  (p.poses||[]).forEach(({t,pose})=>{if(t>0)g.set(t,{pose})});
  (p.say||[]).forEach(({t,text,until})=>{g.set(t,{bubble:String(text)});g.set(until??t+2.6,{bubble:''})});
  return [g]});

/* ---- la pièce : une personne chez elle avec son téléphone (envoyer / recevoir / répondre / sourire) --------------------- */
/* params : {place:'dakar'|'paris', who:'awa'|'lea'|'malik'|'sam'|{...props person}, tag?, contact?, message?,
             typeFrom?, sendAt?, previous?, receiveAt?, reply?, replyFrom?, replyAt?, smileAt?, zoomPhone?:{t0,t1}, zoomOut?:{t0,t1}} */
reg('room',(S,p)=>{
  const place=p.place==='paris'?'paris':'dakar',flip=place==='paris'||p.flip===true,hs=1.45,hx=540,hy=1300,ps=1.25*hs;
  const who=typeof p.who==='object'?Object.assign({},PRESETS.awa,p.who):Object.assign({},PRESETS[p.who||(place==='paris'?'lea':'awa')]||PRESETS.awa);
  const px=flip?hx+110*hs:hx-120*hs,py=hy-106*hs;
  const pp=personPhonePos(px,py,{s:ps,flip,pose:'sitPhone'}),dir=flip?-1:1;
  const msg=String(p.message||'Salut !'),contact=p.contact||(place==='paris'?'Awa':'Léa');
  S.sky('night');
  S.add('city',{x:-200,y:hy,count:12,seed:place==='paris'?7:3,far:true,par:0.5});
  S.add('box',{x:540,y:hy+450,w:2000,h:900,color:'#1a2150',corner:0,layer:-1});
  S.add('house',{x:hx,y:hy,s:hs,palette:place,flip,dark:0.22});
  const prev=p.previous===undefined?(p.sendAt!==undefined?'Tu es où ?':''):p.previous;
  const prevBubble=prev?[{edge:-244,y:-300,text:prev,side:'left',col:'chip',tc:'ink'}]:[];
  const ui=(o={})=>({contact,avatar:place==='paris'?'accent':'primary',input:'',bubbles:prevBubble,...o});
  const per=S.add('person',{x:px,y:py,s:ps,pose:'sitPhone',typing:false,glow:p.receiveAt!==undefined?0.2:1,flip,...who,ui:ui()});
  const out=[per];
  // mot-clé de lieu, visible dès la première image
  if(p.tag){const tg=enter(S.add('text',{text:p.tag,x:220,y:230,size:64,mono:true,weight:800,color:place==='paris'?'primary':'accent',ls:8,hud:true}),0,'up');
    tg.hide(Math.min((p.sendAt??p.receiveAt??S.dur*0.5)-0.3,3.4));out.push(tg)}
  const typeIn=(from,to,text,base)=>{const n=text.length;per.set(from,{typing:true});
    for(let i=1;i<=n;i++){const t=from+(to-from)*(i/n);per.set(t,{ui:ui({...base,input:text.slice(0,i)})});S.sfx(t,'tick')}
    per.set(to,{typing:false})};
  const sendIt=(at,text,bubbles,flyY)=>{
    per.to(at-0.15,at,{press:1},'out');per.to(at,at+0.2,{press:0},'io');
    per.set(at+0.05,{ui:ui({input:'',flyText:text,flyY,bubbles})});per.to(at+0.05,at+0.6,{fly:1},'out');
    per.set(at+0.62,{ui:ui({input:'',bubbles:[...bubbles,{edge:244,y:flyY,text,side:'right',col:'accent'}],sent:true,sentY:flyY}),fly:0});
    S.sfx(at,'pop');S.sfx(at+0.3,'whoosh')};
  // envoi
  if(p.sendAt!==undefined){const from=p.typeFrom??0.8;typeIn(from,p.sendAt-0.3,msg,{});sendIt(p.sendAt,msg,prevBubble,-110)}
  // réception : trois morceaux entrent par la fenêtre, le message se déchiffre
  let shown=prevBubble;
  if(p.receiveAt!==undefined){const r=p.receiveAt,wx=hx+(flip?-200:200)*hs,wy=hy-325*hs;
    per.to(Math.max(0,r-0.3),r,{glow:1},'out');S.sfx(r-0.1,'pop');
    for(let i=0;i<3;i++){const t0=r+0.2+i*0.25,t1=r+1.8+i*0.15;
      const c=S.add('chunk',{x:wx,y:wy,w:92,h:44,label:'#'+(i+1),color:'primary',glow:26,size:24,s:1.5,a:0});
      c.set(t0,{a:1});c.followKeys([[wx,wy],[(wx+pp[0])/2,Math.min(wy,pp[1])-160],[pp[0],pp[1]]],[[t0,0],[t1,1]]);c.set(t1+0.05,{a:0});out.push(c)}
    const t0=r+1.9,t1=r+2.9,steps=12,bub=text=>[{edge:-244,y:-300,text,side:'left',col:'chip',tc:'ink'}];
    for(let k=0;k<=steps;k++){const t=t0+(t1-t0)*k/steps,txt=k===steps?msg:scramble(cipherOf(msg.length),msg,k/steps,t,7);per.set(t,{ui:ui({bubbles:bub(txt)})})}
    shown=bub(msg);S.sfx(r+1.9,'glitch');S.sfx(t1,'ping')}
  // réponse
  if(p.reply){const to=p.replyAt??S.dur-1,from=p.replyFrom??to-1.6,flyY=p.receiveAt!==undefined?-170:-110;typeIn(from,to-0.3,p.reply,{bubbles:shown});sendIt(to,p.reply,shown,flyY)}
  if(p.smileAt!==undefined){per.set(p.smileAt,{pose:'sitHappy'})}
  // caméra : plan large, puis on s'approche du personnage ; zoom optionnel dans l'écran du téléphone
  const key=p.sendAt??p.receiveAt??S.dur*0.5,target={x:px+dir*35*ps,y:py-70*ps,z:2.0};
  S.cam.set(0,{x:540,y:1010,z:1.0,r:0});S.cam.to(0.2,Math.max(0.6,Math.min(key+(p.receiveAt!==undefined?1.2:0),S.dur-0.5)),target,'io');
  if(p.zoomPhone){const ZE=1/(PHK*ps);S.cam.to(p.zoomPhone.t0,p.zoomPhone.t1,{x:pp[0],y:pp[1],z:ZE,r:dir*0.25},'inn')}
  if(p.zoomOut){S.cam.to(p.zoomOut.t0,p.zoomOut.t1,{...target,z:2.2,r:0},'io')}
  return out});

/* ---- le trajet : antenne -> câble sous-marin -> data center -> antenne d'arrivée (un seul monde continu) ---------------- */
const GROUND=900,TOWER_A=560,TOWER_P=6150,DC_X=5640,UEND=22;
const PATH=[],PI={};
(()=>{const add=(n,x,y)=>{if(n)PI[n]=PATH.length;PATH.push([x,y])};
  add('phone',130,820);add('top',TOWER_A,422);add('base',TOWER_A,892);add('st',790,892);
  for(const q of cablePath(60)){if(q[0]>=1500&&PI.slopeEnd===undefined)PI.slopeEnd=PATH.length;if(q[0]>=4500&&PI.farStart===undefined)PI.farStart=PATH.length;PATH.push(q)}
  add('stP',5228,892);add('dcIn',5340,860);add('r1',5420,700);add('r2',5500,640);add('r3',5580,740);add('r4',5660,650);add('r5',5760,720);add('dcOut',5940,700);add('exitP',6020,860);add('baseP',TOWER_P,892);add('topP',TOWER_P,422)})();
const CUM=[0];for(let i=1;i<PATH.length;i++)CUM.push(CUM[i-1]+Math.hypot(PATH[i][0]-PATH[i-1][0],PATH[i][1]-PATH[i-1][1]));
const TOT=CUM[CUM.length-1],fr=n=>CUM[PI[n]]/TOT,GAP=80/TOT;
const FRAC=[[0.3,fr('phone')],[3.0,fr('top')],[4.6,fr('base')],[6.0,fr('st')],[8.8,fr('slopeEnd')],[15.0,fr('farStart')],[17.0,fr('stP')],[18.0,fr('dcIn')],[19.8,fr('dcOut')],[20.9,fr('baseP')],[22.0,fr('topP')]];
const CAM=[[0,{x:330,y:640,z:1.0}],[3.0,{x:560,y:640,z:1.1}],[4.6,{x:640,y:800,z:1.0}],[6.0,{x:900,y:1000,z:0.9}],[8.8,{x:1700,y:1520,z:0.62}],[15.0,{x:4700,y:1480,z:0.62}],
  [17.0,{x:5300,y:1150,z:0.8}],[18.2,{x:5640,y:720,z:0.95}],[19.8,{x:5860,y:720,z:1.0}],[20.9,{x:6040,y:640,z:1.08}],[22,{x:6150,y:580,z:1.2}]];
const wrap=(x,a,b)=>a+(((x-a)%(b-a))+(b-a))%(b-a);
F.registerKind('journeyworld',{t0:0,dur:22,label:'toi'},(p,t)=>{
  const u=(t-p.t0)*UEND/p.dur;
  ctx.fillStyle=vgrad(0,GROUND,GROUND+500,[[0,'#262d5e'],[1,WC.land]]);ctx.fillRect(-1500,GROUND,2320,2800);ctx.fillRect(5200,GROUND,2400,2800);
  ctx.fillStyle='rgba(255,255,255,0.06)';ctx.fillRect(-1500,GROUND+70,2320,5);ctx.fillRect(5200,GROUND+70,2400,5);
  city(-1300,GROUND,22,{far:true,seed:12,minH:90,varH:240,body:'#1a2150',fog:'#070b1f'});city(-1000,GROUND,13,{seed:11,minH:120,varH:200,gap:24,body:'#222a55'});
  city(5300,GROUND,24,{far:true,seed:21,minH:90,varH:240,body:'#1a2150',fog:'#070b1f',warm:'#ffe3a8'});city(6340,GROUND,9,{seed:22,minH:120,varH:200,gap:24,body:'#222a55',warm:'#ffe3a8'});
  ocean(800,5300,t);boat(1900,t,1);boat(2950,t,1.1);boat(4150,t,0.9);
  whale(wrap(2300+t*28,1700,4700),1330,1.1,1,t);
  for(let j=0;j<6;j++){const d=j%2?1:-1,bx=wrap(2000+j*520+t*60*d,1500,4900),by=1180+hash(j,41)*380;
    for(let k=0;k<5;k++)fish(bx+k*38*-d,by+Math.sin(t*2+k+j)*14+k*10,0.9,d,t,mix('#7fd6e6','#f2c14e',hash(j,k)),k+j)}
  seaCable(800,5300,t);
  tower(TOWER_A,GROUND,470,{t,act:out(seg(u,2.4,3.0))*(1-seg(u,4.0,4.6))});landingStation(790,GROUND,t);
  miniPhone(130,830,p.label);
  const wa=1-seg(u,2.6,3.4);
  if(wa>0){ctx.save();ctx.strokeStyle=LC[1];ctx.lineWidth=5;const ang=Math.atan2(422-820,TOWER_A-130);
    for(let k=0;k<4;k++){const r=((u*0.9+k/4)%1)*420;ctx.globalAlpha=wa*(1-r/420);ctx.beginPath();ctx.arc(130,800,r,ang-0.4,ang+0.4);ctx.stroke()}ctx.restore()}
  dataCenter(DC_X,GROUND,t);landingStation(5228,GROUND,t);
  tower(TOWER_P,GROUND,470,{t,act:out(seg(u,20.6,21.2))});
});
/* params : {t0?, dur?, label?} — t0 = début du trajet dans le plan, dur = durée du trajet (par défaut jusqu'à la fin du plan). */
reg('journey',(S,p)=>{
  const t0=p.t0??0,dur=p.dur??(S.dur-t0),k=dur/UEND,T=u=>t0+u*k;
  S.sky('night');
  const world=S.add('journeyworld',{x:0,y:0,t0,dur,label:p.label||'toi'});const out=[world];
  S.cam.set(0,{...CAM[0][1],r:0});for(let i=1;i<CAM.length;i++)S.cam.to(T(CAM[i-1][0]),T(CAM[i][0]),CAM[i][1],'io');
  for(let i=0;i<3;i++){
    const c=S.add('chunk',{x:130,y:820,w:88,h:42,label:'#'+(i+1),color:'primary',glow:30,size:24,a:0});
    c.set(T(0.2+i*0.1),{a:1});c.followKeys(PATH,FRAC.map(([u,f])=>[T(u),Math.max(0,f-i*GAP)]));
    c.to(T(8.4),T(8.8),{s:1.7},'io');c.to(T(16.6),T(17.2),{s:1},'io');out.push(c)}
  if(p.labels!==false){
    [['ANTENNE → CÂBLE',0.6,5.0,'violet'],['AU FOND DE L’OCÉAN',8.6,14.4,'primary'],['CENTRE DE DONNÉES',17.6,20.2,'good']].forEach(([txt,a,b,col])=>{
      const h=S.add('text',{text:txt,x:540,y:1540,size:64,weight:800,color:col,hud:true,maxW:960});h.appear(T(a),0.4,'up');h.hide(T(b),0.4);out.push(h)})}
  [[0,'whoosh'],[3,'ping'],[6,'whooshDown'],[8.8,'whoosh'],[13,'whoosh'],[17.2,'bits'],[20.9,'ping']].forEach(([u,type])=>S.sfx(T(u),type));
  return out});
})();
