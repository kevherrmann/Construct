// CONSTRUCT — Ausbaustufe aus window.CONSTRUCT, Einstellungen, Namen
// ---------- Ausbaustufe ----------
// Das Objekt setzt der Server beim Ausliefern; die Vorgabe im <head> greift nur,
// wenn jemand die Datei direkt im Browser öffnet.
const CFG=window.CONSTRUCT||{},
      WORKSPACE_DIR=CFG.workspace||'',
      ASSISTANT=CFG.assistant||'Cody',USER_NAME=CFG.user||T('Du');
// Ist das claude-CLI da? Davon hängt ab, ob die Claude-Modelle etwas taugen und
// ob der 🔑-Chip zum Anmelden oder zum Installieren führt. Kommt synchron vom
// Server (shutil.which), nicht geraten.
const SETTINGS=CFG.settings||{tiles:{},background:{}};
// Nur für die Vorschau-Punkte in der Auswahl. Die echten Farben stehen im CSS;
// hier dieselben Werte doppelt zu halten ist der Preis dafür, dass die Kärtchen
// ohne einen Satz DOM-Messungen pro Theme auskommen.
const THEME_SWATCH={
  matrix:['#000600','#00ff41','#0d3d18'], bernstein:['#0a0600','#ffb648','#4a2f0a'],
  eis:['#00060c','#5fd8ff','#0d3446'],    space:['#06030f','#b98bff','#2c1a4d'],
  asche:['#0c0e11','#d8dee4','#2b3138'],  blut:['#0b0303','#ff5f57','#481815'],
  papier:['#f5f2ea','#1d6b45','#d3dfd6'], nebel:['#eef1f6','#2757b8','#d5dce8'],
};
const THEMES=[
  {k:'matrix',    n:'Matrix',      d:'Grün auf Schwarz. Der Ursprung.'},
  {k:'bernstein', n:'Bernstein',   d:'Alter Bernstein-Monitor — warm, augenschonend.'},
  {k:'eis',       n:'Eis',         d:'Kühles Cyan auf Tiefblau.'},
  {k:'space',     n:'Space',       d:'Violett auf Nachtblau.'},
  {k:'asche',     n:'Asche',       d:'Neutrales Grau — zurückhaltend, gut zum Lesen.'},
  {k:'blut',      n:'Blut',        d:'Rot auf Schwarz. Laut.'},
  {k:'papier',    n:'Papier',      d:'Hell: Waldgrün auf warmem Papierweiß.'},
  {k:'nebel',     n:'Nebel',       d:'Hell: Tintenblau auf kühlem Grau.'},
];
function applyTheme(){
  const t=SETTINGS.theme||'matrix';
  if(t==='matrix')document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme',t);
  readRainColors();   // der Regen faerbt sich mit
}
function applyBackground(){
  const bg=SETTINGS.background||{}, mode=bg.mode||'matrix';
  const el=document.getElementById('bgimg');
  document.body.classList.toggle('bg-image', mode==='image' && !!bg.image);
  document.body.classList.toggle('bg-plain', mode==='plain');
  if(el){
    el.style.backgroundImage = bg.image ? `url("${bg.image}")` : '';
    el.style.setProperty('--bg-dim', ((bg.dim==null?60:bg.dim)/100).toFixed(2));
  }
  // Der Regen laeuft nur, wenn er auch zu sehen ist — ein Vollbild-Canvas
  // hinter einem deckenden Bild waere reine CPU-Verbrennung.
  RAIN_ON = (mode==='matrix') && !FX_OFF;
}
// Eigenes Bild hinterlegt? Sonst steht der Anfangsbuchstabe im Kreis.
let HAS_AVATAR=!!((CFG.settings&&CFG.settings.avatars||{}).user);
let HAS_CLAUDE=CFG.claude!==false;
const WEB_LOGIN=CFG.web_login!==false;
function applyClaudeState(){
  document.documentElement.classList.toggle('nocl',!HAS_CLAUDE);
  const hint=HAS_CLAUDE?'':' — wirkt nur mit Claude Code. Die Chat-Modelle '
    +'(ChatGPT, Gemini …) haben keinen Zugriff auf Dateien.';
  const f=document.getElementById('folderbar'),m=document.getElementById('modebar');
  if(f)f.title='Arbeitsordner'+hint;
  if(m)m.title='Berechtigungs-Modus'+hint;
}
document.title='CONSTRUCT // '+ASSISTANT;
document.getElementById('whoami').innerHTML='<span class="dot">●</span> '+ASSISTANT.toUpperCase();

