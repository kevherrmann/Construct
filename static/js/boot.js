// CONSTRUCT — Notnagel für fehlenden localStorage — muss vor allem anderen laufen
/* Notnagel für WebViews ohne persistenten Speicher (pywebview im Private Mode,
   strenge Browser-Einstellungen): dort ist localStorage nicht leer, sondern gar
   nicht vorhanden. Der Zugriff weiter unten läuft auf Top-Level — ohne diesen
   Fallback wirft er einen ReferenceError, das restliche Script wird nie
   ausgeführt und KEIN Button reagiert mehr. Lieber Einstellungen vergessen als
   eine tote Oberfläche. Muss vor allem anderen Script stehen. */
(function(){
  var ok = false;
  try {
    ok = (typeof localStorage !== 'undefined') && localStorage !== null;
    if (ok) { localStorage.setItem('__probe','1'); localStorage.removeItem('__probe'); }
  } catch(e) { ok = false; }          // auch abgeschaltet/Quota voll landet hier
  if (ok) return;

  var mem = {};
  var shim = {
    getItem:    function(k){ return Object.prototype.hasOwnProperty.call(mem,k) ? mem[k] : null; },
    setItem:    function(k,v){ mem[k] = String(v); },
    removeItem: function(k){ delete mem[k]; },
    clear:      function(){ mem = {}; },
    key:        function(i){ return Object.keys(mem)[i] || null; }
  };
  Object.defineProperty(shim, 'length', { get: function(){ return Object.keys(mem).length; } });
  try { Object.defineProperty(window, 'localStorage', { value: shim, writable: true, configurable: true }); }
  catch(e) { try { window.localStorage = shim; } catch(e2) {} }
  console.warn('localStorage nicht verfügbar — Einstellungen gelten nur für diese Sitzung.');
})();
