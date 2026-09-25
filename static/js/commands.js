// CONSTRUCT — Slash-Befehle
// ---------- Slash-Befehle (App-Ebene) ----------
function sysNote(html){const m=document.createElement('div');m.className='msg bot';m.innerHTML=`<div class="bubble helpbox">${html}</div>`;chat.appendChild(m);scroll();}
function showHelp(){sysNote('<b>⌨ Befehle</b><br>'
  +'<code>/new</code> — neue Session<br><code>/clear</code> — Ansicht leeren<br>'
  +'<code>/model [name]</code> — Modell wechseln (Claude, GPT, Gemini, DeepSeek, Ollama …)<br>'
  +'<code>/llm</code> — KI-Anbieter einrichten (API-Keys, Ollama-URL)<br>'
  +'<code>/mode [auto|plan|bypassPermissions|default]</code> — Modus wechseln<br>'
  +'<code>/folder [name]</code> — Arbeitsordner wechseln<br>'
  +'<code>/skills</code> — Skills-Ansicht<br>'
  +'<code>/login</code> — bei Claude anmelden (wenn der Token abgelaufen ist)<br>'
  +'<code>/help</code> — diese Liste<br><br>'
  +'<span style="opacity:.7">Hinweis: Claudes eingebaute Slash-Befehle funktionieren im Headless-Modus nicht — das hier sind eigene App-Befehle.</span>');}
function appCommand(raw){
  const parts=raw.slice(1).trim().split(/\s+/);const cmd=(parts[0]||'').toLowerCase();const arg=parts.slice(1).join(' ');
  if(cmd===''||cmd==='help')return showHelp();
  if(cmd==='new')return newSession();
  if(cmd==='clear'){const c=activeConv();if(c)c.pane.innerHTML='';return;}
  if(cmd==='skills')return setView('skills');
  if(cmd==='login')return (HAS_CLAUDE&&WEB_LOGIN)?openLogin():claudeSetupHint();
  if(cmd==='llm'||cmd==='anbieter')return openLlmCfg();
  if(cmd==='model'){if(!arg)return lbar.click();const a=arg.toLowerCase();
    const all=CLAUDE_MODELS.concat(extModels());
    const m=all.find(x=>(x.v||'standard').toLowerCase()===a||x.l.toLowerCase()===a)
      ||all.find(x=>x.v.toLowerCase().endsWith(':'+a))
      ||all.find(x=>x.l.toLowerCase().startsWith(a)||x.v.toLowerCase().includes(a));
    return m?(setModel(m.v),sysNote('Modell → <b>'+esc(m.l)+'</b>'+(m.prov?' <span style="opacity:.6">('+esc(m.d)+' · nur Chat)</span>':'')))
      :sysNote('Unbekanntes Modell. Claude: '+CLAUDE_MODELS.map(x=>'<code>'+(x.v||'standard')+'</code>').join(', ')
        +(extModels().length?'<br>Extern: '+extModels().slice(0,12).map(x=>'<code>'+esc(x.v)+'</code>').join(', ')+(extModels().length>12?' …':''):'<br>Externe Anbieter: erst über <code>/llm</code> einrichten.'));}
  if(cmd==='mode'){if(!arg)return mbar.click();const m=MODES.find(x=>x.v.toLowerCase()===arg.toLowerCase()||x.l.toLowerCase().includes(arg.toLowerCase()));
    return m?(setMode(m.v),sysNote('Mode → <b>'+esc(m.l)+'</b>')):sysNote('Unbekannter Mode. Verfügbar: '+MODES.map(x=>'<code>'+x.v+'</code>').join(', '));}
  if(cmd==='folder'){if(!arg)return fbar.click();const p=foldersCache.find(x=>baseName(x).toLowerCase()===arg.toLowerCase());
    return p?(setFolder(p),sysNote('Ordner → <b>'+esc(baseName(p))+'</b>')):sysNote('Ordner nicht gefunden: '+esc(arg));}
  sysNote('Unbekannter Befehl <code>/'+esc(cmd)+'</code> — <code>/help</code> zeigt alle.');
}

