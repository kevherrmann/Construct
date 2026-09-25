// CONSTRUCT — Matrix-Regen im Hintergrund
// ---------- Matrix Rain ----------
const cv=document.getElementById('rain'),cx=cv.getContext('2d');
let cols,drops;
// Der Regen ist Deko bei 28% Deckkraft und liegt hinter allem. Er muss deshalb
// NICHT in voller Bildschirmauflösung rastern: auf 4K sind das 8,3 Mio Pixel,
// die der Vollbild-fillRect pro Frame neu durchblendet. Bei halber Auflösung
// ist es ein Viertel davon, hochskaliert sieht man den Unterschied nicht.
// Steht auf 1 (volle Schaerfe): gemessen kostet der Canvas selbst nur ~3,6% CPU,
// teuer war die Kombination mit dem Scanline-Overlay. Bei Leistungsproblemen auf
// schwacher Hardware laesst sich hier auf 0.75/0.5 runtergehen — spart Pixel,
// macht den Regen aber weicher.
const RAIN_SCALE = 0.5, CELL = 14;
let step;
function rsize(){
  cv.width  = Math.max(1, Math.round(innerWidth  * RAIN_SCALE));
  cv.height = Math.max(1, Math.round(innerHeight * RAIN_SCALE));
  step = CELL * RAIN_SCALE;
  cols = Math.floor(cv.width / step);
  drops = Array(cols).fill(1);
}
rsize();addEventListener('resize',rsize);
const glyph="ｱｲｳｴｵｶｷｸ0123456789ABCDEFﾊﾋﾌﾍﾎ$+*=<>";
function draw(){
  // Canvas versteht keine CSS-Variablen — die Werte müssen ausgelesen und
  // gemerkt werden. Bei jedem Frame neu zu fragen waere ein erzwungenes
  // Neu-Berechnen des Stils, 18-mal pro Sekunde ueber die ganze Seite.
  cx.fillStyle=RAIN_FADE;cx.fillRect(0,0,cv.width,cv.height);
  cx.fillStyle=RAIN_COLOR;cx.font=step+"px monospace";
  for(let i=0;i<cols;i++){
    cx.fillText(glyph[Math.floor(Math.random()*glyph.length)],i*step,drops[i]*step);
    if(drops[i]*step>cv.height&&Math.random()>.975)drops[i]=0;drops[i]++;
  }
}
// setInterval taktet blind weiter — auch wenn das Fenster verdeckt oder
// minimiert ist — und staut Frames auf, wenn ein Zeichenlauf mal länger dauert
// als der Takt. requestAnimationFrame pausiert automatisch, sobald das Fenster
// unsichtbar ist, und liefert nie mehr Frames, als der Compositor schafft.
// Im WebKitGTK-Fenster ohne GPU-Beschleunigung ist der Vollbild-Canvas sonst
// dauerhafte CPU-Last, die beim Tippen als Verzögerung ankommt.
// Sparmodus: desktop.py haengt ?fx=low an, wenn es mangels GPU auf
// Software-Rendering ausweichen musste. Dann fallen die Scanlines weg und der
// Regen laeuft langsamer. Selbst uebersteuern:
//   localStorage.setItem('mxfx','full')  -> volle Optik, mehr Last
//   localStorage.setItem('mxfx','low')   -> sparsam, auch im Browser
//   localStorage.setItem('mxfx','off')   -> Regen ganz aus (sparsamste Stufe)
//   localStorage.removeItem('mxfx')      -> wieder automatisch
const _fxPref = localStorage.getItem('mxfx');
const FX_OFF = _fxPref === 'off';        // Regen komplett aus (sparsamste Stufe)
const FX_LOW = FX_OFF || _fxPref === 'low'
            || (_fxPref !== 'full'
                && new URLSearchParams(location.search).get('fx') === 'low');

// Bildrate des Regens in ms — der wirksamste Regler fuer die CPU-Last, weil
// jeder Frame ein Neu-Zusammensetzen aller Ebenen darueber ausloest. Gemessen
// auf 4K ohne GPU: 55ms = 33% CPU, 110ms = 21%, Regen ganz aus = 3,7%.
const RAIN_MS = FX_LOW ? 110 : 55;
let _rainLast = 0;
// Wird von applyBackground() umgelegt, wenn der Nutzer auf Bild oder
// schlichten Hintergrund wechselt.
let RAIN_ON = true;
// Farben des Regens, aus den Theme-Variablen gelesen. readRainColors() laeuft
// beim Start und nach jedem Themenwechsel — nicht pro Frame.
let RAIN_COLOR = '#00ff41', RAIN_FADE = 'rgba(0,6,0,.07)';
function readRainColors(){
  const cs = getComputedStyle(document.documentElement);
  RAIN_COLOR = (cs.getPropertyValue('--rain') || '#00ff41').trim();
  RAIN_FADE  = (cs.getPropertyValue('--rain-fade') || 'rgba(0,6,0,.07)').trim();
}
function rainLoop(t){
  requestAnimationFrame(rainLoop);
  if (!RAIN_ON) return;
  if (t - _rainLast < RAIN_MS) return;
  _rainLast = t;
  draw();
}
// Sparmodus: ohne GPU-Beschleunigung ist der Vollbild-Canvas auf einem
// 4K-Schirm der mit Abstand teuerste Teil der Oberfläche — er kostet dann
// mehr als die halbe CPU eines Kerns und verzögert sichtbar die Texteingabe.
// desktop.py hängt ?fx=low an, wenn es auf Software-Rendering ausweichen
// musste. Dauerhaft selbst setzen:  localStorage.setItem('mxfx','low')
// Wieder anschalten:                localStorage.removeItem('mxfx')
document.body.classList.toggle('fx-low', FX_LOW);
document.body.classList.toggle('fx-off', FX_OFF);
if (!FX_OFF) requestAnimationFrame(rainLoop);

