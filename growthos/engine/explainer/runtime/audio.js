/* audio.js — synthe de bruitages (direct + hors ligne) et rendu WAV
   Extrait tel quel du prototype reference/voyage-message.html (phase 1) : aucun changement de comportement. */
/* sound design: one synth, used live (AudioContext) and offline (OfflineAudioContext for the MP4) */
const NOISE=new WeakMap();
function noise(ac){if(NOISE.has(ac))return NOISE.get(ac);const b=ac.createBuffer(1,ac.sampleRate,ac.sampleRate),d=b.getChannelData(0);
  for(let i=0;i<d.length;i++)d[i]=hash(i,7)*2-1;NOISE.set(ac,b);return b}
function env(ac,dest,when,peak,att,dec){const g=ac.createGain();g.gain.setValueAtTime(0.0001,when);g.gain.exponentialRampToValueAtTime(peak,when+att);g.gain.exponentialRampToValueAtTime(0.0001,when+att+dec);g.connect(dest);return g}
function tone(ac,dest,when,type,f0,f1,dur,peak){const o=ac.createOscillator();o.type=type;o.frequency.setValueAtTime(f0,when);o.frequency.exponentialRampToValueAtTime(f1,when+dur);
  o.connect(env(ac,dest,when,peak,0.005,dur));o.start(when);o.stop(when+dur+0.05)}
function burst(ac,dest,when,dur,peak,type,f0,f1,q=1){const s=ac.createBufferSource();s.buffer=noise(ac);const f=ac.createBiquadFilter();f.type=type;f.Q.value=q;
  f.frequency.setValueAtTime(f0,when);f.frequency.exponentialRampToValueAtTime(f1,when+dur);s.connect(f);f.connect(env(ac,dest,when,peak,dur*0.35,dur*0.65));s.start(when,hash(when*1000|0)*0.5);s.stop(when+dur+0.05)}
function sfx(ac,dest,when,type,k=0){
  switch(type){
    case 'tick':burst(ac,dest,when,0.03,0.12,'highpass',3500,4500);break;
    case 'pop':tone(ac,dest,when,'sine',620,300,0.14,0.35);break;
    case 'clip':tone(ac,dest,when,'square',1150,1100,0.03,0.07);tone(ac,dest,when+0.045,'square',1600,1550,0.03,0.07);break;
    case 'unclip':tone(ac,dest,when,'square',1600,1550,0.03,0.07);tone(ac,dest,when+0.045,'square',1050,1000,0.03,0.07);break;
    case 'whoosh':burst(ac,dest,when,0.7,0.32,'bandpass',300,3200,0.9);break;
    case 'whooshDown':burst(ac,dest,when,0.5,0.22,'bandpass',2400,400,1.2);break;
    case 'drop':tone(ac,dest,when,'sine',240,110,0.18,0.3);break;
    case 'impact':tone(ac,dest,when,'sine',130,45,0.5,0.7);burst(ac,dest,when,0.25,0.25,'lowpass',2000,300);break;
    case 'glitch':for(let i=0;i<8;i++)tone(ac,dest,when+i*0.045,'square',300+hash(i,k)*1500,300+hash(i,k+9)*1500,0.03,0.05);break;
    case 'split':[520,680,860].forEach((f,i)=>tone(ac,dest,when+i*0.07,'sine',f,f*0.8,0.1,0.25));break;
    case 'bits':for(let i=0;i<14;i++)tone(ac,dest,when+i*0.035,'square',900+hash(i,k)*1600,900+hash(i,k)*1600,0.018,0.04);break;
    case 'blip':tone(ac,dest,when,'sine',880+k*120,880+k*120,0.09,0.2);break;
    case 'scan':tone(ac,dest,when,'sawtooth',260,1300,0.55,0.05);break;
    case 'ping':tone(ac,dest,when,'sine',1320,1310,0.6,0.25);tone(ac,dest,when+0.09,'sine',1980,1970,0.5,0.16);break;
    case 'hit':sfx(ac,dest,when,'impact');tone(ac,dest,when+0.02,'triangle',440,440,1.2,0.12);tone(ac,dest,when+0.02,'triangle',660,660,1.2,0.08);break;
  }
}


/* Rend la piste sonore (SFX) de la video courante en WAV encode base64. Lit VIDEO.duration et VIDEO.sfx. */
window.renderAudio=async function(){
  const sr=48000,ac=new OfflineAudioContext(2,Math.ceil(sr*VIDEO.duration),sr),comp=ac.createDynamicsCompressor(),m=ac.createGain();m.gain.value=0.9;m.connect(comp);comp.connect(ac.destination);
  for(const e of VIDEO.sfx)sfx(ac,m,e.at+0.001,e.type,e.k);
  const buf=await ac.startRendering(),L=buf.getChannelData(0),R=buf.getChannelData(1),n=L.length,dv=new DataView(new ArrayBuffer(44+n*4));
  const ws=(o,s)=>{for(let i=0;i<s.length;i++)dv.setUint8(o+i,s.charCodeAt(i))};
  ws(0,'RIFF');dv.setUint32(4,36+n*4,true);ws(8,'WAVE');ws(12,'fmt ');dv.setUint32(16,16,true);dv.setUint16(20,1,true);dv.setUint16(22,2,true);
  dv.setUint32(24,sr,true);dv.setUint32(28,sr*4,true);dv.setUint16(32,4,true);dv.setUint16(34,16,true);ws(36,'data');dv.setUint32(40,n*4,true);
  for(let i=0;i<n;i++){dv.setInt16(44+i*4,clamp(L[i],-1,1)*32767,true);dv.setInt16(46+i*4,clamp(R[i],-1,1)*32767,true)}
  const bytes=new Uint8Array(dv.buffer);let s='';for(let i=0;i<bytes.length;i+=32768)s+=String.fromCharCode.apply(null,bytes.subarray(i,i+32768));return btoa(s);
};

