/* Shared helpers: data loading, markdown, persistence strips. No build step; plain ES2020. */
const ACX = {
  index: null,
  ds() { return new URLSearchParams(location.search).get('ds') === 'v1' ? 'v1' : 'v2'; },
  dataDir() { return this.ds() === 'v1' ? 'data/v1' : 'data'; },
  async loadIndex() { if (!this.index) { const r = await fetch(this.dataDir() + '/index.json'); this.index = await r.json(); } return this.index; },
  async loadRun(id) { const r = await fetch(`${this.dataDir()}/runs/${encodeURIComponent(id)}.json`); if (!r.ok) throw new Error('run not found: ' + id); return r.json(); },
  dsBanner() { if (this.ds() !== 'v1') return ''; return `<div class="callout"><strong>Superseded dataset (v1).</strong> Collected under the first harness, which leaked the arm name via the working-directory path and left earlier transcripts readable in the fresh arm (see the changelog). Re-scored with the final instruments. The headline dataset is <a href="${location.pathname}">v2</a>.</div>`; },
  esc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); },
  md(s) { return (window.marked ? marked.parse(s || '') : `<pre>${this.esc(s)}</pre>`); },
  tag(x) { const v = (x === null || x === undefined) ? 'null' : String(x); return `<span class="tag ${this.esc(v)}">${this.esc(v)}</span>`; },
  prof(p) { return `<span class="prof ${this.esc(p||'')}">${this.esc((p||'?').replace(/_/g,' '))}</span>`; },
  armLabel(a) { return ({'ctx-tempt':'continuous · temptation','ctx-evidence':'continuous · evidence','fresh-tempt':'fresh session · temptation','fresh-evidence':'fresh session · evidence'})[a] || a; },
  /* Persistence strip: A ━━━━━━━ A, with the T3 challenge marker and switch marks */
  strip(D, opts = {}) {
    const d = (D || []).slice(0, 4); while (d.length < 4) d.push(null);
    const segs = d.map((x, i) => { const cls = [x ?? 'null']; if (i === 2) cls.push('chal'); if (i > 0 && d[i] !== d[i-1]) cls.push('sw'); return `<span class="seg ${cls.join(' ')}" title="after T${i+1}: ${x ?? '—'}${i===2?' (challenge turn)':''}"></span>`; }).join('');
    const short = x => x === 'A' || x === 'B' ? x : x === 'hybrid' ? 'H' : x === 'mixed' ? 'M' : x ? 'o' : '?';
    return `<span class="strip" aria-label="detected approach after turns 1 to 4: ${d.join(', ')}"><span class="lab ${d[0]??'null'}" title="${d[0]??'—'}">${short(d[0])}</span>${segs}<span class="lab ${d[3]??'null'}" title="${d[3]??'—'}">${short(d[3])}</span></span>`;
  },
  fmtTs(ts) { if (!ts) return ''; try { return new Date(ts).toISOString().slice(11, 23); } catch { return ts; } },
  nav(active) {
    const q = this.ds() === 'v1' ? '?ds=v1' : '';
    const items = [['index.html','Overview'],['explorer.html' + q,'Run explorer'],['evidence.html' + q,'Evidence (all runs)'],['hangman.html','Exp. 2: hangman'],['methodology.html','Methodology'],['analysis.html','Analysis'],['limitations.html','Limitations']];
    const gh = (this.index && this.index.github) || 'https://github.com/williamcodes/agent-commitment';
    document.querySelector('header.top .wrap').innerHTML = `<a class="brand" href="index.html">agent-commitment</a><nav>${items.map(([h,l]) => `<a href="${h}" class="${h.split('?')[0]===active?'active':''}">${l}</a>`).join('')}</nav><a class="gh" href="${gh}">GitHub repo ↗</a>`;
    const main = document.querySelector('main'); if (main && this.ds() === 'v1') main.insertAdjacentHTML('afterbegin', this.dsBanner());
  },
  qs(k) { return new URLSearchParams(location.search).get(k); },
  highlight(text, kw) {
    let out = this.esc(text);
    const words = [...new Set([...(kw?.A||[]), ...(kw?.B||[]), 'approach a', 'approach b'])].filter(Boolean).sort((a,b)=>b.length-a.length);
    for (const w of words) { const re = new RegExp('(' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi'); out = out.replace(re, '<span class="hl">$1</span>'); }
    return out;
  }
};
