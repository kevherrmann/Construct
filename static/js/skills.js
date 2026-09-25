// CONSTRUCT — Skills-Ansicht
// ---------- Skills ----------
async function loadSkills(){
  const el=document.getElementById('skills');el.innerHTML='<div class="vhint">⟲ lade…</div>';
  let g={};try{g=await (await fetch('/api/skills')).json();}catch{}
  el.innerHTML='';const projs=Object.keys(g);
  if(!projs.length){el.innerHTML='<div class="vhint">keine Skills gefunden</div>';return;}
  projs.forEach(proj=>{
    const open=openFolders['sk:'+proj]!==false;
    const hdr=document.createElement('div');hdr.className='folder';
    hdr.innerHTML=`<span class="fa">${open?'▾':'▸'}</span><span class="fn">▣ ${esc(proj)}</span><span class="fc">${g[proj].length}</span>`;
    hdr.onclick=()=>{openFolders['sk:'+proj]=!open;loadSkills();};el.appendChild(hdr);
    if(open)g[proj].forEach(sk=>{
      const d=document.createElement('div');d.className='sess';
      d.innerHTML=`<span class="t">⚡ ${esc(sk.name)}</span><span class="d">${esc(sk.desc||'')}</span>`;
      d.onclick=()=>openSkill(sk);el.appendChild(d);
    });
  });
}
async function openSkill(sk){
  chat.innerHTML='<div class="tool">⟲ …</div>';
  let j={};try{j=await (await fetch('/api/skill?path='+encodeURIComponent(sk.path))).json();}catch{}
  chat.innerHTML='';
  const head=document.createElement('div');head.className='skillhead';
  head.innerHTML=`<span>📄 ${esc(sk.name)}</span>`;
  const back=document.createElement('button');back.className='backbtn';back.textContent='← zurück';back.onclick=newSession;
  head.appendChild(back);chat.appendChild(head);
  const m=document.createElement('div');m.className='msg bot';
  const content=j.content||'(leer / nicht lesbar)';
  const rendered=sk.kind==='py'?md('```python\n'+content+'\n```'):md(content);
  m.innerHTML=`<div class="bubble">${rendered}</div>`;addCopyBtns(m);chat.appendChild(m);scroll();
}

