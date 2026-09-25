// CONSTRUCT — Limits-Anzeige, Anmeldung
// ---------- HUD: Limits + Anmeldung ----------
function usageChip(el,label,u){
  if(!u||u.percent==null){el.textContent=label+' —';el.title='keine Daten';el.className='chip';return;}
  const p=Math.round(u.percent);
  el.className='chip'+(p>=85?' crit':(p>=60?' warn':''));
  el.innerHTML=`${label} <span class="bar"><i style="width:${Math.min(100,p)}%"></i></span><b>${p}%</b>`;
  if(u.resets_at){const d=new Date(u.resets_at);
    el.title=`Reset: ${d.toLocaleString(I18N.locale,{weekday:'short',hour:'2-digit',minute:'2-digit'})} Uhr`;}
}
async function loadHud(){
  const a=document.getElementById('auth');
  try{
    const st=await (await fetch('/api/auth/status')).json();
    HAS_CLAUDE=st.cli!==false;
    if(!HAS_CLAUDE){
      // Kein installiertes Claude Code ist kein Fehler, sondern ein Zustand:
      // wer nur über einen externen Anbieter chattet, soll hier keinen Alarm sehen.
      a.className='chip click';a.textContent='🔑 OHNE CLAUDE';
      a.title='Claude Code ist nicht installiert — der Chat läuft über den Anbieter '
        +'aus dem 🧠-Menü. Klicken für die Anleitung.';
    }
    else if(st.ok){a.className='chip click';a.innerHTML='🔑 <b>OK</b>';
      a.title='Angemeldet'+(st.web_token?' (Web-Login-Token)':st.env_token?' (Server-Token)':' (claudec-Login)')+' — klicken zum Neu-Anmelden';}
    else{a.className='chip click crit alert';a.textContent='🔑 LOGIN NÖTIG';a.title='Anmeldung abgelaufen — klicken zum Einloggen';}
  }catch{a.className='chip click crit';a.textContent='🔑 ?';}
  applyClaudeState();
  if(!HAS_CLAUDE){   // die Limit-Chips zeigen Anthropic-Kontingente — ohne Konto sinnlos
    ['use5','use7'].forEach(id=>{const e=document.getElementById(id);if(e)e.style.display='none';});
    return;
  }
  try{
    const u=await (await fetch('/api/usage')).json();
    const u5=document.getElementById('use5'),u7=document.getElementById('use7');
    if(u.limit_hit){const t=new Date(u.limit_hit*1000).toLocaleTimeString(I18N.locale,{hour:'2-digit',minute:'2-digit'});
      u5.className='chip crit alert';u5.textContent=`⛔ Limit — bis ${t}`;u5.title='Nutzungs-Limit erreicht, Reset um '+t+' Uhr';}
    else if(u.available)usageChip(u5,'5h',u.five_hour);
    else{u5.className='chip';u5.textContent='5h —';u5.title='Limits nicht abrufbar: '+(u.reason||'?');}
    if(u.available)usageChip(u7,'7T',u.seven_day);
    else{u7.className='chip';u7.textContent='7T —';u7.title='Limits nicht abrufbar: '+(u.reason||'?');}
  }catch{}
}
setInterval(loadHud,5*60*1000);

// ---------- Login-Dialog (claude setup-token über die Web-UI) ----------
const lmask=document.getElementById('loginmask'),lgMsg=document.getElementById('lgMsg');
function openLogin(){lmask.classList.add('show');lgMsg.textContent='';lgMsg.className='';
  document.getElementById('lg-step1').style.display='';document.getElementById('lg-step2').style.display='none';
  document.getElementById('lgStart').disabled=false;document.getElementById('lgCode').value='';}
function closeLogin(){lmask.classList.remove('show');}
// Der 🔑-Chip führt dahin, wo der Nutzer gerade steht: installieren, im
// Terminal anmelden (Windows kann den PTY-Login nicht) oder Web-Login.
function claudeSetupHint(){
  sysNote('<b>🔑 Claude Code</b><br>'
    +(HAS_CLAUDE?T('Claude Code ist installiert.'):
       T('Claude Code ist auf diesem Rechner <b>nicht installiert</b>. Ohne das läuft der '
       +'Chat über den Anbieter aus dem 🧠-Menü (ChatGPT, Gemini …) — das reicht '
       +'zum Reden, aber nicht für Dateien und Terminal.')+'<br><br>'
       +T('Nachinstallieren (braucht Node.js):')+'<br>'
       +'<code>npm install -g @anthropic-ai/claude-code</code><br><br>')
    +(WEB_LOGIN
       ?T('Anmelden geht danach direkt hier über diesen Knopf.')
       :T('Anmelden danach <b>einmal im Terminal</b>: <code>claude</code> eingeben und dem '
        +'Login folgen. CONSTRUCT erkennt die Anmeldung anschließend von selbst — '
        +'der Login-Dialog in der Oberfläche braucht ein Pseudo-Terminal, das es '
        +'unter Windows nicht gibt.'))
    +'<br><br><span style="opacity:.7">Dafür braucht es ein Anthropic-Konto (Abo oder API-Guthaben).</span>');
}
document.getElementById('auth').onclick=()=>{
  if(HAS_CLAUDE&&WEB_LOGIN)openLogin(); else claudeSetupHint();
};
document.getElementById('lgClose').onclick=closeLogin;
lmask.addEventListener('click',e=>{if(e.target===lmask)closeLogin();});
document.getElementById('lgStart').onclick=async()=>{
  const btn=document.getElementById('lgStart');btn.disabled=true;
  lgMsg.className='';lgMsg.textContent='⟲ starte Login … (kann ein paar Sekunden dauern)';
  try{
    const r=await fetch('/api/auth/login',{method:'POST'});const j=await r.json();
    if(!r.ok||!j.url)throw new Error(j.error||('HTTP '+r.status));
    const a=document.getElementById('lgUrl');a.href=j.url;a.textContent=j.url;
    document.getElementById('lg-step1').style.display='none';
    document.getElementById('lg-step2').style.display='';
    lgMsg.textContent='';document.getElementById('lgCode').focus();
  }catch(e){lgMsg.className='bad';lgMsg.textContent='⚠ '+e.message;btn.disabled=false;}
};
async function submitLoginCode(){
  const code=document.getElementById('lgCode').value.trim();if(!code)return;
  const btn=document.getElementById('lgSend');btn.disabled=true;
  lgMsg.className='';lgMsg.textContent='⟲ prüfe Code …';
  try{
    const r=await fetch('/api/auth/code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})});
    const j=await r.json();
    if(!r.ok||!j.ok)throw new Error(j.error||('HTTP '+r.status));
    lgMsg.className='ok';lgMsg.textContent='✅ Angemeldet! CONSTRUCT läuft jetzt mit einem langlebigen Token — kein Terminal-Login mehr nötig.';
    document.getElementById('lg-step2').style.display='none';
    loadHud();setTimeout(closeLogin,2500);
  }catch(e){lgMsg.className='bad';lgMsg.textContent='⚠ '+e.message;btn.disabled=false;}
}
document.getElementById('lgSend').onclick=submitLoginCode;
document.getElementById('lgCode').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();submitLoginCode();}});

