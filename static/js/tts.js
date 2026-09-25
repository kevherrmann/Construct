// CONSTRUCT — Vorlesen über Gemini TTS
// ---------- Vorlesen (Gemini TTS, /api/tts) ----------
// Nur der gesprochene Text: Werkzeug-Zeilen, Statistik und Codeblöcke fliegen raus.
let sayAudio=null,sayBtn=null;
function sayText(bubble){
  const c=bubble.cloneNode(true);
  c.querySelectorAll('.tool,.statline,.thinking,.thinkmark,.copy-btn,.err,pre').forEach(e=>e.remove());
  const segs=c.querySelectorAll('.seg');
  return (segs.length?[...segs].map(e=>e.innerText).join('\n'):c.innerText).trim();
}
function sayStop(){
  if(sayAudio){sayAudio.pause();URL.revokeObjectURL(sayAudio.src);sayAudio=null;}
  if(sayBtn){sayBtn.classList.remove('on');sayBtn.textContent='🔊';sayBtn=null;}
}
async function sayPlay(text,btn,opts){
  sayStop();
  if(!text)return;
  sayBtn=btn||null;
  if(btn){btn.classList.add('on');btn.textContent='⏳';}
  try{
    const r=await fetch('/api/tts',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text,...(opts||{})})});
    if(!r.ok){let m='Vorlesen fehlgeschlagen';try{m=(await r.json()).error||m;}catch{}throw new Error(m);}
    const url=URL.createObjectURL(await r.blob());
    if(sayBtn!==(btn||null)){URL.revokeObjectURL(url);return;}   // inzwischen etwas anderes gestartet
    sayAudio=new Audio(url);
    if(btn)btn.textContent='⏹';
    sayAudio.onended=sayStop;
    await sayAudio.play();
  }catch(e){
    sayStop();
    if(btn){btn.textContent='⚠';btn.title=e.message;setTimeout(()=>{btn.textContent='🔊';btn.title='Vorlesen';},3000);}
    else throw e;
  }
}
document.addEventListener('click',e=>{
  const b=e.target.closest('.say-btn');if(!b)return;
  if(b===sayBtn){sayStop();return;}
  const bubble=b.closest('.msgcol')?.querySelector('.bubble');
  if(bubble)sayPlay(sayText(bubble),b);
});
// Absolute Workspace-Pfade in Codys Antworten anklickbar machen (Vorschau/Download)
const PATH_RE=/(^|[\s('"„`>])(\/(?:home|Users)\/[\w.\-\/]+\.[\w]{1,8})/g;
function linkifyPaths(el){
  if(!el)return;
  const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT,{acceptNode:n=>
    n.parentElement&&n.parentElement.closest('a')?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});
  const nodes=[];let n;while(n=walker.nextNode()){if(PATH_RE.test(n.nodeValue))nodes.push(n);PATH_RE.lastIndex=0;}
  nodes.forEach(node=>{
    const frag=document.createDocumentFragment();let last=0;const s=node.nodeValue;let m;
    PATH_RE.lastIndex=0;
    while((m=PATH_RE.exec(s))){
      frag.appendChild(document.createTextNode(s.slice(last,m.index)+m[1]));
      const a=document.createElement('a');a.href='/api/file?path='+encodeURIComponent(m[2]);
      a.target='_blank';a.rel='noopener';a.textContent=m[2];a.title='Datei ansehen (Rechtsklick → Speichern)';
      frag.appendChild(a);last=m.index+m[0].length;
    }
    frag.appendChild(document.createTextNode(s.slice(last)));
    node.parentNode.replaceChild(frag,node);
  });
}

