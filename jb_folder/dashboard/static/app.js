(function () {
'use strict';
const ALGS = ['welsh_powell', 'dsatur', 'smallest_last', 'independent_set'];
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const algColor = (a) => css('--c-' + a) || '#888';
const fmtT = (s) => s == null || isNaN(s) ? '—' : s < 1 ? (s * 1000).toFixed(s < 0.01 ? 2 : 1) + ' ms' : s.toFixed(2) + ' s';
const fmtDur = (s) => s < 60 ? s.toFixed(0) + 's' : Math.floor(s / 60) + 'm ' + String(Math.floor(s % 60)).padStart(2, '0') + 's';
const algTag = (a) => `<span class="alg"><i class="dot" style="background:var(--c-${esc(a)})"></i>${esc(a)}</span>`;
const mean = (a) => a.reduce((x, y) => x + y, 0) / a.length;
const stdev = (a) => { if (a.length < 2) return 0; const m = mean(a); return Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / (a.length - 1)); };
const median = (a) => { const s = [...a].sort((x, y) => x - y), n = s.length; return n ? (n % 2 ? s[(n - 1) >> 1] : (s[n / 2 - 1] + s[n / 2]) / 2) : NaN; };
const lsGet = (k, d) => { try { return localStorage.getItem(k) ?? d; } catch (e) { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } };

let history = [], charts = {}, wasBusy = false, pollTimer = null;
const haveChart = () => typeof window.Chart !== 'undefined';

/* ---------- theme ---------- */
function applyTheme(t) {
  if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
  else document.documentElement.removeAttribute('data-theme');
}
function curTheme() {
  const a = document.documentElement.getAttribute('data-theme');
  return a || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
}
applyTheme(lsGet('theme', ''));
$('themeBtn').onclick = () => { const n = curTheme() === 'dark' ? 'light' : 'dark'; lsSet('theme', n); applyTheme(n); renderCharts(); };
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => renderCharts());

/* ---------- api ---------- */
async function api(path, opts) {
  const r = await fetch(path, opts);
  let body = null; try { body = await r.json(); } catch (e) { /* none */ }
  if (!r.ok) throw Object.assign(new Error((body && body.error) || r.statusText), { status: r.status });
  return body;
}
async function loadHistory() { history = await api('/api/history'); renderAll(); }

/* ---------- run panel ---------- */
$('algChecks').innerHTML = ALGS.map((a) => `<label><input type="checkbox" value="${a}" checked><i class="dot" style="background:var(--c-${a})"></i>${a}</label>`).join('');
function setBusy(b) {
  document.querySelectorAll('#runForm input, #runForm select, #runForm button').forEach((e) => { e.disabled = b; });
  $('runBtn').textContent = b ? 'Running…' : 'Run';
}
function showError(m) { const e = $('runError'); e.hidden = !m; e.textContent = m || ''; }
$('runForm').onsubmit = async (ev) => {
  ev.preventDefault(); showError('');
  const algorithms = [...document.querySelectorAll('#algChecks input:checked')].map((i) => i.value);
  if (!algorithms.length) return showError('Select at least one algorithm.');
  const body = { algorithms, impl: $('impl').value, runs: +$('runs').value, warmup: +$('warmup').value, notes: $('notes').value };
  try {
    await api('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    wasBusy = true; setBusy(true); poll();
  } catch (e) { showError(e.message); }
};
async function poll() {
  clearTimeout(pollTimer);
  let s;
  try { s = await api('/api/status'); } catch (e) { pollTimer = setTimeout(poll, 1500); return; }
  const pb = $('progressBox');
  if (s.busy) {
    wasBusy = true; setBusy(true); pb.hidden = false;
    const p = s.progress, pct = p.total_steps ? Math.min(100, 100 * p.done_steps / p.total_steps) : 0;
    $('barFill').style.width = pct.toFixed(1) + '%';
    $('pAlg').innerHTML = p.current_algorithm ? 'Running ' + algTag(p.current_algorithm) : 'Starting…';
    $('pMsg').textContent = `${p.message} (${p.done_steps}/${p.total_steps})`;
    $('pTime').textContent = 'elapsed ' + fmtDur(s.elapsed_s || 0);
    pollTimer = setTimeout(poll, 500);
  } else {
    setBusy(false); pb.hidden = true;
    if (wasBusy) { wasBusy = false; if (s.last_error) showError('Benchmark failed: ' + s.last_error); await loadHistory(); }
    pollTimer = setTimeout(poll, 3000); // also notices runs started from another tab
  }
}

/* ---------- render ---------- */
function renderAll() {
  const has = history.length > 0;
  $('empty').hidden = has; $('latestSec').hidden = !has;
  document.querySelector('.toolbar').hidden = !has;
  $('chartsGrid').hidden = !has || !haveChart();
  $('noChart').hidden = !has || haveChart();
  renderHeader(); renderKpis(); renderAgg(); renderHistTable(); renderCharts();
}
function renderHeader() {
  const last = history[history.length - 1];
  if (!last) { $('machine').textContent = ''; return; }
  const m = last.machine || {}, g = last.graph || {};
  $('graphSummary').textContent = `${g.nodes} nodes · ${g.edges} edges · max degree ${g.max_degree} · avg ${(+g.avg_degree).toFixed(2)}`;
  $('machine').textContent = `${m.python_impl || ''} ${m.python || ''} · networkx ${m.networkx || '?'} · ${m.machine || ''} · ${m.cpu_count || '?'} CPUs · ${m.platform || ''} · hashseed ${m.pythonhashseed}`;
}
function renderKpis() {
  const last = history[history.length - 1]; if (!last) return;
  $('latestMeta').textContent = `${new Date(last.timestamp).toLocaleString()} · ${last.impl} · ${last.runs_per_algorithm} runs, ${last.warmup} warmup`;
  $('kpis').innerHTML = last.results.map((r) => `
    <div class="kpi" style="--c:var(--c-${esc(r.algorithm)})">
      <div class="name">${esc(r.algorithm)} <span class="badge ${r.valid ? '' : 'bad'}">${r.valid ? 'valid' : 'INVALID'}</span></div>
      <div class="big">${r.colors} <span class="muted" style="font-size:13px;font-weight:400">colors</span></div>
      <dl><dt>Median time</dt><dd>${fmtT(r.median_s)}</dd><dt>Min – max</dt><dd>${fmtT(r.min_s)} – ${fmtT(r.max_s)}</dd><dt>CV%</dt><dd>${r.cv_pct.toFixed(1)}%</dd></dl>
    </div>`).join('');
}
function filtered() { const f = $('implFilter').value; return history.filter((r) => f === 'all' || r.impl === f); }
function renderAgg() {
  const groups = {};
  history.forEach((r) => r.results.forEach((x) => {
    const k = r.impl + '|' + x.algorithm; (groups[k] = groups[k] || { impl: r.impl, alg: x.algorithm, runs: [] }).runs.push(x);
  }));
  const rows = Object.values(groups).sort((a, b) => ALGS.indexOf(a.alg) - ALGS.indexOf(b.alg) || a.impl.localeCompare(b.impl)).map((g) => {
    const all = g.runs.flatMap((x) => x.times_s), m = mean(all), sd = stdev(all);
    const dist = {}; g.runs.forEach((x) => { dist[x.colors] = (dist[x.colors] || 0) + 1; });
    const distS = Object.keys(dist).sort((a, b) => a - b).map((c) => `${c}×${dist[c]}`).join(', ');
    const varies = Object.keys(dist).length > 1;
    const within = mean(g.runs.map((x) => x.stdev_s)), between = g.runs.length > 1 ? stdev(g.runs.map((x) => x.median_s)) : NaN;
    return `<tr><td>${algTag(g.alg)}</td><td class="l"><span class="tag">${esc(g.impl)}</span></td><td>${g.runs.length}</td><td>${all.length}</td><td>${fmtT(m)}</td><td>${fmtT(median(all))}</td><td>${fmtT(sd)}</td><td>${m ? (100 * sd / m).toFixed(1) : '0.0'}%</td><td>${fmtT(Math.min(...all))}</td><td>${fmtT(Math.max(...all))}</td><td>${fmtT(within)}</td><td>${fmtT(between)}</td><td class="l" ${varies ? 'style="color:var(--bad);font-weight:600" title="Color count varies across runs"' : ''}>${distS}</td></tr>`;
  });
  $('aggTable').innerHTML = `<thead><tr><th class="l">Algorithm</th><th class="l">Impl</th><th>Runs</th><th>Samples</th><th>Mean</th><th>Median</th><th>Stdev</th><th title="Coefficient of variation = stdev/mean">CV%</th><th>Min</th><th>Max</th><th title="Mean of per-run stdevs">Within-run σ</th><th title="Stdev of per-run medians">Between-run σ</th><th class="l"title="count×runs">Colors</th></tr></thead><tbody>${rows.join('') || '<tr><td colspan="13" class="l muted">No data</td></tr>'}</tbody>`;
}
function renderHistTable() {
  const rows = [...history].reverse().map((r) => {
    const cells = ALGS.map((a) => { const x = r.results.find((y) => y.algorithm === a); return `<td>${x ? `${fmtT(x.median_s)} <span class="muted">/ ${x.colors}c</span>` : '<span class="muted">—</span>'}</td>`; }).join('');
    const det = r.results.map((x) => `<tr><td>${algTag(x.algorithm)}</td><td>${x.colors}</td><td>${x.valid ? 'yes' : 'NO'}</td><td>${fmtT(x.mean_s)}</td><td>${fmtT(x.median_s)}</td><td>${fmtT(x.min_s)}</td><td>${fmtT(x.max_s)}</td><td>${fmtT(x.stdev_s)}</td><td>${x.cv_pct.toFixed(1)}%</td><td class="l" style="white-space:normal">${x.times_s.map((t) => fmtT(t)).join(', ')}</td></tr>`).join('');
    const m = r.machine || {};
    return `<tr class="row" data-id="${esc(r.run_id)}"><td class="l">${esc(new Date(r.timestamp).toLocaleString())}</td><td class="l"><span class="tag">${esc(r.impl)}</span></td><td>${r.runs_per_algorithm}</td><td class="l" style="white-space:normal;max-width:220px">${esc(r.notes)}</td>${cells}<td><button class="btn del" data-del="${esc(r.run_id)}" type="button">Delete</button></td></tr>
    <tr class="detail" id="d-${esc(r.run_id)}" hidden><td colspan="9"><div class="tablewrap"><table><thead><tr><th class="l">Algorithm</th><th>Colors</th><th>Valid</th><th>Mean</th><th>Median</th><th>Min</th><th>Max</th><th>Stdev</th><th>CV%</th><th class="l">Samples</th></tr></thead><tbody>${det}</tbody></table></div><div class="muted small" style="margin-top:8px">run ${esc(r.run_id)} · warmup ${r.warmup} · python ${esc(m.python)} · networkx ${esc(m.networkx)} · hashseed ${esc(m.pythonhashseed)}</div></td></tr>`;
  });
  $('histTable').innerHTML = `<thead><tr><th class="l">Time</th><th class="l">Impl</th><th>Runs</th><th class="l">Notes</th>${ALGS.map((a) => `<th>${algTag(a)}</th>`).join('')}<th></th></tr></thead><tbody>${rows.join('') || '<tr><td colspan="9" class="l muted">No runs yet</td></tr>'}</tbody>`;
}
$('histTable').addEventListener('click', async (e) => {
  const del = e.target.closest('[data-del]');
  if (del) {
    if (!confirm('Delete this run from history?')) return;
    try { await api('/api/history/' + encodeURIComponent(del.dataset.del), { method: 'DELETE' }); await loadHistory(); } catch (er) { showError(er.message); }
    return;
  }
  const row = e.target.closest('tr.row');
  if (row) { const d = $('d-' + row.dataset.id); d.hidden = !d.hidden; }
});

/* ---------- charts ---------- */
function renderLegend() {
  $('legend').innerHTML = ALGS.map((a) => `<span class="alg"><i class="dot" style="background:var(--c-${a})"></i>${a}</span>`).join('');
}
function renderCharts() {
  renderLegend();
  Object.values(charts).forEach((c) => c.destroy()); charts = {};
  if (!haveChart() || !history.length) return;
  const log = $('logToggle').checked, text = css('--muted'), grid = css('--grid');
  Chart.defaults.color = text; Chart.defaults.borderColor = grid;
  const yAxis = { type: log ? 'logarithmic' : 'linear', title: { display: true, text: 'time (s)' }, grid: { color: grid }, ticks: { callback: (v) => { v = +v; if (log) { const m = v / Math.pow(10, Math.floor(Math.log10(v) + 1e-9)); if (Math.abs(m - 1) > 1e-6 && Math.abs(m - 3) > 1e-6) return ''; } return fmtT(v); } } };
  if (!log) yAxis.beginAtZero = true;

  // within-run strip plot
  const last = history[history.length - 1], res = last.results;
  const seed = (i) => { const x = Math.sin(i * 12.9898) * 43758.5453; return x - Math.floor(x); };
  const sets = res.map((r, i) => ({
    label: r.algorithm, type: 'scatter', order: 2,
    data: r.times_s.map((t, j) => ({ x: i + (seed(i * 100 + j) - 0.5) * 0.45, y: Math.max(t, 1e-6) })),
    backgroundColor: algColor(r.algorithm) + 'cc', borderColor: algColor(r.algorithm), pointRadius: 5, pointHoverRadius: 7,
  }));
  sets.push({
    label: 'median', type: 'scatter', order: 1, pointStyle: 'line', pointRadius: 22, borderWidth: 3, pointHoverRadius: 22,
    borderColor: css('--text'), backgroundColor: css('--text'),
    data: res.map((r, i) => ({ x: i, y: Math.max(r.median_s, 1e-6) })),
  });
  charts.strip = new Chart($('stripChart'), {
    data: { datasets: sets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmtT(c.parsed.y)}` } } },
      scales: { x: { type: 'linear', min: -0.6, max: res.length - 0.4, grid: { display: false }, ticks: { stepSize: 1, callback: (v) => res[v] ? res[v].algorithm.replace('_', ' ') : '' } }, y: yAxis },
    },
  });

  // across runs
  const recs = filtered(), labels = recs.map((r) => new Date(r.timestamp).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }));
  const ds = [];
  ALGS.forEach((a) => {
    const pick = (f) => recs.map((r) => { const x = r.results.find((y) => y.algorithm === a); return x ? Math.max(x[f], 1e-6) : null; });
    if (!pick('median_s').some((v) => v !== null)) return;
    const c = algColor(a);
    ds.push({ label: a + ' max', data: pick('max_s'), borderWidth: 0, pointRadius: 0, fill: '+1', backgroundColor: c + '30', _band: true });
    ds.push({ label: a + ' min', data: pick('min_s'), borderWidth: 0, pointRadius: 0, fill: false, _band: true });
    ds.push({ label: a, data: pick('median_s'), borderColor: c, backgroundColor: c, borderWidth: 2, pointRadius: 3, tension: 0.15, spanGaps: true });
  });
  charts.hist = new Chart($('histChart'), {
    type: 'line', data: { labels, datasets: ds },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'nearest', intersect: false },
      plugins: { legend: { display: false }, tooltip: { filter: (i) => !i.dataset._band, callbacks: { label: (c) => `${c.dataset.label} median: ${fmtT(c.parsed.y)}` } } },
      scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8, maxRotation: 0 } }, y: yAxis },
    },
  });
}
$('logToggle').onchange = renderCharts;
$('implFilter').onchange = renderCharts;

renderAll();
loadHistory().catch((e) => showError('Could not load history: ' + e.message));
poll();
})();
