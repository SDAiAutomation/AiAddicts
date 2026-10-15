/* player.js — lecteur de previsualisation (jamais utilise par le rendu MP4)
   Extrait tel quel du prototype reference/voyage-message.html (phase 1) : aucun changement de comportement. */
const playBtn=document.getElementById('play'),sndBtn=document.getElementById('snd'),seek=document.getElementById('seek'),timeEl=document.getElementById('time'),voText=document.getElementById('voText');
let t=0,prev=0,playing=!matchMedia('(prefers-reduced-motion: reduce)').matches,last=null,ac=null,master=null,stopped=false;
const fmt=s=>`${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`;
function voAt(t){let s='';for(const [at,line] of VIDEO.narration)if(t>=at)s=line;return s}
function ui(){seek.value=t;timeEl.textContent=fmt(t)+' / '+fmt(VIDEO.duration);playBtn.textContent=playing?'Pause':(t>=VIDEO.duration?'Rejouer':'Lecture');const v=voAt(t);if(voText.textContent!==v)voText.textContent=v}
function loop(now){
  if(stopped)return;
  if(playing){if(last!==null)t=Math.min(VIDEO.duration,t+(now-last)/1000);last=now;if(t>=VIDEO.duration)playing=false;
    if(ac&&ac.state==='running')for(const e of VIDEO.sfx)if(e.at>prev&&e.at<=t)sfx(ac,master,ac.currentTime+0.01,e.type,e.k);}
  else last=null;
  prev=t;renderFrame(t);ui();requestAnimationFrame(loop);
}
playBtn.onclick=()=>{if(t>=VIDEO.duration){t=0;prev=0}playing=!playing;};
sndBtn.onclick=()=>{try{if(!ac){ac=new (window.AudioContext||window.webkitAudioContext)();master=ac.createGain();master.gain.value=0.8;master.connect(ac.destination)}
  const on=sndBtn.getAttribute('aria-pressed')!=='true';sndBtn.setAttribute('aria-pressed',String(on));if(on)ac.resume();else ac.suspend();}catch(e){}};
seek.oninput=()=>{t=+seek.value;prev=t;};
window.__stop=()=>{stopped=true};
renderFrame(1.2);ui();
(document.fonts?document.fonts.ready:Promise.resolve()).then(()=>requestAnimationFrame(loop));

