// CONSTRUCT — Kalender
// ---------- Kalender ----------
// Termine leben in events.json (Backend). Cody schreibt per cal.py rein, die UI
// per /api/events. Der große Monats-Grid landet im Hauptbereich (#chat), die
// "Anstehend"-Liste in der Sidebar — wie bei der Skills-Ansicht.
const DE_MONTHS=I18N.lang==='en'
  ?['January','February','March','April','May','June','July','August','September','October','November','December']
  :['Januar','Februar','März','April','Mai','Juni','Juli','August','September','Oktober','November','Dezember'];
const DE_DOW=I18N.lang==='en'?['Mon','Tue','Wed','Thu','Fri','Sat','Sun']:['Mo','Di','Mi','Do','Fr','Sa','So'];
let calYear, calMonth, calSelDay=null, calEvents=[];
// Tagebuch: woran an welchem Tag gearbeitet wurde (/api/activity, aus den
// Transkripten abgeleitet — nichts davon steht in events.json).
let calAct={}, calActRange='';
const pad2=n=>String(n).padStart(2,'0');
const ymd=(y,m,d)=>`${y}-${pad2(m+1)}-${pad2(d)}`;          // m = 0-basiert
const todayYMD=()=>{const n=new Date();return ymd(n.getFullYear(),n.getMonth(),n.getDate());};
async function fetchEvents(){try{calEvents=await(await fetch('/api/events')).json();}catch{calEvents=[];}}
// Findet e am Tag ds statt? Jährliche (Geburtstage) matchen über Monat-Tag, Jahr egal.
function occursOn(e,ds){return e.repeat==='yearly'?(e.date.slice(5)===ds.slice(5)):(e.date===ds);}
function eventsOn(ds){return calEvents.filter(e=>occursOn(e,ds)).sort((a,b)=>(a.time||'~').localeCompare(b.time||'~'));}
// Nächstes Vorkommen ab fromStr (für die "Anstehend"-Liste): jährliche aufs nächste Jahr rollen.
function occDate(e,fromStr){
  if(e.repeat!=='yearly')return e.date;
  const md=e.date.slice(5), y=+fromStr.slice(0,4);
  let cand=y+'-'+md;
  return cand<fromStr?((y+1)+'-'+md):cand;
}

async function loadKal(){
  if(calYear===undefined){const n=new Date();calYear=n.getFullYear();calMonth=n.getMonth();}
  calActRange='';   // beim Öffnen frisch holen: heute kann Neues dazugekommen sein
  await fetchEvents();
  renderCalMain();
  renderCalSide();
}

// Sichtbarer Bereich des Grids (6 Wochen ab dem Montag vor dem 1.).
function calGridStart(){const f=new Date(calYear,calMonth,1);return new Date(calYear,calMonth,1-(f.getDay()+6)%7);}
async function fetchActivity(){
  const s=calGridStart(), e=new Date(s);e.setDate(s.getDate()+41);
  const a=ymd(s.getFullYear(),s.getMonth(),s.getDate()), b=ymd(e.getFullYear(),e.getMonth(),e.getDate());
  if(calActRange===a+'|'+b)return false;
  const key=calActRange=a+'|'+b;
  let d={};try{d=await(await fetch(`/api/activity?start=${a}&end=${b}`)).json();}catch{}
  if(key!==calActRange)return false;   // inzwischen weitergeblättert
  calAct=d;return true;
}
function renderCalMain(){
  // Tagebuch nachladen und dann EINMAL neu zeichnen — das Grid steht sofort,
  // die Projekt-Chips kommen einen Wimpernschlag später dazu.
  fetchActivity().then(changed=>{if(changed&&document.getElementById('calwrap'))renderCalMain();});
  const wrap=document.createElement('div');wrap.id='calwrap';
  const top=document.createElement('div');top.className='cal-top';
  top.innerHTML=`<button class="cal-nav" id="calPrev" title="Vorheriger Monat">‹</button>`
    +`<h2>${DE_MONTHS[calMonth]} ${calYear}</h2>`
    +`<button class="cal-tbtn" id="calToday">HEUTE</button>`
    +`<button class="cal-nav" id="calNext" title="Nächster Monat">›</button>`;
  wrap.appendChild(top);
  const dow=document.createElement('div');dow.className='cal-dow';
  dow.innerHTML=DE_DOW.map((d,i)=>`<span class="${i>=5?'we':''}">${d}</span>`).join('');
  wrap.appendChild(dow);
  const grid=document.createElement('div');grid.className='cal-grid';
  const first=new Date(calYear,calMonth,1);
  const startDow=(first.getDay()+6)%7;                       // Montag = 0
  const start=new Date(calYear,calMonth,1-startDow);
  const tStr=todayYMD();
  for(let i=0;i<42;i++){
    const dt=new Date(start);dt.setDate(start.getDate()+i);
    const ds=ymd(dt.getFullYear(),dt.getMonth(),dt.getDate());
    const cell=document.createElement('div');
    cell.className='cal-cell'+(dt.getMonth()!==calMonth?' other':'')+(ds===tStr?' today':'')+(ds===calSelDay?' sel':'');
    const evs=eventsOn(ds);
    let chips='';
    evs.slice(0,3).forEach(e=>{chips+=`<div class="cal-chip${e.time?'':' allday'}">${e.prompt?'🤖 ':''}${e.time?esc(e.time)+' ':''}${esc(e.title)}</div>`;});
    if(evs.length>3)chips+=`<div class="cal-more">+${evs.length-3} mehr</div>`;
    const act=calAct[ds]||[];
    if(act.length)chips+=`<div class="cal-act" title="${esc(act.map(p=>baseName(p.cwd)).join(', '))}">`
      +`🗂 ${esc(baseName(act[0].cwd))}${act.length>1?` +${act.length-1}`:''}</div>`;
    cell.innerHTML=`<span class="cal-dnum">${dt.getDate()}</span>${chips}`;
    cell.onclick=()=>{calSelDay=ds;renderCalMain();};
    grid.appendChild(cell);
  }
  wrap.appendChild(grid);
  const dp=document.createElement('div');dp.id='calDayPanel';wrap.appendChild(dp);
  chat.innerHTML='';chat.appendChild(wrap);
  document.getElementById('calPrev').onclick=()=>{if(--calMonth<0){calMonth=11;calYear--;}renderCalMain();};
  document.getElementById('calNext').onclick=()=>{if(++calMonth>11){calMonth=0;calYear++;}renderCalMain();};
  document.getElementById('calToday').onclick=()=>{const n=new Date();calYear=n.getFullYear();calMonth=n.getMonth();calSelDay=todayYMD();renderCalMain();};
  if(calSelDay)renderDayPanel(calSelDay);
}

function renderDayPanel(ds){
  const host=document.getElementById('calDayPanel');if(!host)return;
  const [y,m,d]=ds.split('-').map(Number);
  const head=new Date(y,m-1,d).toLocaleDateString(I18N.locale,{weekday:'long',day:'numeric',month:'long',year:'numeric'});
  const evs=eventsOn(ds);
  const evHtml=evs.length?evs.map(e=>`<div class="cal-ev">`
      +`<span class="et">${e.time?esc(e.time):(e.repeat==='yearly'?'🔁':'⬤')}</span>`
      +`<span class="etitle">${e.prompt?'🤖 ':''}${esc(e.title)}${e.notes?` <span class="enote">— ${esc(e.notes)}</span>`:''}`
      +`${e.prompt?` <span class="enote" title="läuft zur Termin-Zeit automatisch, Ergebnis per Telegram">— Aufgabe: ${esc(e.prompt.slice(0,120))}</span>`:''}</span>`
      +`<span class="edel" data-id="${esc(e.id)}" title="löschen">✕</span></div>`).join('')
    :'<div class="vhint" style="padding:2px 0 6px">Keine Termine an diesem Tag.</div>';
  const act=calAct[ds]||[];
  const actHtml=act.length?`<div class="cal-acth">🗂 WORAN GEARBEITET</div>`+act.map((p,pi)=>`<div class="cal-proj">`
      +`<div class="cp-h" title="${esc(p.cwd)}">📂 ${esc(baseName(p.cwd))}<span class="cp-n">${p.n} ${p.n===1?'Eingabe':'Eingaben'}</span></div>`
      +p.sessions.map((s,si)=>`<div class="cp-s" data-p="${pi}" data-s="${si}" title="Session öffnen">↳ ${esc(s.title)}</div>`).join('')
      +`</div>`).join(''):'';
  host.innerHTML=`<div class="cal-day"><h3>📅 ${esc(head)}</h3>${evHtml}${actHtml}`
    +`<div class="cal-add">`
    +`<input class="ci-time" id="caTime" placeholder="HH:MM" maxlength="5" inputmode="numeric">`
    +`<input class="ci-title" id="caTitle" placeholder="Termin eintragen (z.B. Zahnarzt)">`
    +`<label class="ci-rep" title="jedes Jahr wiederholen (z.B. Geburtstag)"><input type="checkbox" id="caRep"> 🔁 jährlich</label>`
    +`<button id="caAdd">＋ Eintragen</button></div>`
    +`<div class="cal-add"><input class="ci-title" id="caPrompt" `
    +`placeholder="🤖 ${ASSISTANT}-Aufgabe zur Termin-Zeit (optional) — Ergebnis kommt per Telegram">`
    +`</div></div>`;
  host.querySelectorAll('.edel').forEach(b=>b.onclick=()=>delEvent(b.dataset.id));
  host.querySelectorAll('.cp-s').forEach(b=>b.onclick=()=>openSession(act[+b.dataset.p].sessions[+b.dataset.s]));
  const add=()=>{
    const time=document.getElementById('caTime').value.trim();
    const title=document.getElementById('caTitle').value.trim();
    const pel=document.getElementById('caPrompt');const prompt=pel?pel.value.trim():'';
    if(!title){document.getElementById('caTitle').focus();return;}
    if(prompt&&!time){document.getElementById('caTime').focus();return;}   // Aufgabe braucht Uhrzeit
    addEvent({date:ds,time,title,prompt,repeat:document.getElementById('caRep').checked?'yearly':''});
  };
  document.getElementById('caAdd').onclick=add;
  document.getElementById('caTitle').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();add();}});
}

async function addEvent(ev){
  try{await fetch('/api/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(ev)});}catch{}
  await fetchEvents();renderCalMain();renderCalSide();
}
async function delEvent(id){
  try{await fetch('/api/events/'+encodeURIComponent(id),{method:'DELETE'});}catch{}
  await fetchEvents();renderCalMain();renderCalSide();
}

function renderCalSide(){
  const el=document.getElementById('kal');if(!el)return;
  const tStr=todayYMD();
  // jedes Event auf sein nächstes Vorkommen abbilden, dann chronologisch sortieren
  const up=calEvents.map(e=>({e,d:occDate(e,tStr)})).filter(x=>x.d>=tStr)
    .sort((a,b)=>(a.d+(a.e.time||'~')).localeCompare(b.d+(b.e.time||'~'))).slice(0,15);
  let html='<button class="kal-add" id="kalAdd">＋ TERMIN</button><div class="kal-uh">ANSTEHEND</div>';
  if(!up.length)html+='<div class="vhint">Keine anstehenden Termine.</div>';
  else up.forEach(({e,d})=>{
    const [yy,mm,dd2]=d.split('-').map(Number);
    const dd=new Date(yy,mm-1,dd2).toLocaleDateString(I18N.locale,{weekday:'short',day:'2-digit',month:'2-digit'});
    html+=`<div class="kal-up${d===tStr?' is-today':''}" data-d="${d}">`
      +`<span class="ku-t">${e.repeat==='yearly'?'🔁 ':''}${e.prompt?'🤖 ':''}${e.time?esc(e.time)+' · ':''}${esc(e.title)}</span>`
      +`<span class="ku-d">${d===tStr?'heute':dd}</span></div>`;
  });
  el.innerHTML=html;
  document.getElementById('kalAdd').onclick=()=>{const n=new Date();calYear=n.getFullYear();calMonth=n.getMonth();
    calSelDay=todayYMD();renderCalMain();setTimeout(()=>{const t=document.getElementById('caTitle');if(t)t.focus();},30);};
  el.querySelectorAll('.kal-up').forEach(it=>it.onclick=()=>{const ds=it.dataset.d;
    const [yy,mm]=ds.split('-').map(Number);calYear=yy;calMonth=mm-1;calSelDay=ds;renderCalMain();});
}
async function loadMcp(){
  const el=document.getElementById('mcp');el.innerHTML='<div class="vhint">⟲ prüfe Konnektoren…</div>';
  let d={};try{d=await(await fetch('/api/mcp')).json();}catch(e){}
  el.innerHTML='';
  const s=d.servers||[];
  if(!s.length){el.innerHTML='<div class="vhint">keine MCP-Server konfiguriert'+(d.error?(' ('+esc(d.error)+')'):'')+'</div>';return;}
  s.forEach(m=>{
    const icon=m.ok?'🟢':(m.needs_auth?'🔑':'🔴');
    const div=document.createElement('div');div.className='sess';
    div.innerHTML=`<span class="t">${icon} ${esc(m.name)}</span><span class="d">${esc(m.status)}</span>`;
    div.title=m.url;el.appendChild(div);
  });
  const h=document.createElement('div');h.className='vhint';h.style.lineHeight='1.6';h.style.marginTop='10px';
  h.innerHTML='🟢 aktiv · 🔑 braucht Login · 🔴 Problem<br><br>Freischalten: im Terminal <code>claudec</code> → <code>/mcp</code>, oder auf <b>claude.ai → Connectors</b>.';
  el.appendChild(h);
}

