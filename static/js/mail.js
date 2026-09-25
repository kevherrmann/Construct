// CONSTRUCT — E-Mails
// ---------- E-Mails ----------
// Konten + IMAP/SMTP laufen im Backend (mail.py). Kategorien sind rein lokal
// (nur hier im Chat) — Löschen passiert dagegen ECHT auf dem Server (Papierkorb).
let mailAccounts=[],mailCats=[],mailMsgs=[],mailErrors={},mailFilter={acc:'',cat:'',q:''},mailAtt=[],mailLoaded=false,msPollTimer=null;
let mailSel=new Set();                 // Auswahl für Sammel-Löschen: "konto|uid"
const mailKey=m=>m.account+'|'+m.uid;
// mailPage = wo der Nutzer in der Mail-Ansicht gerade IST. Der Hintergrund-Abruf
// (loadMailList) darf NUR die Liste neu zeichnen, wenn die Liste auch offen ist —
// sonst reißt er Kevin die Einstellungs-/Schreiben-Seite unterm Tippen weg.
let mailPage='list';
const MAIL_COLORS=['var(--green)','var(--link)','#ffd24a','#7fb2ff','#ff9bd2','#c9ff7f'];
const accColor=em=>{const i=mailAccounts.findIndex(a=>a.email===em);return MAIL_COLORS[(i<0?0:i)%MAIL_COLORS.length];};
const accName=em=>(em||'').split('@')[0];
const cssId=s=>(s||'').replace(/[^a-z0-9]/gi,'-');
const fmtSize=n=>n>=1048576?(n/1048576).toFixed(1)+' MB':n>=1024?Math.round(n/1024)+' kB':n+' B';
function fmtMailDate(ts){if(!ts)return '';const d=new Date(ts*1000),now=new Date();
  if(d.toDateString()===now.toDateString())return d.toLocaleTimeString(I18N.locale,{hour:'2-digit',minute:'2-digit'});
  const s=d.toLocaleDateString(I18N.locale,{day:'2-digit',month:'2-digit'});
  return d.getFullYear()===now.getFullYear()?s:s+String(d.getFullYear()).slice(2);}
async function mailState(){
  try{mailAccounts=(await(await fetch('/api/mail/accounts')).json()).accounts||[];}catch{mailAccounts=[];}
  try{mailCats=(await(await fetch('/api/mail/categories')).json()).categories||[];}catch{mailCats=[];}
}
function renderMailLoading(){mailPage='list';chat.innerHTML='<div class="tool" style="text-align:center;margin-top:40px">⟲ Rufe Postfächer ab … es werden ALLE Mails geladen — bei großen Postfächern kann das eine Minute dauern.</div>';}
let mailWantSettings=false;   // gesetzt von ⚙ Einstellungen → "Konten verwalten"
async function loadMailView(){
  await mailState();renderMailSide();
  if(mailWantSettings||!mailAccounts.some(a=>a.configured)){mailWantSettings=false;renderMailSettings();return;}
  renderMailLoading();await loadMailList(false);
}
async function loadMailList(force){
  // limit=9999 = praktisch alle. (Bewusst nicht 0: der alte Server-Code würde
  // 0 auf 1 Mail kappen — 9999 heißt dort einfach 200, also kein Schaden.)
  try{const r=await fetch('/api/mail/list?limit=9999'+(force?'&force=1':''));const j=await r.json();
    if(!r.ok)throw new Error(j.error||('HTTP '+r.status));
    mailMsgs=j.messages||[];mailErrors=j.errors||{};mailLoaded=true;}
  catch(e){mailMsgs=[];mailErrors={'Abruf':String(e.message||e)};}
  renderMailSide();
  if(mailPage==='list')renderMailList();   // andere Unterseite offen? Nicht drüberbügeln!
}
function mailVisible(){
  // Kategorisierte Mails verschwinden aus dem Posteingang und leben nur noch in
  // ihrer Kategorie. Ausnahme: bei aktiver Suche wird ÜBERALL gesucht.
  const q=(mailFilter.q||'').trim().toLowerCase();
  return mailMsgs.filter(m=>(!mailFilter.acc||m.account===mailFilter.acc)
    &&(mailFilter.cat?m.category===mailFilter.cat:(q?true:!m.category))
    &&(!q||((m.from_name||'')+' '+(m.from_addr||'')+' '+(m.subject||'')+' '+(m.category||'')+' '+m.account).toLowerCase().includes(q)));}
async function backToInbox(){
  if(mailAccounts.some(a=>a.configured)&&!mailLoaded){renderMailLoading();await loadMailList(false);}
  else{renderMailSide();renderMailList();}
}

function renderMailSide(){
  const el=document.getElementById('mailside');if(!el)return;
  let h='<button class="kal-add" id="mailNew">✉ NEUE E-MAIL</button>';
  h+='<div class="kal-uh">KONTEN</div>';
  h+=`<div class="mside${!mailFilter.acc?' on':''}" data-acc="">📥 <span class="mn">Alle Postfächer</span>`
    +(mailMsgs.filter(m=>!m.seen).length?`<span class="fc">${mailMsgs.filter(m=>!m.seen).length}</span>`:'')+'</div>';
  mailAccounts.forEach(a=>{
    const unread=mailMsgs.filter(m=>m.account===a.email&&!m.seen).length;
    const err=mailErrors[a.email];
    h+=`<div class="mside${mailFilter.acc===a.email?' on':''}" data-acc="${esc(a.email)}" title="${esc(err||a.email)}">`
      +`<span class="mdot" style="background:${a.configured?(err?'#ff5c5c':accColor(a.email)):'#444'};box-shadow:0 0 6px ${a.configured&&!err?accColor(a.email):'transparent'}"></span>`
      +`<span class="mn">${esc(accName(a.email))}${err?' ⚠':''}</span>`
      +(unread?`<span class="fc">${unread}</span>`:'')+`</div>`;
  });
  h+='<div class="kal-uh">KATEGORIEN <span id="catAdd" style="cursor:pointer;color:var(--green)" title="Neue Kategorie anlegen">＋</span></div>';
  const uncat=mailMsgs.filter(m=>!m.category).length;
  h+=`<div class="mside${!mailFilter.cat?' on':''}" data-cat="" title="Alles ohne Kategorie">▤ <span class="mn">Posteingang</span>`
    +(uncat?`<span class="fc">${uncat}</span>`:'')+'</div>';
  mailCats.forEach(c=>{
    const n=mailMsgs.filter(m=>m.category===c).length;
    h+=`<div class="mside${mailFilter.cat===c?' on':''}" data-cat="${esc(c)}"><span class="mn">${esc(c)}</span>`
      +(n?`<span class="fc">${n}</span>`:'')+`<span class="mx" data-delcat="${esc(c)}" title="Kategorie löschen">✕</span></div>`;
  });
  h+='<button class="kal-add" id="mailCfg" style="margin-top:14px">⚙ KONTEN VERWALTEN</button>';
  el.innerHTML=h;
  el.querySelectorAll('[data-acc]').forEach(d=>d.onclick=()=>{mailFilter.acc=d.dataset.acc;renderMailSide();renderMailList();});
  el.querySelectorAll('[data-cat]').forEach(d=>d.onclick=()=>{mailFilter.cat=d.dataset.cat;renderMailSide();renderMailList();});
  el.querySelectorAll('.mx').forEach(x=>x.onclick=async e=>{e.stopPropagation();
    if(!confirm('Kategorie „'+x.dataset.delcat+'“ löschen? (Die E-Mails bleiben natürlich erhalten.)'))return;
    await fetch('/api/mail/categories',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({remove:x.dataset.delcat})});
    if(mailFilter.cat===x.dataset.delcat)mailFilter.cat='';
    await mailState();mailMsgs.forEach(m=>{if(m.category===x.dataset.delcat)m.category='';});renderMailSide();renderMailList();});
  document.getElementById('catAdd').onclick=async()=>{const n=prompt('Name der neuen Kategorie:');if(!n||!n.trim())return;
    await fetch('/api/mail/categories',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({add:n.trim()})});
    await mailState();renderMailSide();};
  document.getElementById('mailNew').onclick=()=>renderCompose({});
  document.getElementById('mailCfg').onclick=renderMailSettings;
}

function renderMailList(){
  if(document.querySelector('#menu .mi.active')?.dataset.v!=='mail')return;
  mailPage='list';
  const wrap=document.createElement('div');wrap.id='mailwrap';
  let filt='';
  if(mailFilter.acc||mailFilter.cat)
    filt=`<span class="chip click" id="mailFiltOff" title="Filter aufheben">✕ ${esc(mailFilter.acc?accName(mailFilter.acc):'')}${mailFilter.acc&&mailFilter.cat?' · ':''}${esc(mailFilter.cat)}</span>`;
  let h=`<div class="mail-top"><h2>📧 E-MAILS</h2>${filt}<span style="flex:1"></span>`
    +`<button class="cal-tbtn" id="mailRefresh">⟲ AKTUALISIEREN</button></div>`
    +`<div class="mail-top" style="margin-bottom:10px">`
    +`<input class="mail-search" id="mailSearch" placeholder="🔎 Suchen … (Absender, Betreff)" value="${esc(mailFilter.q||'')}">`
    +`<span class="vhint" id="mailCount" style="margin:0;flex:0 0 auto"></span>`
    +`<button class="cal-tbtn" id="mailSelAll">☑ ALLE MARKIEREN</button>`
    +`<select class="msel" id="mailCatSel" title="Markierte einer Kategorie zuweisen" style="display:none">`
    +['<option value="__none__">🏷 KATEGORIE …</option>']
      .concat(mailCats.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`))
      .concat(['<option value="">✕ Kategorie entfernen</option>']).join('')
    +`</select>`
    +`<button class="cal-tbtn" id="mailDelSel" style="color:#ff5c5c;border-color:#5a1f1f;display:none"></button></div>`;
  Object.entries(mailErrors).forEach(([a,e])=>h+=`<div class="err" style="margin:6px 0">⚠ <b>${esc(a)}</b>: ${esc(e)}</div>`);
  wrap.innerHTML=h;
  const rows=document.createElement('div');rows.id='mlRows';wrap.appendChild(rows);
  chat.innerHTML='';chat.appendChild(wrap);chat.scrollTop=0;
  const updateBar=list=>{
    list=list||mailVisible();
    const db=document.getElementById('mailDelSel'),sa=document.getElementById('mailSelAll'),cs=document.getElementById('mailCatSel');
    if(!db||!sa)return;
    db.style.display=mailSel.size?'':'none';db.textContent=`🗑 LÖSCHEN (${mailSel.size})`;
    if(cs){cs.style.display=mailSel.size?'':'none';cs.value='__none__';}
    const all=list.length&&list.every(m=>mailSel.has(mailKey(m)));
    sa.textContent=all?'☒ KEINE MARKIEREN':'☑ ALLE MARKIEREN';
    const mc=document.getElementById('mailCount');
    if(mc)mc.textContent=list.length?list.length+' Mails':'';
  };
  const buildRow=m=>{
    const k=mailKey(m),on=mailSel.has(k);
    const r=document.createElement('div');r.className='ml-row'+(m.seen?'':' unread')+(on?' sel':'');
    r.innerHTML=`<input type="checkbox" class="ml-chk" title="markieren"${on?' checked':''}>`
      +`<span class="ml-acc" style="border-color:${accColor(m.account)};color:${accColor(m.account)}">${esc(accName(m.account))}</span>`
      +`<div class="ml-main"><span class="ml-from">${m.seen?'':'● '}${esc(m.from_name||m.from_addr||'?')}</span>`
      +`<span class="ml-sub">${esc(m.subject||'(kein Betreff)')}</span></div>`
      +(m.category?`<span class="ml-cat">${esc(m.category)}</span>`:'')
      +`<span class="ml-date">${fmtMailDate(m.ts)}</span><span class="ml-del" title="löschen (auch auf dem Server)">🗑</span>`;
    const cb=r.querySelector('.ml-chk');
    cb.onclick=e=>{e.stopPropagation();
      if(cb.checked)mailSel.add(k);else mailSel.delete(k);
      r.classList.toggle('sel',cb.checked);updateBar();};
    r.querySelector('.ml-del').onclick=e=>{e.stopPropagation();delMail(m);};
    r.onclick=()=>openMail(m);
    return r;
  };
  const CHUNK=400;   // DOM klein halten — tausende Zeilen auf einmal ruckeln
  const drawRows=()=>{
    const list=mailVisible();
    rows.innerHTML='';
    if(!list.length){const d=document.createElement('div');d.className='vhint';
      d.textContent=mailLoaded?('Keine E-Mails'+(mailFilter.acc||mailFilter.cat||mailFilter.q?' (Filter aktiv).':'.')):'Noch nichts geladen.';rows.appendChild(d);}
    let shown=0;
    const more=document.createElement('button');more.className='cal-tbtn';
    more.style.cssText='display:block;margin:12px auto';
    const addChunk=()=>{
      const frag=document.createDocumentFragment();
      const end=Math.min(shown+CHUNK,list.length);
      for(;shown<end;shown++)frag.appendChild(buildRow(list[shown]));
      rows.insertBefore(frag,more.parentNode===rows?more:null);
      if(shown>=list.length){if(more.parentNode)more.remove();}
      else{more.textContent=`▼ WEITERE ${Math.min(CHUNK,list.length-shown)} ANZEIGEN (${shown} von ${list.length})`;
        if(more.parentNode!==rows)rows.appendChild(more);}
    };
    more.onclick=addChunk;
    addChunk();
    updateBar(list);
  };
  drawRows();
  document.getElementById('mailRefresh').onclick=async()=>{renderMailLoading();await loadMailList(true);};
  const fo=document.getElementById('mailFiltOff');
  if(fo)fo.onclick=()=>{mailFilter.acc='';mailFilter.cat='';renderMailSide();renderMailList();};
  const si=document.getElementById('mailSearch');
  si.oninput=()=>{mailFilter.q=si.value;drawRows();};
  document.getElementById('mailSelAll').onclick=()=>{
    const list=mailVisible();
    const all=list.length&&list.every(m=>mailSel.has(mailKey(m)));
    list.forEach(m=>all?mailSel.delete(mailKey(m)):mailSel.add(mailKey(m)));
    drawRows();
  };
  document.getElementById('mailDelSel').onclick=delSelected;
  document.getElementById('mailCatSel').onchange=e=>{
    const v=e.target.value;
    if(v==='__none__')return;
    catSelected(v);
  };
}

async function catSelected(cat){
  const sel=mailMsgs.filter(m=>mailSel.has(mailKey(m)));
  const keys=sel.map(m=>m.key).filter(Boolean);
  if(!keys.length){renderMailList();return;}
  const label=cat?('„'+cat+'“'):'keiner Kategorie';
  const cs=document.getElementById('mailCatSel');
  if(cs){cs.disabled=true;}
  try{
    const r=await fetch('/api/mail/categorize_many',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({keys,category:cat})});
    if(r.status===404){
      // altes Backend ohne categorize_many → einzeln zuweisen
      for(const k of keys)
        await fetch('/api/mail/categorize',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({key:k,category:cat})});
    }else if(!r.ok){const j=await r.json().catch(()=>({}));throw new Error(j.error||('HTTP '+r.status));}
  }catch(e){alert('Kategorisieren fehlgeschlagen: '+(e.message||e));renderMailList();return;}
  sel.forEach(m=>m.category=cat);
  mailSel=new Set();          // Auswahl nach Zuweisung aufheben
  renderMailSide();renderMailList();
}

async function delSelected(){
  const items=mailMsgs.filter(m=>mailSel.has(mailKey(m)))
    .map(m=>({account:m.account,uid:m.uid,folder:m.folder||'INBOX'}));
  if(!items.length)return;
  if(!confirm(items.length+' E-Mail(s) wirklich löschen?\n\nSie werden auch auf den Mail-Servern in den Papierkorb verschoben.'))return;
  const db=document.getElementById('mailDelSel');
  if(db){db.disabled=true;db.textContent='🗑 LÖSCHE …';}
  let j={};
  try{
    const r=await fetch('/api/mail/delete_many',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({items})});
    if(r.status===404){
      // Server läuft noch mit altem Code (kennt delete_many nicht) → einzeln löschen
      j={errors:{}};
      for(let i=0;i<items.length;i++){
        if(db)db.textContent=`🗑 LÖSCHE … ${i+1}/${items.length}`;
        const r1=await fetch('/api/mail/delete',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify(items[i])});
        if(!r1.ok){const e1=await r1.json().catch(()=>({}));j.errors[items[i].account]=e1.error||('HTTP '+r1.status);}
      }
    }else{
      j=await r.json();if(!r.ok)throw new Error(j.error||('HTTP '+r.status));
    }
  }catch(e){alert('Löschen fehlgeschlagen: '+(e.message||e));renderMailList();return;}
  // Bei Teilfehlern bleiben die Mails der betroffenen Konten in Liste & Auswahl
  const gone=new Set(items.map(i=>i.account+'|'+i.uid));
  const failed=Object.keys(j.errors||{});
  failed.forEach(acc=>items.forEach(i=>{if(i.account===acc)gone.delete(i.account+'|'+i.uid);}));
  mailMsgs=mailMsgs.filter(m=>!gone.has(mailKey(m)));
  mailSel=new Set([...mailSel].filter(k=>!gone.has(k)));
  if(failed.length)alert('Teilweise fehlgeschlagen:\n'+failed.map(a=>a+': '+j.errors[a]).join('\n'));
  renderMailSide();renderMailList();
}

async function delMail(m){
  if(!confirm('E-Mail wirklich löschen?\n\n„'+(m.subject||'(kein Betreff)')+'“\n\nSie wird auch auf dem Mail-Server in den Papierkorb verschoben.'))return;
  try{
    const r=await fetch('/api/mail/delete',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({account:m.account,uid:m.uid,folder:m.folder||'INBOX'})});
    const j=await r.json();if(!r.ok)throw new Error(j.error||r.status);
  }catch(e){alert('Löschen fehlgeschlagen: '+(e.message||e));return;}
  mailMsgs=mailMsgs.filter(x=>!(x.account===m.account&&x.uid===m.uid));
  mailSel.delete(mailKey(m));
  renderMailSide();renderMailList();
}

async function openMail(m){
  mailPage='msg';
  chat.innerHTML='<div class="tool">⟲ Lade E-Mail …</div>';
  let d={};
  try{
    const r=await fetch(`/api/mail/msg?account=${encodeURIComponent(m.account)}&uid=${encodeURIComponent(m.uid)}&folder=${encodeURIComponent(m.folder||'INBOX')}`);
    d=await r.json();if(!r.ok)throw new Error(d.error||('HTTP '+r.status));
  }catch(e){chat.innerHTML='<div class="err" style="margin:20px">⚠ '+esc(e.message||''+e)+'</div>';return;}
  m.seen=true;renderMailSide();
  const wrap=document.createElement('div');wrap.id='mailwrap';
  const catOpts=['<option value="">— Kategorie —</option>']
    .concat(mailCats.map(c=>`<option${(m.category===c)?' selected':''}>${esc(c)}</option>`)).join('');
  wrap.innerHTML=`<div class="mail-top"><button class="backbtn" id="mBack">← Posteingang</button>`
    +`<button class="cal-tbtn" id="mReply">↩ ANTWORTEN</button>`
    +`<button class="cal-tbtn" id="mFwd">↪ WEITERLEITEN</button>`
    +`<select id="mCat" class="msel" title="Kategorie (nur lokal, nicht beim Anbieter)">${catOpts}</select>`
    +`<button class="cal-tbtn" id="mUnread" title="als ungelesen markieren">✉ UNGELESEN</button>`
    +`<button class="cal-tbtn" id="mDel" style="color:#ff5c5c;border-color:#5a1f1f" title="löschen (auch auf dem Server)">🗑</button></div>`
    +`<div class="mail-head"><div class="mh-sub">${esc(d.subject||'(kein Betreff)')}</div>`
    +`<div class="mh-line">Von: <b>${esc(d.from_name?d.from_name+' <'+d.from_addr+'>':d.from_addr||'?')}</b></div>`
    +`<div class="mh-line">An: ${esc(d.to||'—')}${d.cc?' · Cc: '+esc(d.cc):''}</div>`
    +`<div class="mh-line">${d.ts?esc(new Date(d.ts*1000).toLocaleString(I18N.locale)):''} · Konto: ${esc(m.account)}</div></div>`;
  if((d.attachments||[]).length){
    const ad=document.createElement('div');ad.className='mail-atts';
    ad.innerHTML=d.attachments.map(a=>`<a class="mail-att" href="/api/mail/att?account=${encodeURIComponent(m.account)}&uid=${encodeURIComponent(m.uid)}&folder=${encodeURIComponent(m.folder||'INBOX')}&idx=${a.idx}">📎 ${esc(a.name)} <span style="opacity:.6">(${fmtSize(a.size||0)})</span></a>`).join('');
    wrap.appendChild(ad);
  }
  if(d.html){
    const f=document.createElement('iframe');f.className='mail-frame';
    f.setAttribute('sandbox','allow-popups allow-popups-to-escape-sandbox');   // keine Skripte!
    f.srcdoc='<base target="_blank"><style>body{font-family:sans-serif;margin:12px;word-break:break-word}</style>'+d.html;
    wrap.appendChild(f);
  }else{
    const t=document.createElement('div');t.className='mail-text';t.textContent=d.text||'(kein Inhalt)';wrap.appendChild(t);
  }
  chat.innerHTML='';chat.appendChild(wrap);chat.scrollTop=0;
  document.getElementById('mBack').onclick=backToInbox;
  document.getElementById('mDel').onclick=()=>delMail(m);
  document.getElementById('mUnread').onclick=async()=>{
    await fetch('/api/mail/flag',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({account:m.account,uid:m.uid,folder:m.folder||'INBOX',seen:false})});
    m.seen=false;backToInbox();};
  document.getElementById('mCat').onchange=async e=>{
    const cat=e.target.value;
    await fetch('/api/mail/categorize',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({key:d.key,category:cat})});
    m.category=cat;renderMailSide();};
  const quote=(d.text||'').split('\n').map(l=>'> '+l).join('\n');
  const when=d.ts?new Date(d.ts*1000).toLocaleString(I18N.locale):'';
  document.getElementById('mReply').onclick=()=>renderCompose({
    from:m.account,to:d.from_addr,reply:d.message_id,
    subject:(/^re:/i.test(d.subject||'')?d.subject:'Re: '+(d.subject||'')),
    body:'\n\nAm '+when+' schrieb '+(d.from_name||d.from_addr)+':\n'+quote});
  document.getElementById('mFwd').onclick=()=>renderCompose({
    from:m.account,subject:(/^(fwd|wg):/i.test(d.subject||'')?d.subject:'Fwd: '+(d.subject||'')),
    body:'\n\n---------- Weitergeleitete Nachricht ----------\nVon: '+(d.from_name||'')+' <'+(d.from_addr||'')+'>\nDatum: '+when
      +'\nBetreff: '+(d.subject||'')+'\n\n'+(d.text||'(HTML-Mail — Inhalt bitte manuell übernehmen)')});
}

function renderCompose(pre){
  mailPage='compose';mailAtt=[];
  const froms=mailAccounts.filter(a=>a.configured);
  if(!froms.length){renderMailSettings();return;}
  const wrap=document.createElement('div');wrap.id='mailwrap';
  wrap.innerHTML=`<div class="mail-top"><button class="backbtn" id="mBack">← zurück</button><h2 style="font-size:16px">✉ ${pre.reply?'ANTWORT':'NEUE E-MAIL'}</h2></div>`
    +`<div class="mc-form">`
    +`<label>VON</label><select id="mcFrom" class="msel" style="max-width:320px">${froms.map(a=>`<option${pre.from===a.email?' selected':''}>${esc(a.email)}</option>`).join('')}</select>`
    +`<label>AN</label><input id="mcTo" value="${esc(pre.to||'')}" placeholder="empfaenger@beispiel.de (mehrere mit Komma)">`
    +`<label>CC</label><input id="mcCc" placeholder="(optional)">`
    +`<label>BETREFF</label><input id="mcSub" value="${esc(pre.subject||'')}">`
    +`<label>NACHRICHT</label><textarea id="mcBody" rows="12"></textarea>`
    +`<div id="mcAtts"></div>`
    +`<div style="display:flex;gap:8px;margin-top:10px;align-items:center">`
    +`<button class="cal-tbtn" id="mcAttach">📎 ANHANG</button>`
    +`<button class="lg-btn" id="mcSend" style="margin:0">➤ SENDEN</button>`
    +`<span id="mcMsg" class="vhint"></span></div></div>`;
  chat.innerHTML='';chat.appendChild(wrap);chat.scrollTop=0;
  document.getElementById('mcBody').value=pre.body||'';
  document.getElementById('mBack').onclick=backToInbox;
  const renderAtts=()=>{
    const el=document.getElementById('mcAtts');
    el.innerHTML=mailAtt.map((a,i)=>`<span class="mc-att">📎 ${esc(a.name)} <span style="opacity:.6">(${fmtSize(a.size||0)})</span><span class="x" data-i="${i}">✕</span></span>`).join('');
    el.querySelectorAll('.x').forEach(x=>x.onclick=()=>{mailAtt.splice(+x.dataset.i,1);renderAtts();});
  };
  document.getElementById('mcAttach').onclick=()=>{
    const fi=document.createElement('input');fi.type='file';fi.multiple=true;
    fi.onchange=async()=>{
      for(const f of fi.files){
        if(f.size>25*1024*1024){alert(f.name+' ist zu groß (max. 25 MB)');continue;}
        const fd=new FormData();fd.append('file',f);
        try{const j=await(await fetch('/api/mail/attach',{method:'POST',body:fd})).json();
          if(j.path)mailAtt.push(j);else alert(j.error||'Upload fehlgeschlagen');}catch{}
      }
      renderAtts();
    };
    fi.click();
  };
  document.getElementById('mcSend').onclick=async()=>{
    const msg=document.getElementById('mcMsg'),btn=document.getElementById('mcSend');
    const b={account:document.getElementById('mcFrom').value,
      to:document.getElementById('mcTo').value.trim(),
      cc:document.getElementById('mcCc').value.trim(),
      subject:document.getElementById('mcSub').value.trim(),
      body:document.getElementById('mcBody').value,
      attachments:mailAtt.map(a=>({path:a.path,name:a.name})),
      reply:pre.reply||''};
    if(!b.to){msg.textContent='⚠ Empfänger fehlt';document.getElementById('mcTo').focus();return;}
    btn.disabled=true;msg.textContent='⟲ sende …';
    try{
      const r=await fetch('/api/mail/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
      const j=await r.json();if(!r.ok)throw new Error(j.error||('HTTP '+r.status));
      msg.innerHTML='<span style="color:var(--green)">✅ gesendet!</span>';
      setTimeout(backToInbox,900);
    }catch(e){btn.disabled=false;msg.textContent='⚠ '+(e.message||e);}
  };
}

function renderMailSettings(){
  mailPage='settings';clearInterval(msPollTimer);
  const wrap=document.createElement('div');wrap.id='mailwrap';
  let h=`<div class="mail-top"><button class="backbtn" id="mBack">← Posteingang</button><h2 style="font-size:16px">⚙ E-MAIL-KONTEN</h2></div>`;
  mailAccounts.forEach(a=>{
    h+=`<div class="mc-acc"><div class="mca-head">`
      +`<span class="mdot" style="background:${a.configured?accColor(a.email):'#444'}"></span>`
      +`<b>${esc(a.email)}</b><span class="mca-prov">${esc(a.provider)}</span>`
      +`<span class="mca-st">${a.configured?'✓ eingerichtet':'— noch nicht eingerichtet'}</span>`
      +`<span class="mx" data-rm="${esc(a.email)}" title="Konto aus der Liste entfernen">✕</span></div>`
      +`<div class="vhint" style="padding:6px 0 0">${esc(a.hint||'')}</div>`;
    if(a.auth==='oauth'){
      h+=`<div class="mca-row"><button class="cal-tbtn" data-ms="${esc(a.email)}">🔑 MICROSOFT-LOGIN</button>`
        +`<button class="cal-tbtn" data-test="${esc(a.email)}">TEST</button>`
        +`<span id="st-${cssId(a.email)}" class="vhint" style="flex:1"></span></div>`;
    }else{
      h+=`<div class="mca-row"><input type="password" data-pw="${esc(a.email)}" autocomplete="new-password" `
        +`placeholder="${a.configured?'••••••••  (gespeichert — nur zum Ändern neu eingeben)':'Passwort / App-Passwort'}">`
        +`<button class="cal-tbtn" data-save="${esc(a.email)}">SPEICHERN</button>`
        +`<button class="cal-tbtn" data-test="${esc(a.email)}">TEST</button>`
        +`<span id="st-${cssId(a.email)}" class="vhint"></span></div>`;
    }
    h+=`</div>`;
  });
  h+=`<div class="mc-acc"><b style="color:var(--green)">＋ Konto hinzufügen</b>`
    +`<div class="mca-row"><input id="naEmail" placeholder="neue@adresse.de">`
    +`<input id="naPw" type="password" placeholder="Passwort (bei Outlook/Hotmail leer lassen)">`
    +`<button class="cal-tbtn" id="naAdd">HINZUFÜGEN</button><span id="naMsg" class="vhint"></span></div></div>`;
  h+=`<div class="vhint" style="margin-top:10px">🔒 Zugangsdaten liegen nur auf deinem Server in <code>.mail-accounts.json</code> (chmod 600) — sie tauchen nie im Browser auf.<br>`
    +`🏷 Kategorien existieren nur hier im Chat — auf den Mail-Servern ändert sich dadurch nichts. Gelöschte Mails wandern dagegen echt in den Server-Papierkorb.</div>`;
  wrap.innerHTML=h;chat.innerHTML='';chat.appendChild(wrap);chat.scrollTop=0;
  document.getElementById('mBack').onclick=backToInbox;
  const setSt=(em,txt,ok)=>{const s=document.getElementById('st-'+cssId(em));if(s){s.innerHTML=txt;s.style.color=ok?'var(--green)':'';}};
  wrap.querySelectorAll('[data-save]').forEach(b=>b.onclick=async()=>{
    const em=b.dataset.save;const pw=wrap.querySelector(`[data-pw="${CSS.escape(em)}"]`).value;
    if(!pw){setSt(em,'⚠ Passwort eingeben');return;}
    setSt(em,'⟲ speichere …');
    const r=await fetch('/api/mail/accounts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:em,password:pw})});
    const j=await r.json();
    if(!r.ok){setSt(em,'⚠ '+esc(j.error||r.status));return;}
    setSt(em,'✓ gespeichert — jetzt TEST klicken',true);await mailState();
  });
  wrap.querySelectorAll('[data-test]').forEach(b=>b.onclick=async()=>{
    const em=b.dataset.test;setSt(em,'⟲ teste Login + Posteingang …');
    try{
      const r=await fetch('/api/mail/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:em})});
      const j=await r.json();if(!r.ok)throw new Error(j.error||r.status);
      setSt(em,'✅ funktioniert — '+j.inbox+' Mails im Posteingang',true);mailLoaded=false;
    }catch(e){setSt(em,'⚠ '+esc(e.message||''+e));}
  });
  wrap.querySelectorAll('[data-ms]').forEach(b=>b.onclick=async()=>{
    const em=b.dataset.ms;setSt(em,'⟲ starte Microsoft-Login …');
    try{
      const r=await fetch('/api/mail/ms_login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:em})});
      const j=await r.json();if(!r.ok)throw new Error(j.error||r.status);
      setSt(em,`1. <a href="${esc(j.url)}" target="_blank" rel="noopener" style="color:var(--link)">${esc(j.url)}</a> öffnen &nbsp;·&nbsp; `
        +`2. Code <b style="color:var(--green);letter-spacing:2px">${esc(j.code)}</b> eingeben &nbsp;·&nbsp; ⟲ warte auf Bestätigung …`);
      clearInterval(msPollTimer);
      msPollTimer=setInterval(async()=>{
        try{
          const p=await(await fetch('/api/mail/ms_poll?email='+encodeURIComponent(em))).json();
          if(p.ok){clearInterval(msPollTimer);setSt(em,'✅ verbunden!',true);mailLoaded=false;await mailState();renderMailSettings();}
          else if(p.error){clearInterval(msPollTimer);setSt(em,'⚠ '+esc(p.error));}
        }catch{}
      },5000);
    }catch(e){setSt(em,'⚠ '+esc(e.message||''+e));}
  });
  wrap.querySelectorAll('[data-rm]').forEach(x=>x.onclick=async()=>{
    const em=x.dataset.rm;
    if(!confirm('Konto „'+em+'“ aus CONSTRUCT entfernen?\n\n(Das Postfach selbst bleibt natürlich bestehen — es wird nur hier nicht mehr abgerufen.)'))return;
    await fetch('/api/mail/accounts/'+encodeURIComponent(em),{method:'DELETE'});
    mailMsgs=mailMsgs.filter(m=>m.account!==em);await mailState();renderMailSide();renderMailSettings();
  });
  document.getElementById('naAdd').onclick=async()=>{
    const em=document.getElementById('naEmail').value.trim(),pw=document.getElementById('naPw').value;
    const msg=document.getElementById('naMsg');
    if(!em){msg.textContent='⚠ Adresse fehlt';return;}
    const r=await fetch('/api/mail/accounts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:em,password:pw})});
    const j=await r.json();
    if(!r.ok){msg.textContent='⚠ '+(j.error||r.status);return;}
    await mailState();renderMailSettings();
  };
}

