// CONSTRUCT — Einstellungen: Engines, Updates, Vorlesen, Telegram, Charakter, Bilder
// ---------- Einstellungen ----------
// Serverseitig gespeichert (settings.json), nicht im localStorage: die App
// wird mal aus dem Fenster, mal aus dem Browser bedient, und zwei Browser
// waeren sonst zwei verschiedene Wahrheiten.
const TILES=[
  {k:'kalender', i:'📅', t:'Kalender',  d:'Termine eintragen und ansehen. Braucht nichts weiter.'},
  {k:'skills',   i:'⚡', t:'Skills',    d:'Zeigt die Skills aus deinen Projekten. Nur mit Claude Code sinnvoll.'},
  {k:'mail',     i:'📧', t:'E-Mails',   d:'Postfach über IMAP/SMTP. Zugangsdaten liegen lokal.'},
  {k:'mcp',      i:'🔌', t:'MCP',       d:'Zeigt konfigurierte MCP-Server. Nur mit Claude Code sinnvoll.'},
];
let setSaveTimer=null;
async function setSave(patch){
  Object.assign(SETTINGS.tiles, patch.tiles||{});
  Object.assign(SETTINGS.background, patch.background||{});
  Object.assign(SETTINGS.names=SETTINGS.names||{}, patch.names||{});
  Object.assign(SETTINGS.updates=SETTINGS.updates||{}, patch.updates||{});
  const tp=patch.tts||{};SETTINGS.tts=SETTINGS.tts||{};
  for(const k in tp)SETTINGS.tts[k]=(tp[k]&&typeof tp[k]==='object')?{...SETTINGS.tts[k],...tp[k]}:tp[k];
  const note=document.getElementById('setSaved');
  try{
    const r=await fetch('/api/settings',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(patch)});
    const fresh=await r.json();
    SETTINGS.tiles=fresh.tiles; SETTINGS.background=fresh.background;
    SETTINGS.names=fresh.names; SETTINGS.updates=fresh.updates; SETTINGS.tts=fresh.tts;
    if(note){note.textContent='✓ gespeichert';note.classList.add('on');
      clearTimeout(setSaveTimer);setSaveTimer=setTimeout(()=>note.classList.remove('on'),1600);}
  }catch{
    if(note){note.textContent='⚠ nicht gespeichert';note.classList.add('on');}
  }
}
function applyTiles(){
  const r=document.documentElement;
  TILES.forEach(x=>r.classList.toggle('no-'+x.k, SETTINGS.tiles[x.k]===false));
  // Steht man gerade in einer Ansicht, die man soeben abgeschaltet hat,
  // waere der Bildschirm sonst leer ohne erkennbaren Grund.
  const cur=document.querySelector('.mi.active')?.dataset.v;
  if(cur && SETTINGS.tiles[cur]===false) setView('einstellungen');
}
// „🧠 MODELLE & ANBIETER“ → „Modelle & Anbieter“
const navLabel=t=>t.replace(/^[^\p{L}]+/u,'').trim().toLowerCase().replace(/(^|[\s-])\p{L}/gu,m=>m.toUpperCase());
function renderSettings(){
  const w=document.createElement('div');w.className='set-wrap';

  // --- 1) Kacheln ---
  const tileRows=TILES.map(x=>`<div class="set-row"><label>
      <input type="checkbox" data-tile="${x.k}" ${SETTINGS.tiles[x.k]!==false?'checked':''}>
      <span><span class="set-t">${x.i} ${esc(x.t)}</span>
      <span class="set-d">${esc(x.d)}</span></span></label></div>`).join('');

  // --- 2) Modelle: drei Wege, die man nicht verwechseln darf ---
  const claudeTag = HAS_CLAUDE
    ? '<span class="set-tag ok">INSTALLIERT</span>'
    : '<span class="set-tag warn">NICHT INSTALLIERT</span>';

  w.innerHTML=`
  <div class="set-sec"><h3>🌐 SPRACHE</h3><div class="set-body">
    <div class="set-row"><span style="flex:1">
      <span class="set-d">Sprache der Oberfläche und des Assistenten. Die Seite lädt danach neu.</span>
      <span style="display:block;margin-top:9px">
        <select id="setLang" class="set-btn" style="padding:7px 9px" translate="no">
          <option value="en">English</option>
          <option value="de">Deutsch</option>
        </select>
      </span></span></div>
  </div></div>

  <div class="set-sec"><h3>⚙ KACHELN</h3><div class="set-body">
    <div class="set-row"><label style="cursor:default">
      <input type="checkbox" checked disabled>
      <span><span class="set-t">💬 Chats</span>
      <span class="set-d">Der Hauptzweck der Oberfläche — lässt sich nicht abschalten.</span></span></label>
      <span class="set-fixed">FEST</span></div>
    ${tileRows}
  </div></div>

  <div class="set-sec"><h3>🧠 MODELLE &amp; ANBIETER</h3><div class="set-body">
    <div class="set-row"><span style="flex:1">
      <span class="set-head"><h4>1 · Claude Code</h4>${claudeTag}</span>
      <span class="set-d">Läuft über dein <b>Anthropic-Abo</b> (OAuth) oder einen API-Key.
      Der einzige Weg mit <b>echtem Zugriff</b> auf Dateien und Terminal — hier greifen
      📂 Ordner und 🛡 Modus. Ein Schlüssel von einem anderen Anbieter funktioniert
      dafür nicht.</span>
      <span style="display:block;margin-top:9px">
        <button class="set-btn" id="setClaude">${HAS_CLAUDE?'🔑 Anmeldung':'📋 Anleitung'}</button>
        <button class="set-btn" id="cInstall" style="display:none">Installieren</button>
        <span class="set-saved" id="cNote"></span>
      </span>
      <pre id="cLog" style="display:none;margin-top:9px;max-height:170px;overflow:auto;
        font-size:11px;line-height:1.4;background:var(--shade);padding:8px;
        border:1px solid var(--green-faint);border-radius:3px;white-space:pre-wrap"></pre>
      </span></div>

    <div class="set-row"><span style="flex:1">
      <span class="set-head"><h4>2 · Fremde Anbieter</h4><span class="set-tag">ÜBER HERMES</span></span>
      <span class="set-d">ChatGPT, Gemini, DeepSeek, lokale Ollama-Modelle oder jede
      OpenAI-kompatible API. Diese Modelle laufen über <b>Hermes</b> (Punkt 3) und können
      damit ebenfalls Dateien und Terminal. Schlüssel bleiben lokal in
      <code>.llm-config.json</code>.<br>
      Angezeigt werden nur Modelle, die <b>Werkzeug-Aufrufe beherrschen</b> — ohne die
      würde der Agent seine Befehle als Fließtext ausgeben, statt sie auszuführen.</span>
      <span style="display:block;margin-top:9px">
        <button class="set-btn" id="setLlm">⚙ Anbieter einrichten…</button>
      </span></span></div>

    <div class="set-row"><span style="flex:1">
      <span class="set-head"><h4>3 · Hermes</h4><span id="hTag" class="set-tag">…</span></span>
      <span class="set-d">Fährt die <b>Chat-Anbieter von oben mit Werkzeugen</b> — Dateien
      und Terminal ohne Anthropic-Konto, auch mit lokalen Modellen über Ollama.
      Ohne Hermes lassen sich fremde Modelle nicht nutzen.</span>
      <span style="display:block;margin-top:9px">
        <button class="set-btn" id="hInstall">Installieren</button>
        <span class="set-saved" id="hNote"></span>
      </span>
      <pre id="hLog" style="display:none;margin-top:9px;max-height:170px;overflow:auto;
        font-size:11px;line-height:1.4;background:var(--shade);padding:8px;
        border:1px solid var(--green-faint);border-radius:3px;white-space:pre-wrap"></pre>
      </span></div>
  </div></div>

  <div class="set-sec"><h3>📧 E-MAIL-KONTEN</h3><div class="set-body">
    <div class="set-row"><span style="flex:1">
      <span class="set-d">Postfächer anlegen, Passwort ändern, Verbindung testen — die Konten
      werden in der E-Mail-Ansicht verwaltet (dort auch links unten über „Konten verwalten“).</span>
      <span style="display:block;margin-top:9px">
        <button class="set-btn" id="setMail" ${SETTINGS.tiles.mail===false?'disabled title="Kachel E-Mails ist abgeschaltet"':''}>⚙ Konten verwalten…</button>
      </span></span></div>
  </div></div>

  <div class="set-sec"><h3>🔊 VORLESEN</h3><div class="set-body">
    <div class="set-d" style="margin-bottom:10px">Antworten per <b>Gemini TTS</b> vorlesen lassen —
      der 🔊 neben dem Namen über jeder Antwort. Braucht einen Gemini-Key
      (kostenlos auf aistudio.google.com/apikey) — derselbe wie für den Gemini-Chat.</div>
    <div style="margin-bottom:10px"><button class="set-btn" id="ttsKey">🔑 Gemini-Key eintragen…</button></div>
    <div class="set-row"><label>
      <input type="checkbox" id="ttsAuto" ${SETTINGS.tts?.auto?'checked':''}>
      <span><span class="set-t">Antworten automatisch vorlesen</span>
      <span class="set-d">Jede fertige Antwort im offenen Chat wird sofort gesprochen.</span></span></label></div>
    <div class="set-row"><span style="flex:1">
      <span class="set-t">Modell</span>
      <span class="set-d"><b>Flash-Lite</b> ist schneller und schont das Kontingent,
      <b>Flash</b> klingt ausdrucksstärker.</span>
      <span style="display:block;margin-top:9px">
        <select id="ttsModel" class="set-btn" style="padding:7px 9px">
          <option value="gemini-3.8-flash-lite-tts">Gemini 3.8 Flash-Lite TTS</option>
          <option value="gemini-3.8-flash-tts">Gemini 3.8 Flash TTS</option>
        </select></span></span></div>
    <div class="set-row"><span style="flex:1">
      <span class="set-t">Stimme</span>
      <span class="set-d" id="ttsVoiceInfo">Stimmen aus dem Gemini-Katalog — passend zur Sprache der Oberfläche.</span>
      <span style="display:block;margin-top:9px;display:flex;gap:9px;flex-wrap:wrap;align-items:center">
        <select id="ttsVoice" class="set-btn" style="padding:7px 9px;max-width:100%"></select>
        <button class="set-btn" id="ttsTry">▶ Hörprobe</button>
        <span class="set-saved" id="ttsNote"></span>
      </span></span></div>
    <div class="set-row"><span style="flex:1">
      <span class="set-t">Sprechweise</span>
      <span class="set-d">Optionale Regieanweisung, z. B. „locker und freundlich, etwas zügig“.</span>
      <input id="ttsStyle" class="set-btn" style="display:block;margin-top:9px;width:100%;box-sizing:border-box;text-align:left;letter-spacing:0"
        maxlength="200" placeholder="leer = natürlich"></span></div>
  </div></div>

  <div class="set-sec"><h3>✈ TELEGRAM</h3><div class="set-body">
    <div class="set-d" style="margin-bottom:10px">${T('Sprich mit {a} von unterwegs — per Text oder Sprachnachricht. Dazu Erinnerungen an Termine, eine Meldung, wenn ein langer Lauf fertig ist, und geplante Aufgaben aus dem Kalender. Läuft nur, solange CONSTRUCT läuft.',{a:esc(ASSISTANT)})}</div>
    <div class="set-row"><label>
      <input type="checkbox" id="tgOn">
      <span><span class="set-t">Telegram-Bot aktiv</span>
      <span class="set-d" id="tgStatus">…</span></span></label></div>
    <div class="set-row"><span style="flex:1">
      <span class="set-t">Bot-Token</span>
      <span class="set-d">In Telegram bei <b>@BotFather</b>: <code>/newbot</code> → Namen vergeben → Token kopieren.</span>
      <span style="display:block;margin-top:8px">
        <input class="set-in" id="tgToken" type="password" autocomplete="off" spellcheck="false" style="width:100%;max-width:420px">
      </span></span></div>
    <div class="set-row"><span style="flex:1">
      <span class="set-t">Deine Chat-ID</span>
      <span class="set-d">Nur diese ID darf mit dem Bot reden. Unbekannt? Bot aktivieren und ihm irgendetwas schreiben — dann erscheint sie hier.</span>
      <span style="display:block;margin-top:8px">
        <input class="set-in" id="tgChat" inputmode="numeric" spellcheck="false" style="width:180px">
        <span id="tgCand"></span>
      </span></span></div>
    <div class="set-row"><span style="flex:1">
      <span class="set-t">Modell und Modus</span>
      <span class="set-d">Womit der Bot antwortet. „Plan“ liest nur und ändert nichts — die sichere Wahl, wenn das Handy mal in fremde Hände gerät.</span>
      <span style="display:block;margin-top:8px">
        <select id="tgModel" class="set-btn" style="padding:7px 9px"></select>
        <select id="tgMode" class="set-btn" style="padding:7px 9px">
          <option value="bypassPermissions">⚡ Auto</option>
          <option value="plan">📋 Plan</option>
        </select>
      </span></span></div>
    <div class="set-row"><label>
      <input type="checkbox" id="tgRem">
      <span><span class="set-t">Erinnerungen an Termine</span>
      <span class="set-d">Morgens eine Übersicht über den Tag, vor terminierten Einträgen ein Ping.</span></span></label>
      <span style="display:block;margin:8px 0 0 30px">
        <select id="tgHour" class="set-btn" style="padding:7px 9px"></select>
        <select id="tgLead" class="set-btn" style="padding:7px 9px">
          <option value="0">kein Ping vorher</option>
          <option value="10">10 Min vorher</option>
          <option value="15">15 Min vorher</option>
          <option value="30">30 Min vorher</option>
          <option value="60">60 Min vorher</option>
        </select>
      </span></div>
    <div class="set-row"><label>
      <input type="checkbox" id="tgNotify">
      <span><span class="set-t">Melden, wenn ein langer Lauf fertig ist</span>
      <span class="set-d">Nur wenn gerade niemand im Fenster zuschaut.</span></span></label></div>
    <div style="margin-top:9px;display:flex;gap:9px;align-items:center;flex-wrap:wrap">
      <button class="set-btn" id="tgSave">Speichern</button>
      <button class="set-btn" id="tgTest">Test-Nachricht</button>
      <span class="set-saved" id="tgNote"></span>
    </div>
  </div></div>

  <div class="set-sec"><h3>🔄 AKTUALISIERUNG</h3><div class="set-body">
    <div class="set-row"><label>
      <input type="checkbox" id="updAuto" ${SETTINGS.updates?.auto!==false?'checked':''}>
      <span><span class="set-t">Beim Start nach Updates suchen</span>
      <span class="set-d">Holt neue Fassungen von <b>Claude Code</b> und <b>Hermes</b>, sobald
      CONSTRUCT hochfährt — im Hintergrund, der Chat bleibt bedienbar. Ohne das bleiben beide
      auf dem Stand von damals: ihre eigene Selbstaktualisierung ist ab Werk abgeschaltet.</span></span></label></div>

    <div class="set-row"><span style="flex:1">
      <span class="set-t">Wie oft höchstens</span>
      <span class="set-d">Verhindert, dass fünf Neustarts an einem Nachmittag fünf Netzrunden auslösen.</span>
      <span style="display:block;margin-top:9px">
        <select id="updIv" class="set-btn" style="padding:7px 9px">
          <option value="0">bei jedem Start</option>
          <option value="6">höchstens alle 6 Stunden</option>
          <option value="24">höchstens einmal am Tag</option>
          <option value="168">höchstens einmal die Woche</option>
        </select>
        <button class="set-btn" id="updNow">Jetzt suchen</button>
        <span class="set-saved" id="updNote"></span>
      </span>
      <pre id="updLog" style="display:none;margin-top:9px;max-height:170px;overflow:auto;
        font-size:11px;line-height:1.4;background:var(--shade);padding:8px;
        border:1px solid var(--green-faint);border-radius:3px;white-space:pre-wrap"></pre>
      </span></div>
  </div></div>

  <div class="set-sec"><h3>🙋 NAMEN</h3><div class="set-body">
    <div class="set-row"><span style="flex:1">
      <span class="set-t">Wie soll ich dich nennen?</span>
      <span class="set-d">Steht im Chat über deinen Nachrichten und wird den Modellen
      mitgegeben. Leer lassen geht auch — dann bleibt es unpersönlich.</span>
      <span style="display:block;margin-top:8px">
        <input class="set-in" id="setUser" maxlength="40" placeholder="dein Name">
      </span></span></div>
    <div class="set-row"><span style="flex:1">
      <span class="set-t">Wie heißt der Assistent?</span>
      <span class="set-d">CONSTRUCT ist der Ort, er ist die Person darin. Wer ihn
      umbenennt, sollte auch <code>SOUL.md</code> anpassen — dort steht sein Charakter.</span>
      <span style="display:block;margin-top:8px">
        <input class="set-in" id="setAsst" maxlength="40" placeholder="Cody">
      </span></span></div>
    <div class="set-row"><span style="flex:1">
      <span class="set-t">Bilder</span>
      <span class="set-d">Erscheinen im Chat neben den Nachrichten. Ohne eigenes Bild
      steht bei dir der Anfangsbuchstabe.</span>
      <span class="av-pick">
        <span class="av-prev" id="avU"></span>
        <button class="set-btn" id="avUPick">Deins wählen…</button>
        <button class="set-btn" id="avUClear">✕</button>
      </span>
      <span class="av-pick">
        <span class="av-prev" id="avA"></span>
        <button class="set-btn" id="avAPick">Seins wählen…</button>
        <button class="set-btn" id="avAClear">✕</button>
      </span></span></div>
    <div class="set-d" style="margin-top:6px">Namen wirken nach dem Neuladen der Seite.</div>
  </div></div>

  <div class="set-sec"><h3>📜 CHARAKTER</h3><div class="set-body">
    <div class="set-d" style="margin-bottom:10px">Beides wird bei <b>jeder</b> Nachricht
    mitgelesen — auch von fremden Modellen. <b>Charakter</b> beschreibt, wer der Assistent
    ist; <b>Über dich</b>, was er über dich wissen soll. Reiner Text, Markdown erlaubt.</div>
    <div class="set-tabs">
      <button class="set-tab on" data-persona="soul">Charakter (SOUL.md)</button>
      <button class="set-tab" data-persona="user">Über dich (USER.md)</button>
    </div>
    <textarea class="set-area" id="setSoul" spellcheck="false"
      placeholder="wird geladen…"></textarea>
    <div style="margin-top:9px;display:flex;gap:9px;align-items:center">
      <button class="set-btn" id="soulSave">Speichern</button>
      <span class="set-saved" id="soulNote"></span>
    </div>
  </div></div>

  <div class="set-sec"><h3>🎨 FARBWELT</h3><div class="set-body">
    <div class="th-grid">${THEMES.map(t=>`
      <div class="th${(SETTINGS.theme||'matrix')===t.k?' on':''}" data-theme-pick="${t.k}">
        <span class="th-sw">
          <i style="background:${THEME_SWATCH[t.k][0]}"></i>
          <i style="background:${THEME_SWATCH[t.k][1]}"></i>
          <i style="background:${THEME_SWATCH[t.k][2]}"></i>
        </span>
        <span class="th-n">${esc(t.n)}${(SETTINGS.theme||'matrix')===t.k?'<b>AKTIV</b>':''}</span>
        <span class="th-d">${esc(t.d)}</span>
      </div>`).join('')}</div>
  </div></div>

  <div class="set-sec"><h3>🖼 HINTERGRUND</h3><div class="set-body">
    <div class="set-row"><label><input type="radio" name="bgm" value="matrix">
      <span><span class="set-t">Matrix-Regen</span>
      <span class="set-d">Die Vorgabe. Kostet etwas Rechenleistung.</span></span></label></div>
    <div class="set-row"><label><input type="radio" name="bgm" value="image">
      <span><span class="set-t">Eigenes Bild</span>
      <span class="set-d">Ersetzt den Regen. Wird abgedunkelt, damit die Schrift lesbar bleibt.</span></span></label></div>
    <div class="set-row"><label><input type="radio" name="bgm" value="plain">
      <span><span class="set-t">Schlicht dunkel</span>
      <span class="set-d">Nichts im Hintergrund — am sparsamsten.</span></span></label></div>
    <div id="bgOpts" style="margin-top:12px">
      <button class="set-btn" id="bgPick">🖼 Bild wählen…</button>
      <button class="set-btn" id="bgClear">✕ Bild entfernen</button>
      <div style="margin-top:12px">
        <label class="set-d" for="bgDim">Abdunkeln: <b id="bgDimV"></b></label>
        <input type="range" min="0" max="95" id="bgDim" class="set-slider">
      </div>
      <div class="set-prev" id="bgPrev"></div>
    </div>
    <input type="file" id="bgFile" accept="image/*" style="display:none">
  </div></div>

  <div style="text-align:right"><span class="set-saved" id="setSaved"></span></div>`;

  chat.innerHTML='';chat.appendChild(w);

  const langSel=document.getElementById('setLang');
  langSel.value=I18N.lang;
  // Neu laden statt live umschalten: Texte stecken auch in schon gebauten
  // Ansichten und im Server-Prompt — ein frischer Start ist die ehrliche Lösung.
  langSel.onchange=async()=>{await setSave({lang:langSel.value});location.reload();};
  w.querySelectorAll('input[data-tile]').forEach(cb=>cb.onchange=()=>{
    setSave({tiles:{[cb.dataset.tile]:cb.checked}}).then(applyTiles);
  });
  // Navigation links aus den tatsächlichen Abschnitten bauen — eine feste
  // Liste lief auseinander, sobald ein Abschnitt dazukam.
  const side=document.getElementById('setnav');
  if(side){
    const secs=[...w.querySelectorAll('.set-sec')];
    side.innerHTML=secs.map((sec,i)=>`<div class="sess" data-i="${i}"><span class="t">`
      +esc(navLabel(sec.querySelector('h3')?.textContent||''))+`</span></div>`).join('');
    side.querySelectorAll('.sess').forEach(n=>n.onclick=()=>{
      side.querySelectorAll('.sess').forEach(x=>x.classList.toggle('active',x===n));
      secs[+n.dataset.i].scrollIntoView({behavior:'smooth',block:'start'});
    });
  }
  setupEngines(w);
  setupUpdates(w);
  setupTTS(w);
  setupTelegram(w);
  setupPersona(w);
  setupAvatars(w);
  const nm=SETTINGS.names||{};
  const uEl=document.getElementById('setUser'), aEl=document.getElementById('setAsst');
  uEl.value=nm.user||''; aEl.value=nm.assistant||'';
  // Beim Verlassen speichern, nicht bei jedem Tastendruck — sonst schreibt
  // jeder Buchstabe eine Datei.
  uEl.onchange=()=>setSave({names:{user:uEl.value}});
  aEl.onchange=()=>setSave({names:{assistant:aEl.value}});

  w.querySelectorAll('[data-theme-pick]').forEach(el=>el.onclick=()=>{
    SETTINGS.theme=el.dataset.themePick;
    applyTheme(); setSave({theme:SETTINGS.theme});
    w.querySelectorAll('[data-theme-pick]').forEach(o=>{
      const on=o.dataset.themePick===SETTINGS.theme;
      o.classList.toggle('on',on);
      const n=o.querySelector('.th-n b'); if(!on&&n)n.remove();
      if(on&&!o.querySelector('.th-n b'))
        o.querySelector('.th-n').insertAdjacentHTML('beforeend','<b>AKTIV</b>');
    });
  });
  document.getElementById('setLlm').onclick=openLlmCfg;
  document.getElementById('setMail').onclick=()=>{mailWantSettings=true;setView('mail');};
  document.getElementById('setClaude').onclick=()=>{
    if(HAS_CLAUDE&&WEB_LOGIN)openLogin(); else {setView('sessions');claudeSetupHint();}
  };

  const bg=SETTINGS.background;
  w.querySelectorAll('input[name=bgm]').forEach(r=>{
    r.checked = (bg.mode||'matrix')===r.value;
    r.onchange=()=>{ if(r.checked) bgApply({mode:r.value}); };
  });
  const dim=document.getElementById('bgDim');
  dim.value = bg.dim==null?60:bg.dim;
  const showDim=()=>{document.getElementById('bgDimV').textContent=dim.value+' %';
    document.getElementById('bgPrev').style.setProperty('--x',dim.value);};
  showDim();
  dim.oninput=()=>{showDim();
    SETTINGS.background.dim=+dim.value;applyBackground();bgPreview();};
  dim.onchange=()=>bgApply({dim:+dim.value});
  document.getElementById('bgPick').onclick=()=>document.getElementById('bgFile').click();
  document.getElementById('bgClear').onclick=()=>bgApply({image:'',mode:'matrix'});
  document.getElementById('bgFile').onchange=async e=>{
    const f=e.target.files&&e.target.files[0]; if(!f)return;
    const fd=new FormData(); fd.append('file',f);
    try{
      const r=await fetch('/api/upload',{method:'POST',body:fd});
      const j=await r.json();
      if(j.url)bgApply({image:j.url,mode:'image'}); else alert(j.error||'Upload fehlgeschlagen');
    }catch{alert('Upload fehlgeschlagen');}
    e.target.value='';
  };
  bgPreview();
}
// ---------- Werkzeug-Maschinen einrichten ----------
// Zwei Wege zu Werkzeugen: Claude Code (Anthropic-Konto) und Hermes (alles
// andere). Beide lassen sich hier installieren, statt den Nutzer ins Terminal
// zu schicken — dasselbe Muster wie beim Ollama-Download: anstossen, pollen.
let engInfo=null, engTimer=null;
async function setupEngines(w){
  const paint=async()=>{
    try{engInfo=await(await fetch('/api/engines')).json();}catch{return;}
    const h=engInfo.hermes||{}, c=engInfo.claude||{};
    const tag=w.querySelector('#hTag'), btn=w.querySelector('#hInstall');
    if(tag){
      tag.className='set-tag'+(h.installed?' ok':' warn');
      tag.textContent=h.installed?'INSTALLIERT':'NICHT INSTALLIERT';
      tag.title=h.installed?(h.version||'')+'\n'+(h.home||''):'';
    }
    if(btn){
      btn.style.display=h.installed?'none':'';
      if(!h.posix){btn.disabled=true;btn.textContent='nur Linux / macOS';}
    }
    const cb=w.querySelector('#cInstall');
    if(cb){
      cb.style.display=c.installed?'none':'';
      if(!c.npm){cb.disabled=true;cb.textContent='braucht Node.js (nodejs.org)';}
    }
  };
  await paint();

  // Ein Installationslauf, zwei Maschinen — derselbe Ablauf, andere Route.
  const drive=(which,btnId,logId,noteId)=>{
    const btn=w.querySelector('#'+btnId), log=w.querySelector('#'+logId),
          note=w.querySelector('#'+noteId);
    if(!btn)return;
    btn.onclick=async()=>{
      btn.disabled=true;btn.textContent='läuft…';
      log.style.display='';log.textContent='';
      note.textContent='';note.classList.add('on');
      try{await fetch(`/api/engines/${which}/install`,{method:'POST'});}catch{}
      clearInterval(engTimer);
      engTimer=setInterval(async()=>{
        let st;try{st=await(await fetch(`/api/engines/${which}/install`)).json();}catch{return;}
        log.textContent=(st.log||[]).join('\n');log.scrollTop=log.scrollHeight;
        if(st.done){
          clearInterval(engTimer);
          btn.disabled=false;btn.textContent='Installieren';
          note.textContent=st.error?('⚠ '+st.error):'✓ fertig';
          await paint();
          if(!st.error&&which==='claude'){HAS_CLAUDE=true;applyClaudeState();}
          // Modell-Liste neu holen: mit Hermes stehen jetzt andere Wege offen.
          loadProviders(true);
        }
      },1200);
    };
  };
  drive('hermes','hInstall','hLog','hNote');
  drive('claude','cInstall','cLog','cNote');
}

// ---------- Aktualisierung (Einstellungen) ----------
// Dieselbe Quelle wie die Karte unten rechts, nur ausfuehrlicher: hier steht
// das ganze Protokoll, und der Lauf laesst sich von Hand anstossen.
let updSetTimer=null;
// ---------- Telegram ----------
// Der Token geht nur einmal zum Server und kommt nie zurück: das Feld zeigt
// danach nur "gespeichert". Der Status wird abgefragt, solange die Seite offen
// ist — so taucht die Chat-ID auf, sobald man dem Bot schreibt.
let tgTimer=null;
function setupTelegram(w){
  const $=id=>w.querySelector('#'+id);
  const on=$('tgOn'),tok=$('tgToken'),chat=$('tgChat'),model=$('tgModel'),mode=$('tgMode'),
        rem=$('tgRem'),hour=$('tgHour'),lead=$('tgLead'),notify=$('tgNotify'),
        stEl=$('tgStatus'),cand=$('tgCand'),note=$('tgNote');
  if(!on)return;
  model.innerHTML=CLAUDE_MODELS.map(m=>`<option value="${m.v}">${esc(m.l)}</option>`).join('');
  hour.innerHTML=Array.from({length:24},(_,h)=>`<option value="${h}">${T('Übersicht um {h} Uhr',{h:String(h).padStart(2,'0')+':00'})}</option>`).join('');
  const showStatus=c=>{
    const s=c.status||{};
    const txt={
      off: c.has_token?T('aus'):T('noch nicht eingerichtet'),
      starting: T('startet …'),
      running: T('läuft')+(s.bot?' — @'+s.bot:'')+(c.chat_id?'':' · '+T('wartet auf deine Chat-ID')),
      conflict: T('⚠ Derselbe Bot wird schon woanders abgefragt (anderer Rechner oder Server). Dort stoppen oder einen eigenen Bot anlegen.'),
      error: '⚠ '+(s.error||T('Fehler')),
    }[s.state]||s.state;
    stEl.textContent=txt;
    cand.innerHTML='';
    if(s.candidate&&!c.chat_id){
      cand.innerHTML=` <span class="set-d" style="display:inline">${esc(T('Nachricht von {n} ({id})',{n:s.candidate.name,id:s.candidate.id}))}</span> `
        +`<button class="set-btn" id="tgTake">${T('Übernehmen')}</button>`;
      cand.querySelector('#tgTake').onclick=()=>{chat.value=s.candidate.id;save();};
    }
  };
  const fill=c=>{
    on.checked=!!c.enabled;chat.value=c.chat_id||'';model.value=c.model||'';mode.value=c.mode;
    rem.checked=!!c.reminders;hour.value=String(c.reminder_hour);lead.value=String(c.reminder_lead);
    notify.checked=!!c.notify;
    tok.value='';tok.placeholder=c.has_token?T('•••••••• (gespeichert — nur zum Ändern neu eingeben)'):'123456789:AA…';
    if(c.from_env){tok.disabled=true;tok.placeholder=T('aus der Umgebung (TELEGRAM_TOKEN)');}
    showStatus(c);
  };
  const flash=(t)=>{note.textContent=t;note.classList.add('on');};
  async function save(){
    const body={enabled:on.checked,chat_id:chat.value.trim(),model:model.value,mode:mode.value,
      reminders:rem.checked,reminder_hour:+hour.value,reminder_lead:+lead.value,notify:notify.checked};
    if(tok.value.trim())body.token=tok.value.trim();
    flash(T('⟲ speichere …'));
    try{
      const r=await fetch('/api/telegram',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const j=await r.json();
      if(!r.ok){flash('⚠ '+(j.error||r.status));return;}
      fill(j);flash(T('✓ gespeichert'));
    }catch(e){flash('⚠ '+(e.message||e));}
  }
  $('tgSave').onclick=save;
  on.onchange=save;
  $('tgTest').onclick=async()=>{
    flash(T('⟲ sende …'));
    try{const r=await fetch('/api/telegram/test',{method:'POST'});const j=await r.json();
      flash(r.ok?T('✅ gesendet!'):'⚠ '+(j.error||r.status));}catch(e){flash('⚠ '+(e.message||e));}
  };
  fetch('/api/telegram').then(r=>r.json()).then(fill).catch(()=>{});
  clearInterval(tgTimer);
  tgTimer=setInterval(async()=>{
    if(!document.body.contains(stEl)){clearInterval(tgTimer);return;}
    try{showStatus(await(await fetch('/api/telegram')).json());}catch{}
  },3000);
}

function setupTTS(w){
  const auto=w.querySelector('#ttsAuto'),model=w.querySelector('#ttsModel'),
        voice=w.querySelector('#ttsVoice'),info=w.querySelector('#ttsVoiceInfo'),
        style=w.querySelector('#ttsStyle'),tryB=w.querySelector('#ttsTry'),note=w.querySelector('#ttsNote');
  if(!auto)return;
  // Stimme und Sprechweise gelten je Oberflächensprache (config.py).
  const lang=I18N.lang==='en'?'en':'de', en=lang==='en';
  const cur=SETTINGS.tts||{}, curVoice=(cur.voice||{})[lang]||'';
  model.value=cur.model||'gemini-3.8-flash-lite-tts';
  style.value=(cur.style||{})[lang]||'';
  const setVoiceOpts=list=>{
    const have=list.some(v=>v.id===curVoice);
    voice.innerHTML=(have||!curVoice?'':`<option value="${esc(curVoice)}">${esc(curVoice)}</option>`)
      +list.map(v=>`<option value="${esc(v.id)}" title="${esc(v.description||'')}">${esc(v.name)}`
        +[v.gender,v.pitch,v.accent].filter(Boolean).map(x=>' · '+esc(x)).join('')+'</option>').join('');
    voice.value=curVoice||list[0]?.id||'';
  };
  setVoiceOpts([]);
  fetch('/api/tts/voices?lang='+(en?'en-US':'de-DE')).then(r=>r.json()).then(d=>{
    if(d.error){info.textContent='⚠ '+d.error;return;}
    info.textContent=en?`${d.voices.length} English (US) voices in the Gemini catalog.`
                       :`${d.voices.length} deutsche Stimmen im Gemini-Katalog.`;
    setVoiceOpts(d.voices);
  }).catch(()=>{info.textContent='⚠ Stimmenliste nicht abrufbar.';});
  w.querySelector('#ttsKey').onclick=openLlmCfg;
  auto.onchange=()=>setSave({tts:{auto:auto.checked}});
  model.onchange=()=>setSave({tts:{model:model.value}});
  voice.onchange=()=>setSave({tts:{voice:{[lang]:voice.value}}});
  style.onchange=()=>setSave({tts:{style:{[lang]:style.value}}});
  tryB.onclick=async()=>{
    note.textContent='…';note.classList.add('on');
    try{
      await sayPlay(en?`Hi ${USER_NAME||''}, I'm ${ASSISTANT}. This is how I sound with this voice.`
                      :`Hallo ${USER_NAME||''}, ich bin ${ASSISTANT}. So klinge ich mit dieser Stimme.`,null,
        {voice:voice.value,model:model.value,style:style.value});
      note.classList.remove('on');
    }catch(e){note.textContent='⚠ '+e.message;}
  };
}

function setupUpdates(w){
  const auto=w.querySelector('#updAuto'), iv=w.querySelector('#updIv'),
        btn=w.querySelector('#updNow'), note=w.querySelector('#updNote'),
        log=w.querySelector('#updLog');
  if(!auto)return;
  const cur=SETTINGS.updates||{};
  iv.value=String(cur.interval_h??6);
  auto.onchange=()=>setSave({updates:{auto:auto.checked}});
  iv.onchange=()=>setSave({updates:{interval_h:+iv.value}});

  const poll=()=>{
    clearInterval(updSetTimer);
    updSetTimer=setInterval(async()=>{
      let st;try{st=await(await fetch('/api/updates')).json();}catch{return;}
      log.style.display='';log.textContent=(st.log||[]).join('\n');log.scrollTop=log.scrollHeight;
      updRender(st);
      if(st.done){
        clearInterval(updSetTimer);
        btn.disabled=false;btn.textContent='Jetzt suchen';
        const bad=Object.values(st.steps||{}).some(s=>s.state==='error');
        note.textContent=bad?'⚠ mit Fehlern beendet':(st.changed?'✓ aktualisiert':'✓ alles aktuell');
        note.classList.add('on');
      }
    },1200);
  };

  btn.onclick=async()=>{
    btn.disabled=true;btn.textContent='läuft…';
    note.textContent='';note.classList.add('on');
    log.style.display='';log.textContent='';
    updHidden=false;                     // die Karte darf wieder auftauchen
    let r={};
    try{r=await(await fetch('/api/updates/run',{method:'POST'})).json();}catch{}
    if(r.ok===false){
      btn.disabled=false;btn.textContent='Jetzt suchen';
      note.textContent='⚠ '+(r.error||'nicht gestartet');
      return;
    }
    poll();
  };
  // Laeuft gerade schon einer (etwa der vom Start), gleich mitzeigen.
  fetch('/api/updates').then(r=>r.json()).then(st=>{
    if(st.log&&st.log.length){log.style.display='';log.textContent=st.log.join('\n');}
    if(st.running){btn.disabled=true;btn.textContent='läuft…';poll();}
    else if(st.last_check){
      const min=Math.round((Date.now()/1000-st.last_check)/60);
      note.textContent=min<1?'zuletzt gerade eben geprüft'
        :(min<60?`zuletzt vor ${min} min geprüft`:`zuletzt vor ${Math.round(min/60)} h geprüft`);
      note.classList.add('on');
    }
  }).catch(()=>{});
}

// ---------- Charakter (SOUL.md / USER.md) ----------
let personaCache=null, personaTab='soul';
async function setupPersona(w){
  const area=w.querySelector('#setSoul'), note=w.querySelector('#soulNote');
  if(!personaCache){
    try{personaCache=await(await fetch('/api/persona')).json();}
    catch{personaCache={soul:'',user:''};}
  }
  const show=()=>{area.value=personaCache[personaTab]||'';};
  show();
  w.querySelectorAll('[data-persona]').forEach(b=>b.onclick=()=>{
    // Ungespeichertes des aktuellen Reiters mitnehmen, sonst ist es beim
    // Zurückwechseln weg — und der Nutzer merkt es erst zu spaet.
    personaCache[personaTab]=area.value;
    personaTab=b.dataset.persona;
    w.querySelectorAll('[data-persona]').forEach(o=>o.classList.toggle('on',o===b));
    show();
  });
  w.querySelector('#soulSave').onclick=async()=>{
    personaCache[personaTab]=area.value;
    note.textContent='…';note.classList.add('on');
    try{
      await fetch('/api/persona',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({[personaTab]:area.value})});
      note.textContent='✓ gespeichert — gilt ab der nächsten Nachricht';
    }catch{note.textContent='⚠ nicht gespeichert';}
    setTimeout(()=>note.classList.remove('on'),2600);
  };
}

// ---------- Bilder ----------
function setupAvatars(w){
  const av=SETTINGS.avatars||(SETTINGS.avatars={user:'',assistant:''});
  const paint=()=>{
    const u=w.querySelector('#avU'), a=w.querySelector('#avA');
    u.style.backgroundImage=av.user?`url("${av.user}")`:'';
    u.textContent=av.user?'':((SETTINGS.names&&SETTINGS.names.user||'?').slice(0,1).toUpperCase());
    a.style.backgroundImage=`url("${av.assistant||'/static/cody.png'}")`;
    a.textContent='';
  };
  paint();
  const pick=(who)=>{
    const inp=document.createElement('input');
    inp.type='file';inp.accept='image/*';
    inp.onchange=async e=>{
      const f=e.target.files&&e.target.files[0];if(!f)return;
      const fd=new FormData();fd.append('file',f);
      try{
        const j=await(await fetch('/api/upload',{method:'POST',body:fd})).json();
        if(!j.url){alert(j.error||'Upload fehlgeschlagen');return;}
        av[who]=j.url;paint();setSave({avatars:{[who]:j.url}});applyAvatars();
      }catch{alert('Upload fehlgeschlagen');}
    };
    inp.click();
  };
  w.querySelector('#avUPick').onclick=()=>pick('user');
  w.querySelector('#avAPick').onclick=()=>pick('assistant');
  w.querySelector('#avUClear').onclick=()=>{av.user='';paint();setSave({avatars:{user:''}});applyAvatars();};
  w.querySelector('#avAClear').onclick=()=>{av.assistant='';paint();setSave({avatars:{assistant:''}});applyAvatars();};
}
// Eigene Bilder als CSS-Variablen: die Avatar-Regeln greifen dann ueberall,
// auch in schon gezeichneten Nachrichten.
function applyAvatars(){
  const av=SETTINGS.avatars||{}, r=document.documentElement;
  r.style.setProperty('--av-user', av.user?`url("${av.user}")`:'none');
  r.style.setProperty('--av-asst', `url("${av.assistant||'/static/cody.png'}")`);
  r.classList.toggle('no-avatar', !av.user);
  HAS_AVATAR = !!av.user;
}

function bgApply(patch){
  Object.assign(SETTINGS.background, patch);
  applyBackground(); bgPreview();
  setSave({background:patch});
  document.querySelectorAll('input[name=bgm]').forEach(r=>{
    r.checked=(SETTINGS.background.mode||'matrix')===r.value;
  });
}
function bgPreview(){
  const el=document.getElementById('bgPrev'); if(!el)return;
  const bg=SETTINGS.background, img=bg.image;
  el.style.backgroundImage = img?`linear-gradient(rgba(0,0,0,${((bg.dim==null?60:bg.dim)/100).toFixed(2)}),`
    +`rgba(0,0,0,${((bg.dim==null?60:bg.dim)/100).toFixed(2)})), url("${img}")` : 'none';
  el.innerHTML = img?'<span>VORSCHAU</span>':'<span style="opacity:.5">kein Bild gewählt</span>';
}

