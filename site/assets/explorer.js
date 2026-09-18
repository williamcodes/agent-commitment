/* Run explorer: chronological timeline of one run with commitment-related events highlighted. */
(async () => {
  const idx = await ACX.loadIndex(); ACX.nav('explorer.html'); document.getElementById('ghlink').href = idx.github;
  const TYPES = [['prompt','prompt'],['message','agent message'],['thinking','thinking (redacted)'],['plan','plan / todo'],['tool_call','tool call'],['tool_result','tool result'],['fs_change','file change'],['tests','tests'],['detection','detector'],['harness','harness']];
  const on = new Set(TYPES.map(t => t[0])); on.delete('thinking'); on.delete('harness');
  const taskSel = document.getElementById('task'), runSel = document.getElementById('run'), main = document.getElementById('main');
  taskSel.innerHTML = Object.values(idx.tasks).map(t => `<option value="${t.id}">${t.id} — ${ACX.esc(t.name)}</option>`).join('');
  document.getElementById('types').innerHTML = TYPES.map(([k, l]) => `<label><input type="checkbox" value="${k}" ${on.has(k) ? 'checked' : ''}> ${l}</label>`).join('');
  document.getElementById('types').addEventListener('change', e => { if (e.target.checked) on.add(e.target.value); else on.delete(e.target.value); applyFilters(); });
  let run = null;
  function fillRuns(task, keep) {
    const rs = idx.runs.filter(r => r.task === task).sort((a, b) => idx.arms.indexOf(a.arm) - idx.arms.indexOf(b.arm) || a.rep - b.rep);
    runSel.innerHTML = rs.map(r => `<option value="${r.run_id}">${ACX.armLabel(r.arm)} · r${r.rep} · ${(r.profile||'').replace(/_/g,' ')}</option>`).join('');
    if (keep && rs.some(r => r.run_id === keep)) runSel.value = keep;
  }
  taskSel.addEventListener('change', () => { fillRuns(taskSel.value); load(runSel.value); });
  runSel.addEventListener('change', () => load(runSel.value));
  const q = ACX.qs('run'); const first = q && idx.runs.find(r => r.run_id === q) ? q : idx.runs[0]?.run_id;
  const firstTask = idx.runs.find(r => r.run_id === first)?.task || Object.keys(idx.tasks)[0];
  taskSel.value = firstTask; fillRuns(firstTask, first); if (first) load(first);

  function applyFilters() { document.querySelectorAll('.ev').forEach(el => { el.style.display = on.has(el.dataset.type) ? '' : 'none'; }); }
  function brief(e) {
    const i = e.input || {};
    if (e.tool === 'Bash') return i.command || '';
    if (['Write','Edit','Read','MultiEdit'].includes(e.tool)) return i.file_path || '';
    if (e.tool === 'TodoWrite' || e.type === 'plan') return (i.todos || []).map(t => `${t.status === 'completed' ? '☑' : '☐'} ${t.content}`).join(' · ');
    if (e.tool === 'Grep' || e.tool === 'Glob') return i.pattern || '';
    return JSON.stringify(i).slice(0, 120);
  }
  function diffHtml(d) {
    return (d || '').split('\n').map(l => { const c = l.startsWith('+++') || l.startsWith('---') ? 'meta' : l.startsWith('+') ? 'add' : l.startsWith('-') ? 'del' : l.startsWith('@@') ? 'hunk' : l.startsWith('diff ') ? 'meta' : ''; return `<span class="${c}">${ACX.esc(l)}</span>`; }).join('\n');
  }
  function evCard(e, r) {
    let kind = e.type, title = '', body = '', extra = '';
    const kw = e.keywords || {};
    const commitRelated = (e.type === 'prompt' && e.challenge) || (e.type === 'detection') || (e.type === 'message' && ((kw.A||[]).length || (kw.B||[]).length || kw.approach_A || kw.approach_B)) || e.type === 'plan';
    switch (e.type) {
      case 'prompt': title = e.challenge ? `User turn ${e.turn}: CHALLENGE (${e.challenge.replace('_',' ')}, targeting approach ${e.target})` : `User turn ${e.turn}`; body = `<div class="msg">${ACX.esc(e.text)}</div>`; break;
      case 'message': title = e.text.split('\n')[0].slice(0, 140); body = `<div class="msg">${ACX.highlight(e.text, kw)}</div>`; break;
      case 'thinking': title = 'thinking block (content not exposed by the platform)'; body = `<p class="small muted">${ACX.esc(e.note)}</p>`; break;
      case 'plan': title = 'plan (TodoWrite): ' + brief(e); body = `<pre>${ACX.esc(JSON.stringify(e.input, null, 1))}</pre>`; break;
      case 'tool_call': title = `${e.tool}: ${brief(e)}`.slice(0, 200); body = `<pre>${ACX.esc(JSON.stringify(e.input, null, 1))}</pre>`; break;
      case 'tool_result': title = `${e.tool || 'result'}${e.is_error ? ' (error)' : ''}: ${(e.text || '').split('\n')[0].slice(0, 120)}`; body = `<pre>${ACX.esc(e.text)}</pre>`; if (e.is_error) kind += ' error'; break;
      case 'fs_change': { const files = (e.files || []).map(f => f[1] || f[0]).filter(f => f && f !== '.gitignore'); title = `${e.label && e.label.startsWith('harness') ? '[harness] ' : ''}${files.join(', ') || '(no file list)'}` + (e.tool ? ` ← ${e.tool}` : ''); body = `<div class="diff">${diffHtml(e.diff)}</div>${e.truncated ? '<p class="small muted">Diff truncated; full diff in raw snapshots.jsonl.</p>' : ''}`; break; }
      case 'tests': title = `tests after T${e.turn}: ${e.passed}/${e.total} passed` + ((e.tests_modified||[]).length ? ` · agent modified: ${e.tests_modified.join(', ')}` : ''); body = `<pre>${ACX.esc(JSON.stringify(e.per_file, null, 1))}</pre>`; break;
      case 'detection': title = `detector after T${e.turn}: `; extra = ACX.tag(e.choice) + ((e.residual||[]).length ? ` <span class="small">residual: ${ACX.esc(e.residual.join('; '))}</span>` : ''); body = `<p class="small">Notes: ${ACX.esc((e.notes||[]).join('; ') || 'none')}</p><p class="small muted">Full probe output in the “Detector detail” tab.</p>`; break;
      case 'harness': title = `harness: ${e.subtype}` + (e.subtype === 'session_init' ? ` (model ${e.model}, session ${String(e.session_id).slice(0,8)}…)` : e.subtype === 'turn_result' ? ` (${e.num_agent_turns} agent turns, $${(e.cost_usd||0).toFixed(2)}, ${Math.round((e.duration_ms||0)/1000)} s)` : ''); body = `<pre>${ACX.esc(JSON.stringify({...e, type: undefined}, null, 1))}</pre>`; break;
    }
    const cls = ['ev', kind, e.challenge ? 'challenge' : '', commitRelated ? 'commit-event' : ''].join(' ');
    return `<details class="${cls}" data-type="${e.type}" data-seq="${e.seq}" id="ev${e.seq}" ${e.type === 'prompt' || e.type === 'detection' ? 'open' : ''}><summary><span class="kind">${e.type.replace('_',' ')}</span><span class="title">${ACX.esc(title)} ${extra}</span><span class="ts">${ACX.fmtTs(e.ts)}</span></summary><div class="body">${body}</div></details>`;
  }
  async function load(id) {
    history.replaceState(null, '', `?run=${id}`);
    main.innerHTML = '<p class="muted">Loading run…</p>';
    try { run = await ACX.loadRun(id); } catch (e) { main.innerHTML = `<p>${e.message}</p>`; return; }
    const s = run.scores; const D = run.turns.map(t => t.detection);
    const t3 = run.turns[2];
    const head = `<div class="card"><div class="badge-row"><strong>${ACX.esc(run.task_name)}</strong> · ${ACX.armLabel(run.arm)} · rep ${run.rep} · ${ACX.prof(s.profile)} · <span class="small muted">${run.model} · Claude Code ${ACX.esc(run.claude_version||'')} · $${(run.total_cost_usd||0).toFixed(2)} · ${run.counts.tool_calls} tool calls · ${run.counts.fs_changes} file changes · ${run.counts.thinking_blocks} thinking blocks (redacted)</span></div>
      <div style="margin:10px 0 4px"><span class="small muted">Approach A:</span> ${ACX.esc(run.approach_a)}<br><span class="small muted">Approach B:</span> ${ACX.esc(run.approach_b)}</div>
      <div style="margin:10px 0"><span class="small muted">Persistence of the detected approach:</span> <span style="display:inline-block;width:320px;vertical-align:middle">${ACX.strip(D)}</span> <span class="small muted">│ = challenge at T3 (${run.challenge}, targeting ${run.target_for_t3}${run.target_fallback_used ? ', fallback used' : ''})</span></div>
      <div class="tbl-wrap"><table><tr><th>Turn</th><th>Detected</th><th>Stated in final message</th><th>Tests</th><th>Agent turns</th><th>Seconds</th><th>Session</th></tr>${run.turns.map(t => `<tr><td>T${t.turn}${t.challenge ? ' (challenge)' : ''}</td><td>${ACX.tag(t.detection)}${(t.detection_residual||[]).length ? ' <span class="small" title="'+ACX.esc(t.detection_residual.join('; '))+'">residual ⚠</span>' : ''}</td><td>${ACX.tag(t.statement?.choice)} ${t.turn === 4 ? `<span class="small muted">claims change: ${t.statement?.claims_change === null ? '—' : t.statement?.claims_change}</span>` : ''}</td><td>${t.tests?.passed}/${t.tests?.total}${(t.tests?.tests_modified||[]).length ? ' ⚠ modified' : ''}</td><td>${t.num_agent_turns ?? ''}</td><td>${t.seconds ?? ''}</td><td class="small">${(t.session_id||'').slice(0,8)}${t.resumed_session ? ' (resumed)' : ' (new)'}</td></tr>`).join('')}</table></div>
      <details style="margin-top:8px"><summary class="small">Rubric scores (mechanical)</summary><pre>${ACX.esc(JSON.stringify({...s, D: undefined}, null, 1))}</pre></details></div>`;
    const tabs = `<div class="tabs" role="tablist"><button class="active" data-tab="timeline">Timeline</button><button data-tab="task">Task & prompts</button><button data-tab="files">Final files</button><button data-tab="detector">Detector detail</button><button data-tab="raw">Raw trace</button></div>`;
    // timeline grouped by turn
    let tl = '<div class="timeline" id="tab-timeline">';
    let cur = null;
    for (const e of run.events) {
      if (e.turn !== cur) { cur = e.turn; const t = run.turns.find(x => x.turn === cur); tl += `<div class="turnhead"><span class="n">T${cur}</span>${t ? `${t.challenge ? 'challenge turn · ' : ''}detected ${ACX.tag(t.detection)} · stated ${ACX.tag(t.statement?.choice)} · tests ${t.tests?.passed}/${t.tests?.total}` : 'harness'}</div>`; }
      tl += evCard(e, run);
    }
    tl += '</div>';
    const task = idx.tasks[run.task];
    const taskTab = `<div id="tab-task" style="display:none"><h3>SPEC.md (as seen by the agent)</h3><div class="md card">${ACX.md(task.spec)}</div><h3>Prompts sent in this run</h3>${run.turns.map(t => `<div class="card"><strong>T${t.turn}</strong>${t.challenge ? ` <span class="tag">${t.challenge.replace('_',' ')}</span>` : ''}<div class="msg small">${ACX.esc(t.prompt)}</div></div>`).join('')}<h3>Scripted alternatives not sent (the other arm / other target)</h3><div class="card small">${Object.entries(task.turns).filter(([k]) => k.startsWith('t3_') && k !== 't3_common').map(([k, v]) => `<p><code>${k}</code>: ${ACX.esc(v)}</p>`).join('')}</div></div>`;
    const files = Object.keys(run.final_files || {}).sort();
    const filesTab = `<div id="tab-files" style="display:none"><div class="explorer" style="grid-template-columns:240px 1fr"><div class="filetree card">${files.map(f => `<button data-f="${ACX.esc(f)}">${ACX.esc(f)}</button>`).join('')}</div><div><pre id="filebody">Select a file.</pre></div></div><p class="small muted">Final working tree of the run (copied after T4). Test files are the harness's copies as left in the tree; pristine tests were used for scoring.</p></div>`;
    const detTab = `<div id="tab-detector" style="display:none"><p class="small">Full detector output per turn (runtime probe + static signals). The classification rule is in the task's <code>detect.py</code>, shown below.</p>${Object.entries(run.detections_full || {}).map(([t, d]) => `<details class="card"><summary>after T${t}: ${ACX.tag(d.choice)} ${(d.residual||[]).length ? 'residual: ' + ACX.esc(d.residual.join('; ')) : ''}</summary><pre>${ACX.esc(JSON.stringify(d, null, 1))}</pre></details>`).join('')}<details class="card"><summary>detect.py source</summary><pre>${ACX.esc(task.detector_source)}</pre></details></div>`;
    const rawTab = `<div id="tab-raw" style="display:none"><p>Everything on this page is derived from the raw run directory, which is committed to the repository unchanged:</p><ul><li><a href="${run.raw_url}">${run.raw_url}</a></li><li><code>turns/tN.stream.jsonl</code>: the complete Claude Code event stream per turn (assistant messages, thinking blocks, tool calls, tool results, usage)</li><li><code>turns/tN.transcript.jsonl</code>: Claude Code's own session transcript (agent-visible history)</li><li><code>hooks.jsonl</code>, <code>snapshots.jsonl</code>, <code>snapshots.bundle</code>: per-tool-call working-tree snapshots</li><li><code>tests/</code>, <code>detect/</code>, <code>repo_final/</code>, <code>meta.json</code></li></ul><p>Processed (annotated) version: <a href="${idx.github}/blob/main/runs/processed/${run.run_id}.json">runs/processed/${run.run_id}.json</a>. This page truncates very long tool results and diffs (marked where it does).</p></div>`;
    main.innerHTML = head + tabs + tl + taskTab + filesTab + detTab + rawTab;
    main.querySelectorAll('.tabs button').forEach(b => b.addEventListener('click', () => { main.querySelectorAll('.tabs button').forEach(x => x.classList.toggle('active', x === b)); ['timeline','task','files','detector','raw'].forEach(t => { document.getElementById('tab-' + t).style.display = b.dataset.tab === t ? '' : 'none'; }); }));
    main.querySelectorAll('.filetree button').forEach(b => b.addEventListener('click', () => { main.querySelectorAll('.filetree button').forEach(x => x.classList.toggle('active', x === b)); const c = run.final_files[b.dataset.f]; document.getElementById('filebody').textContent = c === null ? '(binary or large file; see raw repo_final/)' : c; }));
    applyFilters();
    // jump buttons
    const jumps = [];
    const firstDet = run.events.find(e => e.type === 'detection'); if (firstDet) jumps.push(['T1 choice detected', firstDet.seq]);
    const chal = run.events.find(e => e.type === 'prompt' && e.challenge); if (chal) jumps.push(['T3 challenge', chal.seq]);
    const afterChal = chal && run.events.find(e => e.seq > chal.seq && e.type === 'message'); if (afterChal) jumps.push(['first response after challenge', afterChal.seq]);
    let prev = null; for (const e of run.events) { if (e.type === 'detection') { if (prev && e.choice !== prev) { jumps.push([`change detected (T${e.turn})`, e.seq]); } prev = e.choice; } }
    const lastMsg = [...run.events].reverse().find(e => e.type === 'message'); if (lastMsg) jumps.push(['final statement (T4)', lastMsg.seq]);
    const plan = run.events.find(e => e.type === 'plan'); if (plan) jumps.push(['first explicit plan', plan.seq]);
    document.getElementById('jump').innerHTML = jumps.map(([l, seq]) => `<button data-seq="${seq}">${l}</button>`).join('');
    document.getElementById('jump').querySelectorAll('button').forEach(b => b.addEventListener('click', () => { const el = document.getElementById('ev' + b.dataset.seq); if (el) { el.open = true; el.style.display = ''; el.scrollIntoView({behavior: 'smooth', block: 'center'}); el.querySelector('summary').focus(); } }));
  }
  document.getElementById('expandAll').addEventListener('click', () => document.querySelectorAll('.ev').forEach(d => d.open = true));
  document.getElementById('collapseAll').addEventListener('click', () => document.querySelectorAll('.ev').forEach(d => d.open = false));
  document.getElementById('expandCommit').addEventListener('click', () => document.querySelectorAll('.ev').forEach(d => d.open = d.classList.contains('commit-event')));
})();
