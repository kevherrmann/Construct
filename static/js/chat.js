// CONSTRUCT — Werkzeug-Boxen, Warteschlange, Senden/Streamen, Anhänge
// ---------- Tool- & Thinking-Boxen ----------
function toolSummary(name,inp){
  if(!inp||typeof inp!=='object')return '';
  const f=inp.command||inp.file_path||inp.path||inp.pattern||inp.url||inp.query||inp.prompt||inp.description;
  if(f)return String(f).replace(/\s+/g,' ').slice(0,90);
  const k=Object.keys(inp)[0];return k?`${k}: ${String(inp[k]).slice(0,70)}`:'';
}
// Edit/Write als rot/grün-Diff statt rohem JSON — Kontrolle auf einen Blick
function diffHtml(name,inp){
  const cap=s=>esc(String(s??'').slice(0,4000))+(String(s??'').length>4000?'\n… (gekürzt)':'');
  const edits=name==='MultiEdit'&&Array.isArray(inp.edits)?inp.edits
    :('old_string'in inp||'new_string'in inp)?[inp]:null;
  if(name==='Write'&&typeof inp.content==='string')
    return `<div class="df-file">📄 ${esc(inp.file_path||'')}</div><div class="df df-add">${cap(inp.content)}</div>`;
  if(!edits)return null;
  let h=`<div class="df-file">📄 ${esc(inp.file_path||'')}</div>`;
  edits.forEach(e=>{
    if(e.old_string)h+=`<div class="df df-del">${cap(e.old_string)}</div>`;
    h+=`<div class="df df-add">${cap(e.new_string)}</div>`;
  });
  return h;
}
function makeTool(ev){
  const el=document.createElement('div');el.className='toolcall';
  el.innerHTML=`<div class="tc-head"><span class="tc-ic">⚙</span><span class="tc-name">${esc(ev.name)}</span>`
    +`<span class="tc-sum">${esc(toolSummary(ev.name,ev.input))}</span><span class="tc-st">⏳</span><span class="tc-tg">▸</span></div>`
    +`<div class="tc-body"><div class="tc-lbl">EINGABE</div><div class="tc-in"></div>`
    +`<div class="tc-lbl tc-olbl" style="display:none">ERGEBNIS</div><div class="tc-out"></div></div>`;
  const dh=(ev.input&&typeof ev.input==='object')?diffHtml(ev.name,ev.input):null;
  if(dh)el.querySelector('.tc-in').innerHTML=dh;
  else el.querySelector('.tc-in').textContent=(ev.input&&typeof ev.input==='object')?JSON.stringify(ev.input,null,2):String(ev.input??'');
  el.querySelector('.tc-head').onclick=()=>{el.classList.toggle('open');el.querySelector('.tc-tg').textContent=el.classList.contains('open')?'▾':'▸';};
  return el;
}
function skillUseLabel(inp){if(!inp||typeof inp!=='object')return '';return String(inp.command||inp.name||inp.skill||Object.values(inp)[0]||'').slice(0,70);}
function skillFileName(p){const m=/skills\/([^/]+)\/SKILL\.md$/i.exec(p||'');return m?m[1]:((p||'').split('/').filter(Boolean).pop()||'');}
function makeSkillBanner(kind,label){const el=document.createElement('div');el.className='skillbanner';
  el.innerHTML=`🧠 <b>Skill ${kind}</b>${label?': <span class="sk-n">'+esc(label)+'</span>':''}`;return el;}
function fillTool(el,ev){
  if(!el)return;
  el.querySelector('.tc-st').textContent=ev.is_error?'✗':'✓';
  if(ev.is_error)el.classList.add('err-tool');
  el.querySelector('.tc-olbl').style.display='';
  el.querySelector('.tc-out').textContent=(ev.content&&ev.content.trim())?ev.content:'(kein Ergebnis)';
}
// ---------- Warteschlange ----------
function renderQueue(){
  const q=document.getElementById('queuebar');const conv=activeConv();const ql=conv?conv.queue:[];
  if(!ql.length){q.style.display='none';q.innerHTML='';return;}
  q.style.display='block';
  q.innerHTML='⏳ <b>'+ql.length+'</b> in Warteschlange — läuft automatisch nach der aktuellen Aufgabe (gleiche Session):'
    +ql.map((m,i)=>`<div class="qitem"><span>${esc(m.text).slice(0,90)||'(Bild)'}</span><span class="qx" data-i="${i}">✕</span></div>`).join('');
  q.querySelectorAll('.qx').forEach(b=>b.onclick=()=>{ql.splice(+b.dataset.i,1);renderQueue();});
}
function updateSendBtn(){const b=document.getElementById('send');const busy=!!(activeConv()&&activeConv().busy);
  b.textContent=busy?'➤ EINWERFEN':'SENDEN';
  b.title=busy?'Geht SOFORT an den laufenden Cody (Steering) — er bezieht es in die aktuelle Arbeit ein':'';
  document.getElementById('stop').style.display=busy?'':'none';
  chat.classList.toggle('busy',busy);}

// ---------- Send ----------
// UI-Einstieg: schickt an die GERADE AKTIVE Unterhaltung.
async function send(){
  const conv=activeConv();if(!conv)return;
  const text=inp.value.trim();const images=pending.map(p=>p.path);const urls=pending.map(p=>p.url);
  if(!text&&!images.length)return;
  if(text.startsWith('/')&&!images.length){inp.value='';autosize();appCommand(text);return;}
  inp.value='';autosize();pending=[];renderThumbs();
  if(conv.busy||conv.nachlauf){
    // Cody arbeitet gerade (oder sein Prozess wartet im Nachlauf auf eine
    // Hintergrundaufgabe): Nachricht DIREKT in den laufenden Prozess einwerfen
    // (Steering). Klappt das nicht (Turn gerade fertig), normale Warteschlange —
    // im Nachlauf stattdessen ein frischer Lauf per --resume.
    if(conv.runId){
      try{
        const r=await fetch('/api/inject/'+encodeURIComponent(conv.runId),{method:'POST',
          headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,images,urls})});
        if(r.ok){if(conv.nachlauf){conv.nachlauf=false;conv.busy=true;if(conv.key===activeKey)updateSendBtn();}return;}
      }catch{}
    }
    if(conv.nachlauf){conv.nachlauf=false;}
    else{conv.queue.push({text,images,urls});renderQueue();return;}
  }
  runSend(conv,text,images,urls);
}

// Startet einen entkoppelten Lauf: POST holt die run_id, dann dockt consumeRun an.
async function runSend(conv,text,images,urls){
  conv.busy=true;conv.stopReq=false;if(conv.key===activeKey)updateSendBtn();
  // cwd beim ersten Senden festschreiben, damit parallele Sessions stabil bleiben.
  if(!conv.cwd)conv.cwd=currentCwd||WORKSPACE_DIR;
  const sendCwd=conv.cwd, sendMode=currentMode;
  let uhtml=md(text);urls.forEach(u=>uhtml+=attHtml(u));
  addMsg('user',uhtml,conv,text);
  // Alles, was zu DIESEM Lauf gehört (Bot-Antworten + eingeworfene Nachrichten),
  // lebt in einem Container — bei Reconnect wird er komplett aus dem Replay neu gebaut.
  const wrap=document.createElement('div');wrap.className='runwrap';conv.pane.appendChild(wrap);
  try{
    const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:text,session_id:conv.sessionId,images,cwd:sendCwd,mode:sendMode,model:conv.model||''})});
    let j={};try{j=await r.json();}catch{}
    if(!r.ok||!j.run_id)throw new Error(j.error||(r.status===401?'Nicht angemeldet (Passwort?)':'HTTP '+r.status));
    conv.runId=j.run_id;if(j.session_id)conv.sessionId=j.session_id;
  }catch(e){
    wrap.innerHTML='<div class="err">⚠ Konnte Anfrage nicht starten: '+esc(e.message||''+e)+'</div>';
    finishRun(conv);return;
  }
  await consumeRun(conv,wrap);
}

// Dockt an conv.runId an: spielt erst den Backlog nach, dann live — und reconnectet
// bei Aussetzern (Reload/Schlaf/Netz). Der Lauf selbst läuft server-seitig weiter.
// wrap = Container für den GANZEN Lauf (mehrere Bubbles bei eingeworfenen Nachrichten).
async function consumeRun(conv,wrap){
  const CARET='<span class="caret">&nbsp;</span>';
  let finished=false;
  while(conv.runId&&!finished&&!conv.stopReq){
    wrap.innerHTML='';   // bei jedem (Re)Connect frisch aus dem Replay aufbauen
    let blk=null,textEl=null,textAcc='',thinkMarked=false,thinkEl=null,flow=null;const toolEls={};
    // Ergebnisdateien: was dieser Zug per Write/Edit angefasst hat, kommt am Ende
    // als Zeile mit Links (ansehen / herunterladen) — man muss nicht im Verlauf
    // nach dem Pfad suchen.
    const written=new Map();   // tool-id -> Pfad (nur erfolgreiche zählen)
    const notePath=ev=>{const fp=ev.input&&(ev.input.file_path||ev.input.path||ev.input.notebook_path);
      if(ev.id&&fp&&/^(Write|Edit|MultiEdit|NotebookEdit|write|edit)/i.test(ev.name||'')&&!/SKILL\.md$/i.test(fp))written.set(ev.id,{fp,ok:false});};
    const filesLine=()=>{const fps=[...new Set([...written.values()].filter(w=>w.ok).map(w=>w.fp))];written.clear();if(!fps.length)return;
      const d=document.createElement('div');d.className='statline files';d.innerHTML='📁 '
        +fps.map(fp=>`<a href="/api/file?path=${encodeURIComponent(fp)}" target="_blank" rel="noopener" title="${esc(fp)}">${esc(fp.split('/').pop())}</a>`
          +`<a href="/api/file?path=${encodeURIComponent(fp)}&dl=1" title="herunterladen">⬇</a>`).join(' · ');
      flow.appendChild(d);};
    const newThinking=()=>{thinkEl=document.createElement('div');thinkEl.className='thinking';
      thinkEl.innerHTML='Denke nach<span class="td"></span><span class="td"></span><span class="td"></span>';
      flow.appendChild(thinkEl);};
    let turnBubble=null;
    const newTurn=()=>{const bubble=turnBubble=addMsgTo(wrap,'bot','');flow=document.createElement('div');bubble.appendChild(flow);thinkMarked=false;newThinking();};
    const killThinking=()=>{if(thinkEl){thinkEl.remove();thinkEl=null;}};
    const sc=()=>{if(conv.key===activeKey)scroll();};
    const endBlock=()=>{if(blk==='text'&&textEl){textEl.innerHTML=md(textAcc);linkifyPaths(textEl);addCopyBtns(textEl);}blk=null;textEl=null;textAcc='';};
    const onText=t=>{killThinking();if(blk!=='text'){endBlock();textEl=document.createElement('div');textEl.className='seg';flow.appendChild(textEl);blk='text';}textAcc+=t;textEl.innerHTML=md(textAcc)+CARET;sc();};
    const mark=()=>{killThinking();if(thinkMarked)return;thinkMarked=true;const tm=document.createElement('div');tm.className='thinkmark';tm.textContent='💭 nachgedacht';flow.insertBefore(tm,flow.firstChild);};
    newTurn();
    const ctrl=new AbortController();conv.streamCtrl=ctrl;let wd;
    const bump=()=>{clearTimeout(wd);wd=setTimeout(()=>ctrl.abort('idle'),40000);};
    let dropped=false;
    try{
      bump();
      const res=await fetch('/api/stream/'+encodeURIComponent(conv.runId),{signal:ctrl.signal});
      if(res.status===404){finished=true;flow.innerHTML='<div class="tool">⚠ Lauf nicht mehr verfügbar (zu alt/aufgeräumt). Schick einfach nochmal.</div>';break;}
      const reader=res.body.getReader(),dec=new TextDecoder();let buf='';
      while(true){
        const {value,done}=await reader.read();if(done)break;
        bump();
        buf+=dec.decode(value,{stream:true});let i;
        while((i=buf.indexOf('\n\n'))>=0){
          const line=buf.slice(0,i);buf=buf.slice(i+2);
          if(!line.startsWith('data: '))continue;
          let ev;try{ev=JSON.parse(line.slice(6))}catch{continue}
          if(ev.type==='session'){conv.sessionId=ev.session_id;if(conv.key===activeKey)loadSessions();}
          else if(ev.type==='text')onText(ev.text);
          else if(ev.type==='user_inject'){endBlock();killThinking();
            let uh=md(ev.text||'');(ev.urls||[]).forEach(u=>uh+=attHtml(u));
            addMsgTo(wrap,'user',uh);newTurn();sc();}
          else if(ev.type==='thinking_marker')mark();
          else if(ev.type==='tool'){killThinking();endBlock();
            const fp=(ev.input&&ev.input.file_path)||'';
            if(/^skill$/i.test(ev.name||'')){flow.appendChild(makeSkillBanner('genutzt',skillUseLabel(ev.input)));}
            else if(/SKILL\.md$/i.test(fp)){flow.appendChild(makeSkillBanner('gespeichert',skillFileName(fp)));const el=makeTool(ev);if(ev.id)toolEls[ev.id]=el;flow.appendChild(el);}
            else{const el=makeTool(ev);if(ev.id)toolEls[ev.id]=el;flow.appendChild(el);}
            notePath(ev);sc();}
          else if(ev.type==='tool_result'){fillTool(toolEls[ev.id],ev);if(written.has(ev.id))written.get(ev.id).ok=!ev.is_error;sc();}
          else if(ev.type==='stats'){killThinking();endBlock();const s=document.createElement('div');s.className='statline';
            s.innerHTML=`⏱ ${esc(fmtDur(ev.duration_ms))} · 🧮 ${esc(fmtNum(ev.out))} Tokens`
              +(ev.ctx?` · 📚 Kontext ${esc(fmtNum(ev.ctx))}`:'')
              +(ev.model?` · 🧠 ${esc(ev.model)}`:'');
            s.title='Dauer · Output-Tokens dieser Antwort · gelesener Kontext (großteils Cache) · Modell';
            flow.appendChild(s);filesLine();sc();zeigeModell(ev.model);}
          else if(ev.type==='nachlauf'){killThinking();endBlock();
            // Zug fertig, aber claude wartet noch auf eigene Hintergrundaufgaben.
            // Der Prozess bleibt offen, Kevin darf tippen (geht per inject in
            // denselben Prozess), und was der Hintergrund liefert, kommt als
            // neue Sprechblase — siehe 'neuer_zug'.
            conv.nachlauf=true;conv.busy=false;if(conv.key===activeKey)updateSendBtn();
            const n=document.createElement('div');n.className='tool';
            n.textContent='⏳ läuft noch im Hintergrund: '+(ev.tasks||[]).join(' · ')+' — ich melde mich, sobald es fertig ist.';
            flow.appendChild(n);sc();}
          else if(ev.type==='neuer_zug'){endBlock();killThinking();conv.nachlauf=false;conv.busy=true;if(conv.key===activeKey)updateSendBtn();newTurn();sc();}
          else if(ev.type==='nachlauf_ende'){conv.nachlauf=false;}
          else if(ev.type==='done'){killThinking();if(ev.session_id)conv.sessionId=ev.session_id;endBlock();if(!conv.nachlauf)finished=true;
            if(SETTINGS.tts?.auto&&conv.key===activeKey&&turnBubble){const b=turnBubble.closest('.msgcol')?.querySelector('.say-btn');sayPlay(sayText(turnBubble),b);}}
          else if(ev.type==='error'){killThinking();endBlock();finished=true;const e=document.createElement('div');e.className='err';e.textContent='⚠ '+ev.message;flow.appendChild(e);}
        }
      }
      endBlock();clearTimeout(wd);
      if(!finished&&!conv.stopReq)dropped=true;   // Stream zu, aber Lauf nicht fertig -> reconnect
    }catch(e){
      clearTimeout(wd);endBlock();
      if(conv.stopReq)finished=true; else dropped=true;
    }
    if(dropped&&!conv.stopReq){
      if(conv.key===activeKey){const n=document.createElement('div');n.className='tool';n.textContent='… Verbindung verloren – dock wieder an …';flow.appendChild(n);scroll();}
      await new Promise(r=>setTimeout(r,1000));
    }
  }
  if(conv.stopReq){const s=document.createElement('div');s.className='tool';s.textContent='⏹ Gestoppt.';wrap.appendChild(s);}
  finishRun(conv);
}

function finishRun(conv){
  conv.runId=null;conv.busy=false;conv.nachlauf=false;conv.streamCtrl=null;conv.stopReq=false;
  conv.fileOffset=null;   // Tail-Position neu syncen — der Lauf wurde ja live gezeigt
  if(conv.key===activeKey){updateSendBtn();inp.focus();}
  loadSessions();loadHud();
  if(conv.queue.length){const nx=conv.queue.shift();if(conv.key===activeKey)renderQueue();runSend(conv,nx.text,nx.images,nx.urls);}
}

// ---------- Anhänge (Bilder, PDFs) ----------
const IS_PDF=u=>/\.pdf$/i.test(u||'');
// Anhang in einer Nachricht: Bild inline, PDF als Link-Chip.
const attHtml=u=>IS_PDF(u)?`<a class="att" href="${u}" target="_blank">📄 PDF</a>`:`<img src="${u}">`;
async function uploadFile(f){
  const fd=new FormData();fd.append('file',f);
  let j;try{j=await (await fetch('/api/upload',{method:'POST',body:fd})).json();}catch{j={error:'Upload fehlgeschlagen'};}
  if(!j.path){alert(j.error||'Upload fehlgeschlagen');return;}
  pending.push({path:j.path,url:j.url,name:j.name||f.name});renderThumbs();
}
function renderThumbs(){
  const t=document.getElementById('thumbs');t.innerHTML='';
  pending.forEach((p,idx)=>{
    const d=document.createElement('div');d.className='th';
    d.innerHTML=(IS_PDF(p.url)?`<span class="doc" title="${esc(p.name||'')}">📄 ${esc(p.name||'PDF')}</span>`:`<img src="${p.url}">`)+`<span class="x">✕</span>`;
    d.querySelector('.x').onclick=()=>{pending.splice(idx,1);renderThumbs();};t.appendChild(d);
  });
}
document.getElementById('attach').onclick=()=>document.getElementById('file').click();
document.getElementById('file').onchange=e=>{[...e.target.files].forEach(uploadFile);e.target.value='';};
inp.addEventListener('paste',e=>{for(const it of e.clipboardData.items){if(it.type.startsWith('image/')){uploadFile(it.getAsFile());e.preventDefault();}}});
const dm=document.getElementById('dropmask');
addEventListener('dragover',e=>{e.preventDefault();dm.classList.add('show');});
addEventListener('dragleave',e=>{if(e.relatedTarget===null)dm.classList.remove('show');});
// Im Desktop-Fenster (WebKitGTK) kommen hereingezogene Dateien hier nur als
// Name an, nicht lesbar - dort uebernimmt desktop.py den Drop und meldet die
// Anhaenge ueber __nativeDrop. Im Browser laeuft der normale Upload.
const NATIVE_DROP=()=>window.pywebview&&window.pywebview.platform==='gtkwebkit2';
const ATT_EXT=/\.(png|jpe?g|gif|webp|bmp|svg|heic|pdf)$/i;
window.__nativeDrop=items=>{items.forEach(p=>pending.push({path:p.path,url:p.url,name:p.name}));renderThumbs();};
addEventListener('drop',e=>{e.preventDefault();dm.classList.remove('show');if(NATIVE_DROP())return;
  [...e.dataTransfer.files].forEach(f=>(f.type.startsWith('image/')||ATT_EXT.test(f.name))&&uploadFile(f));});

