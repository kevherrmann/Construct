// CONSTRUCT — KI-Anbieter, Bonsai, Ollama
// ---------- KI-Anbieter-Dialog (ChatGPT, Gemini, DeepSeek, Ollama) ----------
const lmmask=document.getElementById('llmmask');
function openLlmCfg(){lmmask.classList.add('show');renderLlmCfg();}
document.getElementById('lmClose').onclick=()=>{lmmask.classList.remove('show');clearTimeout(ollTimer);};
lmmask.addEventListener('click',e=>{if(e.target===lmmask){lmmask.classList.remove('show');clearTimeout(ollTimer);}});
async function renderLlmCfg(){
  const box=document.getElementById('llmcfg');
  box.innerHTML='<div class="vhint">⟲ lade Anbieter …</div>';
  try{llmProviders=await(await fetch('/api/llm/providers')).json();}catch{}
  if(!Array.isArray(llmProviders))llmProviders=[];
  box.innerHTML='';
  llmProviders.forEach(p=>{
    const div=document.createElement('div');div.className='mc-acc';
    const st=p.configured?(p.error?('⚠ '+p.error):('✓ aktiv — '+(p.models||[]).length+' Modelle')):'— nicht eingerichtet';
    div.innerHTML=`<div class="mca-head"><span class="mdot" style="background:${p.configured?(p.error?'#ff5c5c':'var(--green)'):'#444'}"></span>`
      +`<b>${PROV_ICON[p.id]||'🌐'} ${esc(p.label)}</b><span class="mca-st">${esc(st)}</span></div>`
      +`<div class="vhint" style="padding:4px 0 0">${esc(p.hint||'')}</div>`;
    const row=document.createElement('div');row.className='mca-row';
    let keyIn=null,urlIn=null;
    if(p.needs_key){
      keyIn=document.createElement('input');keyIn.type='password';keyIn.autocomplete='new-password';
      keyIn.placeholder=p.key_set?'••••••••  (gespeichert — nur zum Ändern neu eingeben)':'API-Key';
      row.appendChild(keyIn);
    }
    if(p.id==='ollama'){
      urlIn=document.createElement('input');
      urlIn.placeholder='URL (Standard: '+p.default_base+')';
      urlIn.value=(p.base_url&&p.base_url!==p.default_base)?p.base_url:'';
      row.appendChild(urlIn);
    }
    const save=document.createElement('button');save.className='cal-tbtn';
    save.textContent=p.configured?'SPEICHERN & TESTEN':'AKTIVIEREN';
    const msg=document.createElement('span');msg.className='vhint';msg.style.flex='1';
    save.onclick=async()=>{
      save.disabled=true;msg.textContent='⟲ speichere & teste …';
      const body={id:p.id,enabled:true};
      if(keyIn&&keyIn.value.trim())body.api_key=keyIn.value.trim();
      if(urlIn)body.base_url=urlIn.value.trim();
      try{
        const r=await fetch('/api/llm/providers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const j=await r.json();if(!r.ok)throw new Error(j.error||('HTTP '+r.status));
        msg.textContent=j.ok?('✅ verbunden — '+j.models+' Modelle'):('⚠ '+(j.error||'?')+' (gespeichert — Standard-Modelle aktiv)');
        await loadProviders(true);setTimeout(renderLlmCfg,1200);
      }catch(e){save.disabled=false;msg.textContent='⚠ '+(e.message||e);}
    };
    row.appendChild(save);
    if(p.configured){
      const off=document.createElement('button');off.className='cal-tbtn';off.textContent='✕ AUS';
      off.style.color='#ff5c5c';off.style.borderColor='#5a1f1f';off.title='Anbieter deaktivieren (Key bleibt gespeichert)';
      off.onclick=async()=>{
        await fetch('/api/llm/providers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:p.id,enabled:false})});
        await loadProviders(true);renderLlmCfg();
      };
      row.appendChild(off);
    }
    row.appendChild(msg);
    div.appendChild(row);
    if(p.id==='ollama'){   // immer zeigen — enthält notfalls den Install-Button
      const ob=document.createElement('div');ob.id='ollBox';
      ob.innerHTML='<div class="vhint">⟲ prüfe Ollama …</div>';
      div.appendChild(ob);
    }
    if(p.id==='bonsai'){   // liegt der Server gerade im VRAM? + Knopf zum Freigeben
      const bb=document.createElement('div');bb.id='bonsaiBox';
      div.appendChild(bb);
    }
    box.appendChild(div);
  });
  if(document.getElementById('ollBox'))renderOllamaBox();
  if(document.getElementById('bonsaiBox'))renderBonsaiBox();
  const intro=document.getElementById('llmintro');
  box.insertAdjacentHTML('beforeend','<div class="vhint" style="margin-top:10px">🔒 Keys liegen nur auf deinem Server in <code>.llm-config.json</code> (chmod 600) — sie tauchen nie im Browser auf.<br>'
    +T('⚡ Fremde Modelle laufen über <b>Hermes</b> und können damit Dateien und Terminal. '
    +'Skills, Kalender und E-Mail bleiben Claude Code vorbehalten. '
    +'Beim Modellwechsel mitten im Gespräch nimmt {a} den bisherigen Verlauf automatisch mit.',{a:esc(ASSISTANT)})+'</div>');
}

// ---------- Bonsai: Server-Zustand (VRAM belegt?) ----------
async function renderBonsaiBox(){
  const bb=document.getElementById('bonsaiBox');if(!bb)return;
  let st={};try{st=await(await fetch('/api/bonsai/status')).json();}catch{return;}
  if(!st.available){bb.innerHTML='<div class="vhint">⚠ Bonsai-Demo nicht gefunden — <code>setup.sh</code> im Bonsai-Ordner ausführen oder <code>BONSAI_DIR</code> setzen.</div>';return;}
  bb.innerHTML=`<div class="mca-row" style="align-items:center"><span class="vhint" style="flex:1">${st.running?'🟢 läuft — Modell im VRAM (stoppt nach '+st.idle_min+' Min Leerlauf von selbst)':'⚪ aus — VRAM frei, startet beim ersten Prompt'}</span>`
    +(st.running?'<button class="cal-tbtn" id="bonsaiStop">⏹ JETZT STOPPEN</button>':'')+'</div>';
  const b=document.getElementById('bonsaiStop');
  if(b)b.onclick=async()=>{b.disabled=true;await fetch('/api/bonsai/stop',{method:'POST'}).catch(()=>{});renderBonsaiBox();};
}

// ---------- Ollama-Modelle verwalten (Liste, Download mit Fortschritt, Löschen) ----------
let ollTimer=null,ollDoneSeen=new Set();
const fmtGB=n=>n>=1e9?(n/1e9).toFixed(1).replace('.',',')+' GB':Math.round((n||0)/1e6)+' MB';
async function ollPull(model){
  try{
    const r=await fetch('/api/ollama/pull',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model})});
    if(!r.ok){const j=await r.json().catch(()=>({}));alert(j.error||'Download konnte nicht starten');}
  }catch(e){alert('Download konnte nicht starten: '+(e.message||e));}
  renderOllamaBox();
}
async function renderOllamaBox(){
  clearTimeout(ollTimer);
  if(!lmmask.classList.contains('show')||!document.getElementById('ollBox'))return;
  let d={};try{d=await(await fetch('/api/ollama/models')).json();}catch{return;}
  const bx=document.getElementById('ollBox');
  if(!bx||!lmmask.classList.contains('show'))return;   // Dialog inzwischen zu
  const inst=d.installed||[],pulls=d.pulls||{},cat=d.catalog||[];
  const have=new Set(inst.map(m=>m.name));
  // Ollama läuft (noch) nicht -> Installieren/Starten direkt aus dem Dialog
  if(!d.reachable){
    let h='';
    const ins=d.install;
    if(ins&&!ins.done){
      const pct=ins.total?Math.round(ins.completed/ins.total*100):0;
      h+=`<div class="oll-row"><span class="oll-name">⚙ Ollama</span>`
        +(ins.total?`<span class="oll-prog"><i style="width:${pct}%"></i></span>`:'')
        +`<span class="oll-meta">${esc(ins.status||'…')}${ins.total?' · '+pct+'% · '+fmtGB(ins.completed)+' / '+fmtGB(ins.total):''}</span></div>`;
      ollTimer=setTimeout(renderOllamaBox,1200);
    }else{
      if(ins&&ins.error)h+=`<div class="vhint" style="color:#ff9b9b;padding:6px 0">⚠ ${esc(ins.error).slice(0,300)}</div>`;
      else if(d.error)h+=`<div class="vhint" style="color:#ff9b9b;padding:6px 0">${esc(d.error).slice(0,200)}</div>`;
      h+=`<div class="mca-row"><button class="obtn" id="ollInstall" style="padding:9px 16px">${d.bin?'▶ OLLAMA STARTEN':'⬇ OLLAMA INSTALLIEREN &amp; STARTEN'}</button>`
        +`<span class="vhint" style="flex:1;margin:0">${d.bin
          ?'Ollama ist installiert, läuft aber gerade nicht — ein Klick startet es.'
          :'Cody lädt das offizielle Linux-Paket (~1–2 GB), entpackt es nach <code>~/.cody-ollama</code> und startet es — ganz ohne Terminal. Startet nach einem Neustart automatisch mit.'}</span></div>`;
    }
    bx.innerHTML=h;
    const bi=document.getElementById('ollInstall');
    if(bi)bi.onclick=async()=>{bi.disabled=true;bi.textContent='⟲ …';
      await fetch('/api/ollama/install',{method:'POST'}).catch(()=>{});renderOllamaBox();};
    return;
  }
  // Install gerade eben fertig geworden -> Picker + Dialog einmalig nachladen
  if(d.install&&d.install.done&&!d.install.error&&d.install.status&&!ollDoneSeen.has('__install__')){
    ollDoneSeen.add('__install__');await loadProviders(true);renderLlmCfg();return;}
  // frisch fertig gewordene Downloads -> Modell-Picker einmalig nachladen
  Object.entries(pulls).forEach(([m,s])=>{if(s.done&&!s.error&&!ollDoneSeen.has(m)){ollDoneSeen.add(m);loadProviders(true);}});
  // Eingabe im Freitextfeld über die Poll-Neuzeichnung retten
  const oldFree=document.getElementById('ollFree');
  const keepVal=oldFree?oldFree.value:'',keepFocus=oldFree&&document.activeElement===oldFree;
  let h='';
  if(d.error)h+=`<div class="vhint" style="color:#ff9b9b;padding:6px 0">${esc(d.error)}</div>`;
  h+=`<div class="kal-uh" style="margin-top:10px">INSTALLIERTE MODELLE (${inst.length})</div>`;
  if(!inst.length&&!d.error)h+='<div class="vhint" style="padding:2px 0">Noch keine Modelle installiert — unten eins aussuchen und ⬇ klicken.</div>';
  inst.forEach(m=>{h+=`<div class="oll-row"><span class="oll-name">🦙 ${esc(m.name)}</span>`
    +`<span class="oll-meta">${fmtGB(m.size)}${m.param?' · '+esc(m.param):''}${m.quant?' · '+esc(m.quant):''}</span>`
    +`<button class="obtn red" data-odel="${esc(m.name)}" title="Modell von der Platte löschen">🗑 LÖSCHEN</button></div>`;});
  Object.entries(pulls).forEach(([m,s])=>{
    if(s.done&&s.error)h+=`<div class="oll-row"><span class="oll-name">⬇ ${esc(m)}</span>`
      +`<span class="oll-meta" style="color:#ff9b9b">⚠ ${esc(s.error).slice(0,160)}</span></div>`;
    else if(!s.done){const pct=s.total?Math.round(s.completed/s.total*100):0;
      h+=`<div class="oll-row"><span class="oll-name">⬇ ${esc(m)}</span>`
      +`<span class="oll-prog"><i style="width:${pct}%"></i></span>`
      +`<span class="oll-meta">${s.total?pct+'% · '+fmtGB(s.completed)+' / '+fmtGB(s.total):esc(s.status||'…')}</span>`
      +`<button class="obtn red" data-ocancel="${esc(m)}" title="Download abbrechen">✕</button></div>`;}
    else h+=`<div class="oll-row"><span class="oll-name">✅ ${esc(m)}</span><span class="oll-meta">fertig geladen — steht im 🧠-Menü bereit</span></div>`;
  });
  const offer=cat.filter(c=>!have.has(c.name)&&!pulls[c.name]);
  if(offer.length){
    h+='<div class="kal-uh" style="margin-top:12px">BELIEBTE MODELLE ZUM LADEN</div>';
    offer.forEach(c=>{h+=`<div class="oll-row"><span class="oll-name">${esc(c.name)}</span>`
      +`<span class="oll-meta">${esc(c.desc)}</span>`
      +`<button class="obtn" data-opull="${esc(c.name)}">⬇ ${esc(c.size)}</button></div>`;});
  }
  h+=`<div class="mca-row"><input id="ollFree" placeholder="anderes Modell von ollama.com/library — z.B. qwen3:32b" autocomplete="off">`
    +`<button class="obtn" id="ollFreeGo" style="padding:8px 14px">⬇ LADEN</button></div>`;
  bx.innerHTML=h;
  bx.querySelectorAll('[data-opull]').forEach(b=>b.onclick=()=>ollPull(b.dataset.opull));
  bx.querySelectorAll('[data-ocancel]').forEach(b=>b.onclick=async()=>{
    await fetch('/api/ollama/pull_cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:b.dataset.ocancel})});
    renderOllamaBox();});
  bx.querySelectorAll('[data-odel]').forEach(b=>b.onclick=async()=>{
    if(!confirm('Modell „'+b.dataset.odel+'“ wirklich von der Platte löschen?\n\n(Kann jederzeit neu geladen werden.)'))return;
    const r=await fetch('/api/ollama/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:b.dataset.odel})});
    if(!r.ok){const j=await r.json().catch(()=>({}));alert(j.error||'Löschen fehlgeschlagen');}
    loadProviders(true);renderOllamaBox();});
  const fi=document.getElementById('ollFree'),fg=document.getElementById('ollFreeGo');
  fi.value=keepVal;
  if(keepFocus){fi.focus();fi.setSelectionRange(keepVal.length,keepVal.length);}
  fg.onclick=()=>{if(fi.value.trim())ollPull(fi.value.trim());};
  fi.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();fg.click();}});
  // solange etwas lädt: Fortschritt weiter pollen (Download läuft server-seitig)
  if(Object.values(pulls).some(s=>!s.done))ollTimer=setTimeout(renderOllamaBox,1200);
}

