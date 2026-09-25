// CONSTRUCT — Zustand, Hilfsfunktionen, parallele Unterhaltungen, Nachrichten
// ---------- State + Helpers ----------
let pending=[], currentCwd=null, openFolders={}, foldersCache=[];
const chat=document.getElementById('chat'), inp=document.getElementById('inp'), sidEl=document.getElementById('sid');
// ---------- Mehrere parallele Unterhaltungen (wie mehrere Terminals) ----------
// Jede Unterhaltung hat EIGENEN Zustand (sessionId, busy, queue, laufender Stream)
// und ein EIGENES, erhaltenes Chat-DOM (pane). Wechseln blendet nur um – die
// laufende Antwort einer anderen Session läuft im Hintergrund einfach weiter.
const conversations=new Map();   // key -> conv
let activeKey=null, convSeq=0;
function makeConv(opts={}){
  const key='conv'+(++convSeq)+'-'+Date.now().toString(36);
  const pane=document.createElement('div');pane.className='pane';
  // model: an DIESE Session gebunden. Neue Sessions erben die zuletzt gewählte
  // Vorgabe (localStorage), bestehende bekommen ihr echtes Modell beim Öffnen.
  const conv={key,sessionId:opts.sessionId||null,cwd:opts.cwd||null,
    model:opts.model!=null?opts.model:defaultModel(),busy:false,queue:[],ctrl:null,pane};
  conversations.set(key,conv);return conv;
}
function activeConv(){return conversations.get(activeKey);}
function convBySession(sid){if(!sid)return null;for(const c of conversations.values())if(c.sessionId===sid)return c;return null;}
function mountConv(conv){
  activeKey=conv.key;chat.innerHTML='';chat.appendChild(conv.pane);
  setFolder(conv.cwd||WORKSPACE_DIR);
  syncModelPicker(conv);   // Picker zeigt das Modell DIESER Session
  sidEl.textContent='▣ '+baseName(conv.cwd||WORKSPACE_DIR);sidEl.title=conv.cwd||'(unbekannt)';
  updateSendBtn();renderQueue();scroll();
}
marked.setOptions({breaks:true,highlight:(c,l)=>{try{return hljs.highlight(c,{language:hljs.getLanguage(l)?l:'plaintext'}).value}catch{return c}}});
const md=t=>DOMPurify.sanitize(marked.parse(t||''));

// Externe Links gehoeren in den Systembrowser, nicht in dieses Fenster.
// Die WebView (desktop.py) hat weder Adress- noch Zurueck-Leiste: ein Klick auf
// einen Chat-Link navigiert das GANZE Fenster dorthin, und es gibt keinen Weg
// zurueck zur App. Im Browser ist ein neuer Tab ebenfalls richtig, sonst ist
// der Chat weg. Bewusst ein globaler Handler statt target="_blank" beim
// Rendern: so sind auch alle nachtraeglich gestreamten Markdown-Links erfasst,
// ohne md() pro Token durch einen DOM-Umweg zu schicken.
addEventListener('click', function(e){
  if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey) return;
  var t = e.target;
  var a = (t && t.closest) ? t.closest('a[href]') : null;
  if (!a) return;
  var u; try { u = new URL(a.href, location.href); } catch (err) { return; }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return;  // mailto:, #anker, blob:
  if (u.origin === location.origin) return;                       // eigene Seite normal lassen
  e.preventDefault();
  var api = window.pywebview && window.pywebview.api;
  if (api && api.open_url) api.open_url(u.href);   // Fenster -> Systembrowser
  else window.open(u.href, '_blank', 'noopener');  // Browser -> neuer Tab
}, true);
const esc=s=>(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
const baseName=p=>(p||'').split('/').filter(Boolean).pop()||p||'?';
const fmtNum=n=>(n==null)?'?':(n>=1000?(n/1000).toFixed(n>=10000?0:1).replace(/\.0$/,'')+'k':String(n));
function fmtDur(ms){if(ms==null)return '?';const s=ms/1000;if(s<60)return s.toFixed(1)+' s';const m=Math.floor(s/60);return m+' m '+Math.round(s%60)+' s';}
function scroll(){chat.scrollTop=chat.scrollHeight;}
// Copy-Button auf jeden Code-Block (<pre>) — praktisch bei Code-Antworten.
function addCopyBtns(root){
  if(!root)return;
  root.querySelectorAll('pre').forEach(pre=>{
    if(pre.querySelector('.copy-btn'))return;
    const code=pre.querySelector('code');if(!code)return;
    const btn=document.createElement('button');btn.type='button';btn.className='copy-btn';btn.textContent='⧉ Kopieren';
    btn.onclick=e=>{e.stopPropagation();
      const txt=code.innerText;
      navigator.clipboard.writeText(txt).then(()=>{
        btn.textContent='✓ Kopiert';btn.classList.add('done');
        setTimeout(()=>{btn.textContent='⧉ Kopieren';btn.classList.remove('done');},1500);
      }).catch(()=>{btn.textContent='✗ Fehler';setTimeout(()=>btn.textContent='⧉ Kopieren',1500);});
    };
    pre.appendChild(btn);
  });
}
// Letzte (bzw. jede) eigene Nachricht bearbeiten & neu senden — spart Tokens,
// wenn man Cody gestoppt hat und den Auftrag nur korrigieren will.
function attachEdit(bubble,raw){
  bubble._raw=raw;
  const b=document.createElement('button');b.type='button';b.className='edit-btn';b.title='Bearbeiten & neu senden';b.textContent='✎';
  b.onclick=e=>{e.stopPropagation();startEdit(bubble);};
  bubble.appendChild(b);
}
function startEdit(bubble){
  const conv=activeConv();
  if(!conv||conv.busy)return;   // während Cody arbeitet: kein Bearbeiten
  const raw=bubble._raw||'';
  const prevHtml=bubble.innerHTML;
  const rebind=()=>{const eb=bubble.querySelector('.edit-btn');if(eb)eb.onclick=e=>{e.stopPropagation();startEdit(bubble);};};
  const restore=()=>{bubble.innerHTML=prevHtml;rebind();};
  bubble.innerHTML='';
  const ta=document.createElement('textarea');ta.className='editbox';ta.value=raw;
  const bar=document.createElement('div');bar.className='editbar';
  const cancel=document.createElement('button');cancel.className='eb-cancel';cancel.textContent='Abbrechen';
  const send=document.createElement('button');send.className='eb-send';send.textContent='↺ Neu senden';
  bar.append(cancel,send);bubble.append(ta,bar);
  const fit=()=>{ta.style.height='auto';ta.style.height=Math.min(ta.scrollHeight,300)+'px';};
  ta.addEventListener('input',fit);fit();ta.focus();ta.setSelectionRange(raw.length,raw.length);
  const doSend=()=>{
    const nt=ta.value.trim();if(!nt||conv.busy){restore();return;}
    const msgEl=bubble.closest('.msg');
    // Nur wenn dies die LETZTE eigene Nachricht ist, räumen wir die (gestoppte)
    // Antwort darunter weg — bei älteren Nachrichten bleibt alles stehen.
    let laterUser=false;
    if(msgEl){let n=msgEl.nextSibling;while(n){if(n.nodeType===1&&((n.matches&&n.matches('.msg.user'))||(n.querySelector&&n.querySelector('.msg.user')))){laterUser=true;break;}n=n.nextSibling;}}
    if(msgEl&&!laterUser){let n=msgEl.nextSibling;while(n){const x=n;n=n.nextSibling;x.remove();}msgEl.remove();}
    else restore();
    runSend(conv,nt,[],[]);
  };
  cancel.onclick=restore;
  send.onclick=doSend;
  ta.addEventListener('keydown',e=>{
    if(e.key==='Escape'){e.preventDefault();restore();}
    else if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();doSend();}
  });
}
function msgNode(role,html){
  const user=role==='user';
  const m=document.createElement('div');m.className='msg '+(user?'user':'bot');
  // Der Anfangsbuchstabe steht im Kreis, wenn kein Foto hinterlegt ist —
  // ein leerer Kreis sähe aus, als wäre ein Bild kaputt.
  const initial=user&&!HAS_AVATAR?esc(USER_NAME.slice(0,1).toUpperCase()):'';
  m.innerHTML=`<div class="avatar ${user?'av-user':'av-cody'}">${initial}</div>`
    +`<div class="msgcol"><div class="who">${esc((user?USER_NAME:ASSISTANT).toUpperCase())}`
    +(user?'':`<button type="button" class="say-btn" title="Vorlesen">🔊</button>`)+`</div>`
    +`<div class="bubble">${html}</div></div>`;
  return m;
}
function addMsg(role,html,conv,raw){
  const pane=(conv&&conv.pane)||(activeConv()&&activeConv().pane)||chat;
  const m=msgNode(role,html);
  pane.appendChild(m);
  const bubble=m.querySelector('.bubble');
  if(role==='user'&&raw!=null)attachEdit(bubble,raw);
  addCopyBtns(bubble);
  if(!conv||conv.key===activeKey)scroll();return bubble;
}
function addMsgTo(container,role,html){const m=msgNode(role,html);container.appendChild(m);const bubble=m.querySelector('.bubble');addCopyBtns(bubble);return bubble;}
