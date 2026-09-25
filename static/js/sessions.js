// CONSTRUCT — Sitzungsliste, Live-Tail
// ---------- Sessions ----------
let showArchived=false, showAgents=false, runningRuns={}, sessCache=[], sessQuery='';
async function loadSessions(){
  try{
    sessCache=await (await fetch('/api/sessions')).json();
    try{const rs=await (await fetch('/api/runs')).json();runningRuns={};rs.forEach(r=>{if(r.session_id)runningRuns[r.session_id]=r.run_id;});}catch{}
    renderSessions();
  }catch(e){}
}
function renderSessions(){
    const list=sessCache;
    const el=document.getElementById('sessions');el.innerHTML='';
    // Archiv-Umschalter
    const archCount=list.filter(s=>s.archived).length;
    const tg=document.createElement('div');tg.className='archtoggle'+(showArchived?' on':'');
    tg.innerHTML=`🗄 Archiv (${archCount}) · <span>${showArchived?'ausblenden':'anzeigen'}</span>`;
    tg.onclick=()=>{showArchived=!showArchived;renderSessions();};
    el.appendChild(tg);
    // Sitzungen der Firma: jeder Agentenzug in FACTORIA legt eine eigene an,
    // und die erschlagen die eigenen Gespräche rein zahlenmäßig. Standardmäßig
    // aus, aber nachsehen können muss man — der Schalter erscheint nur, wenn
    // es überhaupt welche gibt.
    const agentCount=list.filter(s=>s.agent).length;
    if(agentCount){
      const at=document.createElement('div');at.className='archtoggle'+(showAgents?' on':'');
      at.innerHTML=`🏢 Firma (${agentCount}) · <span>${showAgents?'ausblenden':'anzeigen'}</span>`;
      at.onclick=()=>{showAgents=!showAgents;renderSessions();};
      el.appendChild(at);
    }
    let visible=list.filter(s=>showArchived?true:!s.archived);
    if(!showAgents)visible=visible.filter(s=>!s.agent);
    if(sessQuery)visible=visible.filter(s=>((s.title||'')+' '+(s.cwd||'')).toLowerCase().includes(sessQuery));
    const groups={};visible.forEach(s=>{const k=s.cwd||'(unbekannt)';(groups[k]=groups[k]||[]).push(s);});
    const folders=Object.keys(groups).sort((a,b)=>groups[b][0].mtime-groups[a][0].mtime);
    if(!folders.length){const e=document.createElement('div');e.className='vhint';
      e.textContent=sessQuery?'Nichts gefunden.':(showArchived?'Keine Sessions.':'Keine aktiven Sessions.');el.appendChild(e);return;}
    folders.forEach(folder=>{
      const items=groups[folder],open=sessQuery?true:openFolders[folder]!==false;   // bei Suche alles aufklappen
      const hdr=document.createElement('div');hdr.className='folder';
      hdr.innerHTML=`<span class="fa">${open?'▾':'▸'}</span><span class="fn" title="${esc(folder)}">▣ ${esc(baseName(folder))}</span><span class="fc">${items.length}</span>`;
      hdr.onclick=()=>{openFolders[folder]=!open;renderSessions();};el.appendChild(hdr);
      if(open)items.forEach(s=>{
        const ac=activeConv();const rc=convBySession(s.id);const running=!!(rc&&rc.busy)||!!runningRuns[s.id];
        const d=document.createElement('div');d.className='sess'+((ac&&s.id===ac.sessionId)?' active':'')+(running?' running':'')+(s.archived?' archived':'');
        const dt=new Date(s.mtime*1000).toLocaleString(I18N.locale,{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})
          +(s.provider?' · '+(PROV_ICON[s.provider]||'🌐')+' '+esc(s.model||s.provider):'');
        d.innerHTML=`<div class="sessmain"><span class="t">${running?'⚡ ':''}${s.archived?'🗄 ':''}${s.agent?'🏢 ':''}${s.renamed?'✏ ':''}${esc(s.title)}</span><span class="d">${dt}</span></div>`
          +`<div class="sessact"><span class="sx" data-a="ren" title="umbenennen">✏</span>`
          +`<span class="sx" data-a="arch" title="${s.archived?'aus Archiv holen':'archivieren'}">${s.archived?'⤴':'🗄'}</span>`
          +`<span class="sx sx-del" data-a="del" title="löschen">🗑</span></div>`;
        d.title=s.cwd||'';
        d.querySelector('.sessmain').onclick=()=>openSession(s);
        d.querySelector('[data-a=ren]').onclick=e=>{e.stopPropagation();renameSession(s);};
        d.querySelector('[data-a=arch]').onclick=e=>{e.stopPropagation();archiveSession(s,!s.archived);};
        d.querySelector('[data-a=del]').onclick=e=>{e.stopPropagation();deleteSession(s);};
        el.appendChild(d);
      });
    });
}
document.getElementById('sessSearch').addEventListener('input',e=>{sessQuery=e.target.value.trim().toLowerCase();renderSessions();});
async function renameSession(s){
  const name=prompt('Name für diese Session (leer = automatischer Titel):',s.renamed?s.title:'');
  if(name===null)return;
  try{await fetch('/api/sessions/'+encodeURIComponent(s.id)+'/rename',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});}catch{}
  loadSessions();
}
async function archiveSession(s,val){
  try{await fetch('/api/sessions/'+encodeURIComponent(s.id)+'/archive',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({archived:val})});}catch{}
  loadSessions();
}
async function deleteSession(s){
  if(!confirm('Session endgültig löschen?\n\n„'+(s.title||s.id)+'"\n\nDas kann nicht rückgängig gemacht werden.'))return;
  try{await fetch('/api/sessions/'+encodeURIComponent(s.project)+'/'+encodeURIComponent(s.id),{method:'DELETE'});}catch{}
  // Falls die gelöschte Session gerade offen ist -> frische Session zeigen
  const cv=convBySession(s.id);
  if(cv&&cv.key===activeKey)newSession();
  loadSessions();
}
async function openSession(s){
  document.getElementById('side').classList.remove('open');
  // Läuft diese Session schon (offen / gerade am Antworten)? Dann nur wieder
  // einblenden – Stream + Verlauf bleiben unangetastet (kein Neuladen!).
  const existing=convBySession(s.id);
  if(existing){mountConv(existing);loadSessions();return;}
  // Läuft serverseitig noch ein Lauf für diese Session (z.B. nach Reload)?
  // Dann Verlauf laden UND live wieder andocken (Backlog-Replay + weiter live).
  if(runningRuns[s.id]){
    const conv=makeConv({sessionId:s.id,cwd:s.cwd||WORKSPACE_DIR});
    conv.runId=runningRuns[s.id];conv.busy=true;
    mountConv(conv);
    conv.pane.innerHTML='<div class="tool">⟲ Lade Verlauf …</div>';
    let j={};try{j=await (await fetch(`/api/sessions/${encodeURIComponent(s.project)}/${encodeURIComponent(s.id)}`)).json();}catch{}
    if(j.model){conv.model=j.model;if(conv.key===activeKey){syncModelPicker(conv);zeigeModell(j.model);}}
    conv.pane.innerHTML='';
    conv.fileOffset=null;   // nach dem Lauf synchronisiert der Live-Tail neu
    (j.messages||[]).forEach(m=>{const u=m.role==='user';const b=addMsg(u?'user':'bot',md(m.text),conv,u?m.text:null);if(!u)linkifyPaths(b);});
    const wrap=document.createElement('div');wrap.className='runwrap';conv.pane.appendChild(wrap);
    if(conv.key===activeKey){updateSendBtn();scroll();}
    consumeRun(conv,wrap);
    loadSessions();return;
  }
  const conv=makeConv({sessionId:s.id,cwd:s.cwd||WORKSPACE_DIR});
  mountConv(conv);
  conv.pane.innerHTML='<div class="tool">⟲ Lade Verlauf …</div>';
  let j={};try{j=await (await fetch(`/api/sessions/${encodeURIComponent(s.project)}/${encodeURIComponent(s.id)}`)).json();}catch{}
  if(j.model){conv.model=j.model;if(conv.key===activeKey){syncModelPicker(conv);zeigeModell(j.model);}}
  conv.pane.innerHTML='';
  conv.fileOffset=j.offset;   // ab hier übernimmt der Live-Tail (pollTail)
  (j.messages||[]).forEach(m=>{const u=m.role==='user';const b=addMsg(u?'user':'bot',md(m.text),conv,u?m.text:null);if(!u)linkifyPaths(b);});
  if(!j.messages||!j.messages.length)conv.pane.innerHTML='<div class="tool">(leere Session)</div>';
  if(conv.key===activeKey)scroll();
  loadSessions();
}

// ---------- Live-Tail: fremd-laufende Sessions ohne F5 mitverfolgen ----------
// Läuft die geöffnete Session woanders (Terminal, Telegram, anderer Browser),
// wächst ihre .jsonl-Datei — wir holen alle 3 s das Neue ab und hängen es an.
// Eigene Läufe streamen weiter live über SSE (dann pausiert der Tail).
async function pollTail(){
  const conv=activeConv();
  if(!conv||conv.busy||conv.nachlauf||!conv.sessionId||document.hidden)return;   // im Nachlauf streamt SSE noch
  const sid=conv.sessionId;
  try{
    const j=await (await fetch('/api/session_tail/'+encodeURIComponent(sid)
      +'?offset='+(conv.fileOffset==null?-1:conv.fileOffset))).json();
    if(j.offset==null)return;
    // Situation kann sich während des fetch geändert haben -> nichts anfassen
    if(conv!==activeConv()||conv.busy||conv.sessionId!==sid)return;
    const firstSync=conv.fileOffset==null;
    conv.fileOffset=j.offset;
    if(firstSync)return;   // nur Position merken, Verlauf steht ja schon da
    (j.messages||[]).forEach(m=>{const u=m.role==='user';const b=addMsg(u?'user':'bot',md(m.text),conv,u?m.text:null);if(!u)linkifyPaths(b);});
  }catch{}
}
setInterval(pollTail,3000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)pollTail();});
function newSession(){
  const conv=makeConv({cwd:null});
  mountConv(conv);
  conv.pane.innerHTML='<div class="tool" style="text-align:center;margin-top:40px">⌁ Neue Session — Ordner unten wählbar, dann schreib los ⌁</div>';
  inp.focus();loadSessions();
}
document.getElementById('newBtn').onclick=newSession;

