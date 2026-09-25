// CONSTRUCT — Menü, Eingabe, Werkzeug-Updates, Start
// ---------- Menü ----------
function setView(v){
  // Abgeschaltete Kacheln sind auch per Tastatur/Slash-Befehl nicht erreichbar.
  if(SETTINGS.tiles[v]===false)return;
  document.querySelectorAll('.mi').forEach(b=>b.classList.toggle('active',b.dataset.v===v));
  document.querySelectorAll('.view').forEach(el=>el.style.display='none');
  document.getElementById('view-'+v).style.display='';
  document.body.classList.toggle('mailmode',v==='mail');   // Scanlines nur außerhalb der Mails
  if(v==='skills')loadSkills();if(v==='kalender')loadKal();if(v==='mcp')loadMcp();if(v==='mail')loadMailView();
  if(v==='einstellungen')renderSettings();
  // Zurueck zu den Chats: die Unterhaltung wieder einhaengen -- Mail, Kalender
  // ueberschreiben #chat, sonst bliebe deren Ansicht stehen.
  if(v==='sessions'){const c=activeConv();if(c)mountConv(c);}
}
document.querySelectorAll('.mi').forEach(b=>b.onclick=()=>setView(b.dataset.v));
document.getElementById('burger').onclick=()=>document.getElementById('side').classList.toggle('open');

// ---------- Eingabe ----------
function autosize(){inp.style.height='auto';inp.style.height=Math.min(inp.scrollHeight,180)+'px';}
// Nicht direkt an 'input' hängen: die Folge "height='auto' schreiben ->
// scrollHeight lesen" erzwingt ein sofortiges Neu-Layout der GANZEN Seite, und
// das bei jedem einzelnen Tastendruck. Zusammen mit Vollbild-Canvas und
// Scanlines-Overlay ist das der spürbare Tipp-Lag. Pro Frame einmal reicht;
// die expliziten autosize()-Aufrufe (nach dem Absenden) bleiben synchron.
let _asPending = false;
inp.addEventListener('input',()=>{
  if (_asPending) return;
  _asPending = true;
  requestAnimationFrame(()=>{ _asPending = false; autosize(); });
});
inp.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}});
document.getElementById('send').onclick=send;
document.getElementById('stop').onclick=()=>{
  const c=activeConv();
  if(c&&c.runId){
    c.stopReq=true;c.queue.length=0;renderQueue();
    fetch('/api/stop/'+encodeURIComponent(c.runId),{method:'POST'}).catch(()=>{});
    if(c.streamCtrl)c.streamCtrl.abort('user');
  }
};

// ---------- Werkzeuge aktuell halten ----------
// Der Server sucht beim Start selbst nach neuen Fassungen von Claude Code und
// Hermes (updates.py). Hier wird das nur sichtbar gemacht: eine Karte unten
// rechts, die sich von allein wieder verabschiedet, wenn nichts war.
const UPD_NAMES={claude:'Claude Code',hermes:'Hermes'};
const UPD_ICON={run:'<span class="upd-spin">⟳</span>',ok:'✓',new:'✓',error:'⚠',skip:'–',idle:'·'};
let updTimer=null,updHidden=false,updLive=false,updFadeTimer=null;
// Kurz nach dem Laden schneller nachfragen: der Start-Lauf braucht einen
// Moment, bis er ueberhaupt als "laeuft" in Erscheinung tritt.
const updEager=Date.now()+25000;

function updStepText(k,s){
  if(s.state==='new')return s.msg||'aktualisiert';
  if(s.state==='ok')return 'aktuell'+(s.to?' · '+s.to:'');
  if(s.state==='error')return s.msg||'Fehler';
  if(s.state==='skip')return s.msg||'übersprungen';
  if(s.state==='run')return 'prüfe …';
  return '';
}

function updRender(st){
  const card=document.getElementById('updcard');
  if(st.running)updLive=true;
  // Nur melden, was gerade passiert — eine laengst abgeschlossene Pruefung
  // soll nicht bei jedem Neuladen der Seite wieder auftauchen.
  if(updHidden||!(st.running||(updLive&&st.done))){card.classList.remove('show');return;}
  const steps=st.steps||{};
  const shown=Object.keys(UPD_NAMES).filter(k=>steps[k]&&steps[k].state!=='idle');
  document.getElementById('updRows').innerHTML=shown.map(k=>{
    const s=steps[k];
    return `<div class="upd-row ${s.state}"><span>${UPD_ICON[s.state]||'·'}</span>
      <span class="n">${UPD_NAMES[k]}</span><span class="v">${esc(updStepText(k,s))}</span></div>`;
  }).join('')||'<div class="upd-row"><span class="n">suche …</span></div>';

  const bad=shown.some(k=>steps[k].state==='error');
  document.getElementById('updIcon').outerHTML=
    `<span id="updIcon"${st.running?' class="upd-spin"':''}>${st.running?'⟳':(bad?'⚠':'✓')}</span>`;
  document.getElementById('updTitle').textContent=
    st.running?'WERKZEUGE PRÜFEN':(bad?'UPDATE FEHLGESCHLAGEN':(st.changed?'AKTUALISIERT':'ALLES AKTUELL'));
  const last=(st.log||[]).slice(-1)[0]||'';
  document.getElementById('updline').textContent=
    st.done&&st.changed?'wirkt ab dem nächsten Chat':last;
  card.classList.add('show');

  // Gute Nachricht = kurze Nachricht. Neuerungen und Fehler bleiben stehen,
  // damit sie nicht ungesehen vorbeiziehen.
  clearTimeout(updFadeTimer);
  if(st.done&&!st.changed&&!bad)
    updFadeTimer=setTimeout(()=>card.classList.remove('show'),3500);
}

async function updPoll(){
  let st;
  try{st=await(await fetch('/api/updates')).json();}catch{updSchedule(8000);return;}
  updRender(st);
  updSchedule(st.running?1200:(Date.now()<updEager?1500:60000));
}
function updSchedule(ms){clearTimeout(updTimer);updTimer=setTimeout(updPoll,ms);}
document.getElementById('updClose').onclick=()=>{
  updHidden=true;document.getElementById('updcard').classList.remove('show');};

// ---------- Init ----------
fetch('/api/version').then(r=>r.json()).then(j=>{document.getElementById('build').textContent='build '+j.version;}).catch(()=>{document.getElementById('build').textContent='build ALT/unbekannt';});
setMode(currentMode);setModel(currentModel);applyClaudeState();
applyAvatars();      // eigene Bilder, falls hinterlegt
// Seitenleiste in der Breite ziehen. Pointer-Capture statt mousemove am
// document: so geht der Zug auch nicht verloren, wenn die Maus über den Chat
// oder aus dem Fenster rutscht.
(function(){
  const g=document.getElementById('sideGrip'), side=document.getElementById('side'), r=document.documentElement;
  const setW=w=>{w=Math.round(Math.max(220,Math.min(w,Math.min(900,innerWidth*.6))));
    r.style.setProperty('--side-w',w+'px');return w;};
  g.addEventListener('pointerdown',e=>{
    if(e.button!==0)return;e.preventDefault();
    g.setPointerCapture(e.pointerId);g.classList.add('drag');document.body.classList.add('side-drag');
    const x0=e.clientX, w0=side.getBoundingClientRect().width;
    const move=ev=>setW(w0+ev.clientX-x0);
    const up=ev=>{g.removeEventListener('pointermove',move);g.removeEventListener('pointerup',up);g.removeEventListener('pointercancel',up);
      g.classList.remove('drag');document.body.classList.remove('side-drag');
      try{localStorage.setItem('sideW',String(Math.round(side.getBoundingClientRect().width)));}catch{}};
    g.addEventListener('pointermove',move);g.addEventListener('pointerup',up);g.addEventListener('pointercancel',up);
  });
  g.addEventListener('dblclick',()=>{r.style.removeProperty('--side-w');try{localStorage.removeItem('sideW');}catch{}});
})();
applyTheme();        // Farbwelt (im <head> schon gesetzt, hier der Regen)
applyBackground();   // Hintergrund aus den gespeicherten Einstellungen
// Kein fest verdrahteter Pfad: /api/folders liefert
// an erster Stelle den echten Arbeitsordner des Servers (WORKSPACE) — unter
// Windows und nativ auf dem Desktop ist das ein ganz anderer Pfad, und die
// Anzeige log bisher, weil der Server still auf seinen Standard zurückfiel.
loadFolders().then(()=>setFolder(foldersCache[0]||''));
loadProviders();   // externe Anbieter/Modelle für den 🧠-Picker
newSession();loadSessions();loadHud();
updPoll();         // zeigt den Update-Lauf, den der Server beim Start angestoßen hat
