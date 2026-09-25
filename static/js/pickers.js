// CONSTRUCT — Ordner- und Modus-Auswahl
// ---------- Picker: Ordner + Mode ----------
const MODES=[
  {v:'bypassPermissions',l:'⚡ Auto',d:'volle Rechte — alles läuft automatisch'},
  {v:'plan',l:'📋 Plan',d:'nur lesen / planen, ändert nichts'},
  {v:'default',l:'🛡 Standard',d:'fragt nach (im Web eingeschränkt)'},
];
let currentMode=localStorage.getItem('mxmode')||'bypassPermissions';
// Modell-Auswahl: Claude (voll integriert, mit Tools) + externe Anbieter
// (reiner Chat, Einrichtung über 🧠 → ⚙ KI-Anbieter). Externe Werte heißen
// "anbieter:modell", z.B. "openai:gpt-4o" oder "ollama:gemma3:12b".
// Volle Modell-IDs statt Aliase ('sonnet', 'fable'): ein Alias zeigt immer auf
// das jeweils neueste Modell seiner Reihe, und man sieht ihm nicht an, welches
// das gerade IST. Hier steht, was wirklich läuft.
//
// Nachmessen, wenn ein neues Modell erscheint — raten hilft hier nicht:
//   claude -p "ok" --model <name> --output-format json | jq .modelUsage
// Der Schlüssel darin ist die tatsächlich benutzte ID. Gemessen am 04.09.2026
// mit Claude Code 2.1.280: fable→claude-fable-5-1, opus→claude-opus-5-5,
// sonnet→claude-sonnet-5, haiku→claude-haiku-4-5-20251001.
// Längere IDs zuerst: die Rückführung unten geht über den Präfix, und
// "claude-opus-5-5" fängt nun einmal mit "claude-opus-5" an.
const CLAUDE_MODELS=[
  {v:'',l:'Standard',d:'Konto-Standard von Claude Code'},
  {v:'claude-opus-5-5',l:'Opus 5.5',d:'neuestes Opus — stark für Coding und komplexe Aufgaben'},
  {v:'claude-fable-5-1',l:'Fable 5.1',d:'stärkstes Modell — für die härtesten und längsten Aufgaben'},
  {v:'claude-opus-5',l:'Opus 5',d:'Vorgänger von Opus 5.5'},
  {v:'claude-sonnet-5',l:'Sonnet 5',d:'schnell, schont das Limit'},
  {v:'claude-haiku-4-5',l:'Haiku 4.5',d:'am schnellsten — kleine Aufgaben'},
];
// Vorgabe für alle neuen Gespräche.
const DEFAULT_MODEL='claude-opus-5-5';
// Alte Auswahl aus dem localStorage und Rückmeldungen aus Transkripten kommen
// als Alias oder mit Zusätzen an (`claude-haiku-4-5-20251001`, `…[1m]`). Ohne
// diese Zuordnung fiele der Picker bei jeder solchen Angabe stumm auf
// "Standard" zurück — und zeigte damit genau das Falsche an.
const MODEL_ALIAS={fable:'claude-fable-5-1',opus:'claude-opus-5-5',
                   sonnet:'claude-sonnet-5',haiku:'claude-haiku-4-5'};
const PROV_ICON={openai:'🟢',gemini:'✦',deepseek:'🐋',ollama:'🦙',bonsai:'🌱'};
let llmProviders=[];   // /api/llm/providers — nur konfigurierte liefern Modelle
async function loadProviders(force){
  try{llmProviders=await(await fetch('/api/llm/providers'+(force?'?refresh=1':''))).json();}
  catch{llmProviders=[];}
  if(!Array.isArray(llmProviders))llmProviders=[];
  // Ohne installiertes Claude Code wäre der leere Standardwert eine Sackgasse:
  // die erste Nachricht liefe in "claude nicht gefunden". Sobald ein externer
  // Anbieter eingerichtet ist, also von selbst dorthin schalten.
  // (Auch die Vorgabe Opus 5.5 ist ohne CLI eine Sackgasse — daher nicht nur
  // auf den leeren Wert prüfen, sondern auf "kein externes Modell gewählt".)
  if(!HAS_CLAUDE&&!(currentModel||'').includes(':')){const e=extModels()[0];if(e)setModel(e.v);}
  syncModelPicker(activeConv());   // Anzeige ggf. nachziehen (Label statt Roh-Wert)
}
function extModels(){const out=[];llmProviders.forEach(p=>{if(!p.configured)return;
  (p.models||[]).forEach(m=>{
    // tools: true = sicher werkzeugfähig, null = unbekannt (nicht in der
    // Datenbank). Unbekannte bekommen ein Fragezeichen statt zu verschwinden.
    const cap=(p.tools||{})[m];
    out.push({v:p.id+':'+m,l:m,d:p.label,prov:p.id,cap:cap});
  });});return out;}
// Oben in der Statuszeile: womit zuletzt WIRKLICH geantwortet wurde. Nicht die
// Auswahl — die kann "Standard" sein oder ein Alias, der sich mit dem nächsten
// Modell still verschiebt. Leer, solange in dieser Session nichts lief; das ist
// ehrlicher als eine Angabe, die niemand geprüft hat.
function zeigeModell(id){
  const el=document.getElementById('curmodel');if(!el)return;
  const m=id?modelInfo(id):null;
  el.textContent=id?('· '+((m&&m.l)||id.replace(/^claude-/,''))):'';
}
function modelInfo(v){
  const c=CLAUDE_MODELS.find(x=>x.v===v);if(c)return c;
  const e=extModels().find(x=>x.v===v);if(e)return e;
  // Claude-Modell, aber in anderer Schreibweise: Alias, Datumsstempel oder
  // Kontext-Zusatz. Auf den Listeneintrag zurückführen statt aufzugeben.
  if(v&&!v.includes(':')){
    const roh=v.replace(/\[.*\]$/,'');
    // Längster passender Präfix gewinnt, sonst würde "claude-opus-5-5[1m]"
    // bei "claude-opus-5" hängenbleiben.
    const treffer=MODEL_ALIAS[roh]||CLAUDE_MODELS.slice(1).filter(x=>roh.startsWith(x.v))
                                     .sort((a,b)=>b.v.length-a.v.length)[0]?.v;
    if(treffer){const m=CLAUDE_MODELS.find(x=>x.v===treffer);if(m)return m;}
    // Ein Claude-Modell, das nicht (mehr) zur Auswahl steht — etwa eine alte
    // Session auf claude-opus-4-8. Mit der rohen ID anzeigen: "Standard" wäre
    // hier schlicht gelogen.
    if(roh.startsWith('claude-'))return {v,l:roh.replace(/^claude-/,''),d:'nicht mehr in der Auswahl'};
  }
  // unbekannt, aber extern (Anbieterliste evtl. noch nicht geladen) -> trotzdem anzeigen
  if(v&&v.includes(':'))return {v,l:v.split(':').slice(1).join(':'),d:v.split(':')[0],prov:v.split(':')[0]};
  return null;
}
// Noch nie etwas gewählt -> Opus 5.5. Ein bewusst gewähltes "Standard" ist ''
// und muss "Standard" bleiben — deshalb auf null prüfen statt auf falsy.
function storedModel(){const v=localStorage.getItem('mxmodel');return v===null?DEFAULT_MODEL:v;}
let currentModel=storedModel();
const fbar=document.getElementById('folderbar'),flist=document.getElementById('folderlist');
const mbar=document.getElementById('modebar'),mlist=document.getElementById('modelist');
const lbar=document.getElementById('llmbar'),llist=document.getElementById('llmlist');
async function loadFolders(){try{foldersCache=await (await fetch('/api/folders')).json();}catch{foldersCache=[];}}
function setFolder(path){currentCwd=path||null;const n=document.getElementById('fbname');n.textContent=baseName(path);n.title=path||'';}
function setMode(v){let m=MODES.find(x=>x.v===v);if(!m){m=MODES[0];v=m.v;}currentMode=v;localStorage.setItem('mxmode',v);
  document.getElementById('mbicon').textContent=m.l.split(' ')[0];document.getElementById('mbname').textContent=m.l.split(' ').slice(1).join(' ');}
function defaultModel(){return storedModel();}
// Nutzer wählt ein Modell: gilt für die AKTIVE Session + wird Vorgabe für neue.
function setModel(v){let m=modelInfo(v);if(!m){m=CLAUDE_MODELS[0];v='';}currentModel=v;
  const c=activeConv();if(c)c.model=v;
  localStorage.setItem('mxmodel',v);
  document.getElementById('llmname').textContent=(m.prov?(PROV_ICON[m.prov]||'🌐')+' ':'')+m.l;}
// Picker nur ANZEIGEN passend zur Session (ohne Vorgabe zu überschreiben).
function syncModelPicker(conv){const v=(conv&&conv.model!=null)?conv.model:'';
  const m=modelInfo(v)||CLAUDE_MODELS[0];currentModel=m.v;
  document.getElementById('llmname').textContent=(m.prov?(PROV_ICON[m.prov]||'🌐')+' ':'')+m.l;}
function closeLists(){flist.classList.remove('show');mlist.classList.remove('show');llist.classList.remove('show');}
fbar.onclick=e=>{e.stopPropagation();const open=flist.classList.contains('show');closeLists();if(open)return;
  flist.innerHTML='';foldersCache.forEach(p=>{const d=document.createElement('div');d.className='fl-item'+(p===currentCwd?' sel':'');
    d.textContent='📂 '+baseName(p);d.title=p;d.onclick=()=>{setFolder(p);closeLists();};flist.appendChild(d);});flist.classList.add('show');};
mbar.onclick=e=>{e.stopPropagation();const open=mlist.classList.contains('show');closeLists();if(open)return;
  mlist.innerHTML='';MODES.forEach(m=>{const d=document.createElement('div');d.className='fl-item'+(m.v===currentMode?' sel':'');
    d.innerHTML=`${m.l} <span style="opacity:.55">— ${m.d}</span>`;d.onclick=()=>{setMode(m.v);closeLists();};mlist.appendChild(d);});mlist.classList.add('show');};
lbar.onclick=e=>{e.stopPropagation();const open=llist.classList.contains('show');closeLists();if(open)return;
  llist.innerHTML='';
  const head=t=>{const h=document.createElement('div');h.className='fl-head';h.textContent=t;llist.appendChild(h);};
  const item=(m,icon)=>{const d=document.createElement('div');d.className='fl-item'+(m.v===currentModel?' sel':'');
    d.innerHTML=`${icon} ${esc(m.l)} <span style="opacity:.55">— ${esc(m.d)}</span>`;
    d.onclick=()=>{setModel(m.v);closeLists();};llist.appendChild(d);};
  head('CLAUDE · VOLLER ZUGRIFF (TOOLS, DATEIEN)'+(HAS_CLAUDE?'':' — NICHT INSTALLIERT'));
  CLAUDE_MODELS.forEach(m=>item(m,'🧠'));
  llmProviders.filter(p=>p.configured).forEach(p=>{
    head(`${PROV_ICON[p.id]||'🌐'} ${p.label.toUpperCase()} · ÜBER HERMES`);
    const ms=p.models||[];
    if(!ms.length){const d=document.createElement('div');d.className='fl-item';d.style.opacity=.5;
      d.textContent=p.error?('⚠ '+p.error):'(keine Modelle gefunden)';llist.appendChild(d);}
    ms.forEach(mid=>{
      const cap=(p.tools||{})[mid];
      item({v:p.id+':'+mid, l:mid+(cap===true?' ⚡':cap==null?' ⚡?':''),
            d:p.label+(cap===true?' · mit Werkzeugen':cap==null?' · Werkzeuge unbestätigt':'')},
           PROV_ICON[p.id]||'🌐');
    });
  });
  head('');
  const cfg=document.createElement('div');cfg.className='fl-item';
  cfg.innerHTML='⚙ <b>KI-Anbieter einrichten…</b> <span style="opacity:.55">— ChatGPT, Gemini, DeepSeek, Ollama</span>';
  cfg.onclick=()=>{closeLists();openLlmCfg();};llist.appendChild(cfg);
  llist.classList.add('show');};
document.addEventListener('click',closeLists);

