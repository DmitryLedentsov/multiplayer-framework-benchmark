const B = '/benchmark/api';
let presets = {};
let active = null;

const $ = id => document.getElementById(id);
const num = (v, d = 2) => v == null || !Number.isFinite(Number(v)) ? '—' : Number(v).toFixed(d);
const latency = v => {
  if (v == null || !Number.isFinite(Number(v))) return '—';
  const n = Number(v);
  return n < 0.01 ? `${(n * 1000).toFixed(1)} µs` : n < 1 ? `${n.toFixed(3)} ms` : `${n.toFixed(2)} ms`;
};

const toast = t => {
  const e = $('toast');
  e.textContent = t;
  e.classList.add('show');
  setTimeout(() => e.classList.remove('show'), 2500);
};

async function api(path, opt = {}) {
  const r = await fetch(B + path, {
    headers: {'Content-Type': 'application/json'},
    ...opt,
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(d.detail || `HTTP ${r.status}`);
  return d;
}

function values() {
  return {
    name: $('name').value.trim() || 'manual',
    runtimes: [...$('runtimes').selectedOptions].map(x => x.value),
    session_levels: $('sessions').value.split(',').map(x => Number(x.trim())).filter(x => x > 0),
    action_rate: +$('actionRate').value,
    tick_rate: +$('tickRate').value,
    publication_rate: +$('publicationRate').value,
    workers: +$('workers').value,
    capacity: +$('capacity').value,
    budget: +$('budget').value,
    warmup_seconds: +$('warmup').value,
    measurement_seconds: +$('measurement').value,
    repetitions: +$('repetitions').value,
    producer_threads: +$('producerThreads').value,
    sample_interval_ms: 1000,
    randomize_order: $('randomize').checked,
    order_seed: +$('seed').value,
    mode: 'factorial',
  };
}

function apply(c) {
  $('name').value = c.name;
  $('sessions').value = c.session_levels.join(',');
  $('actionRate').value = c.action_rate;
  $('tickRate').value = c.tick_rate;
  $('publicationRate').value = c.publication_rate;
  $('workers').value = c.workers;
  $('capacity').value = c.capacity;
  $('budget').value = c.budget;
  $('warmup').value = c.warmup_seconds;
  $('measurement').value = c.measurement_seconds;
  $('repetitions').value = c.repetitions;
  $('producerThreads').value = c.producer_threads;
  $('seed').value = c.order_seed;
  $('randomize').checked = c.randomize_order;
  [...$('runtimes').options].forEach(o => o.selected = c.runtimes.includes(o.value));
  estimate();
}

function estimate() {
  const v = values();
  const runs = v.runtimes.length * v.session_levels.length * v.repetitions;
  const sec = runs * (v.warmup_seconds + v.measurement_seconds);
  $('estimate').textContent = `${runs} JVM-прогонов · ≈ ${(sec / 3600).toFixed(1)} ч чистого времени`;
}

$('preset').onchange = () => {
  if ($('preset').value !== 'custom') apply(presets[$('preset').value]);
};
$('form').oninput = estimate;
$('form').onsubmit = async e => {
  e.preventDefault();
  try {
    const d = await api('/experiments', {method: 'POST', body: JSON.stringify(values())});
    toast('Эксперимент запущен');
    active = d.id;
    await refresh();
  } catch (err) {
    toast(err.message);
  }
};
$('stop').onclick = async () => {
  if (!active) return;
  try {
    await api(`/experiments/${active}/stop`, {method: 'POST'});
    toast('Остановка запрошена');
  } catch (e) {
    toast(e.message);
  }
};
$('refresh').onclick = refresh;

function metric(name, value) {
  return `<div class="metric"><span>${name}</span><b>${value}</b></div>`;
}

async function refresh() {
  try {
    const d = await api('/experiments');
    const a = d.active;
    active = a?.manifest?.id || null;
    $('stop').disabled = !active;

    if (a) {
      const s = a.status || {};
      $('currentHint').textContent = `${a.manifest.request.name} · ${s.status}`;
      $('current').innerHTML =
        metric('Статус', s.status) +
        metric('Готово', `${s.completedRuns || 0}/${s.totalRuns || 0}`) +
        metric('Failed', s.failedRuns || 0) +
        metric('Runtime', s.currentRun?.runtime || '—') +
        metric('Sessions', s.currentRun?.sessions || '—');
    } else {
      $('currentHint').textContent = 'Нет активного эксперимента';
      $('current').innerHTML = '';
    }

    $('history').innerHTML = (d.items || []).map(x => `
      <div class="history-row">
        <div><b>${x.name}</b><div class="muted">${x.id}</div></div>
        <span class="pill ${x.status}">${x.status}</span>
        <span>${x.completedRuns}/${x.totalRuns}</span>
        <span>${x.createdAt ? new Date(x.createdAt).toLocaleString('ru-RU') : '—'}</span>
        <button data-open="${x.id}">Открыть</button>
      </div>
    `).join('') || '<p class="muted">Прогонов пока нет.</p>';

    document.querySelectorAll('[data-open]').forEach(b => {
      b.onclick = () => openExperiment(b.dataset.open);
    });
  } catch (e) {
    toast(e.message);
  }
}

function svgEscape(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function runChart(runs, options) {
  const {
    title,
    yLabel,
    metricKey,
    threshold = null,
    thresholdLabel = null,
    scale = 1,
    cpu = false,
  } = options;

  const completed = (runs || []).filter(row => Number.isFinite(Number(row.repetition)));
  const repetitions = [...new Set(completed.map(row => Number(row.repetition)))].sort((a, b) => a - b);
  const runtimes = [...new Set(completed.map(row => String(row.runtime)))].sort();
  if (!completed.length || !repetitions.length || !runtimes.length) {
    return '<div class="muted">Нет данных для графика.</div>';
  }

  const palette = ['#2563eb', '#dc2626', '#16a34a', '#7c3aed', '#ea580c', '#0891b2'];
  const series = [];
  runtimes.forEach((runtime, runtimeIndex) => {
    if (cpu) {
      series.push({
        runtime,
        key: 'cpuPercent',
        label: `${runtime} JVM`,
        color: palette[runtimeIndex % palette.length],
        dashed: false,
      });
      series.push({
        runtime,
        key: 'generatorCpuPercent',
        label: `${runtime} generator`,
        color: palette[runtimeIndex % palette.length],
        dashed: true,
      });
    } else {
      series.push({
        runtime,
        key: metricKey,
        label: runtime,
        color: palette[runtimeIndex % palette.length],
        dashed: false,
      });
    }
  });

  const values = [];
  for (const row of completed) {
    for (const s of series) {
      if (String(row.runtime) !== s.runtime) continue;
      const value = Number(row[s.key]);
      if (Number.isFinite(value) && (!s.key.includes('generator') || value >= 0)) {
        values.push(value * scale);
      }
    }
  }
  if (!values.length) return '<div class="muted">Нет данных для графика.</div>';

  const width = 900;
  const height = 500;
  const left = 80;
  const right = 30;
  const top = 45;
  const legendRows = Math.ceil(series.length / 4);
  const bottom = 65 + Math.max(0, legendRows - 1) * 16;
  const dataMax = Math.max(...values);
  const thresholdValue = threshold == null ? null : Number(threshold) * scale;
  const thresholdOnScale = thresholdValue != null && thresholdValue <= Math.max(dataMax * 2.5, 1e-9);
  let maxY = Math.max(dataMax * 1.15, 1e-6);
  if (thresholdOnScale) maxY = Math.max(maxY, thresholdValue * 1.12);

  const minX = Math.min(...repetitions);
  const maxX = Math.max(...repetitions);
  const singleX = minX === maxX;
  const plotMinX = singleX ? minX - 1 : minX;
  const plotMaxX = singleX ? maxX + 1 : maxX;
  const px = x => left + (x - plotMinX) / (plotMaxX - plotMinX) * (width - left - right);
  const py = y => top + (1 - y / maxY) * (height - top - bottom);
  const fmt = value => {
    if (maxY < 0.01) return value.toFixed(3);
    if (maxY < 1) return value.toFixed(2);
    if (maxY < 10) return value.toFixed(1);
    return value.toFixed(0);
  };

  const parts = [
    `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${svgEscape(title)}" style="width:100%;display:block;background:white;border-radius:8px">`,
    '<rect width="100%" height="100%" fill="white"/>',
    `<text x="${width / 2}" y="26" text-anchor="middle" font-family="sans-serif" font-size="18" fill="#111827">${svgEscape(title)}</text>`,
  ];

  for (let i = 0; i < 6; i++) {
    const value = maxY * i / 5;
    const y = py(value);
    parts.push(`<line x1="${left}" y1="${y.toFixed(2)}" x2="${width - right}" y2="${y.toFixed(2)}" stroke="#e5e7eb"/>`);
    parts.push(`<text x="${left - 10}" y="${(y + 4).toFixed(2)}" text-anchor="end" font-family="sans-serif" font-size="11" fill="#111827">${fmt(value)}</text>`);
  }

  for (const repetition of repetitions) {
    const x = px(repetition);
    parts.push(`<text x="${x.toFixed(2)}" y="${height - bottom + 22}" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#111827">${repetition}</text>`);
  }

  parts.push(`<line x1="${left}" y1="${top}" x2="${left}" y2="${height - bottom}" stroke="#111827"/>`);
  parts.push(`<line x1="${left}" y1="${height - bottom}" x2="${width - right}" y2="${height - bottom}" stroke="#111827"/>`);
  parts.push(`<text x="${width / 2}" y="${height - 18}" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#111827">JVM run / repetition</text>`);
  parts.push(`<text x="18" y="${height / 2}" transform="rotate(-90 18 ${height / 2})" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#111827">${svgEscape(yLabel)}</text>`);

  if (thresholdValue != null) {
    if (thresholdOnScale) {
      const y = py(thresholdValue);
      parts.push(`<line x1="${left}" y1="${y.toFixed(2)}" x2="${width - right}" y2="${y.toFixed(2)}" stroke="#111827" stroke-dasharray="6 5"/>`);
      parts.push(`<text x="${width - right - 4}" y="${(y - 6).toFixed(2)}" text-anchor="end" font-family="sans-serif" font-size="11" fill="#111827">threshold ${svgEscape(thresholdLabel ?? thresholdValue)}</text>`);
    } else {
      parts.push(`<text x="${width - right}" y="${top + 12}" text-anchor="end" font-family="sans-serif" font-size="11" fill="#6b7280">threshold ${svgEscape(thresholdLabel ?? thresholdValue)} · off scale</text>`);
    }
  }

  for (let seriesIndex = 0; seriesIndex < series.length; seriesIndex++) {
    const s = series[seriesIndex];
    const rows = completed
      .filter(row => String(row.runtime) === s.runtime && Number.isFinite(Number(row[s.key])))
      .filter(row => !s.key.includes('generator') || Number(row[s.key]) >= 0)
      .sort((a, b) => Number(a.repetition) - Number(b.repetition));
    if (!rows.length) continue;

    const points = rows.map(row => `${px(Number(row.repetition)).toFixed(2)},${py(Number(row[s.key]) * scale).toFixed(2)}`).join(' ');
    parts.push(`<polyline points="${points}" fill="none" stroke="${s.color}" stroke-width="2.5"${s.dashed ? ' stroke-dasharray="7 5"' : ''}/>`);

    for (const row of rows) {
      const x = px(Number(row.repetition));
      const y = py(Number(row[s.key]) * scale);
      parts.push(`<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="4.5" fill="${s.color}"/>`);
      if (series.length === 1 && repetitions.length <= 12) {
        const value = Number(row[s.key]) * scale;
        parts.push(`<text x="${(x + 7).toFixed(2)}" y="${Math.max(top + 12, y - 7).toFixed(2)}" font-family="sans-serif" font-size="10" fill="#111827">${fmt(value)}</text>`);
      }
    }

    const legendX = left + (seriesIndex % 4) * 190;
    const legendY = height - 42 + Math.floor(seriesIndex / 4) * 16;
    parts.push(`<line x1="${legendX}" y1="${legendY}" x2="${legendX + 24}" y2="${legendY}" stroke="${s.color}" stroke-width="3"${s.dashed ? ' stroke-dasharray="7 5"' : ''}/>`);
    parts.push(`<text x="${legendX + 30}" y="${legendY + 4}" font-family="sans-serif" font-size="11" fill="#111827">${svgEscape(s.label)}</text>`);
  }

  parts.push('</svg>');
  return parts.join('');
}

function experimentPlots(id, analysis, request) {
  const sessionLevels = request.session_levels || [];
  if (sessionLevels.length > 1) {
    return `
      <img style="width:100%;background:white;border-radius:8px" src="${B}/experiments/${id}/file/plots/step-p99-vs-sessions.svg">
      <img style="width:100%;background:white;border-radius:8px" src="${B}/experiments/${id}/file/plots/action-p99-vs-sessions.svg">
      <img style="width:100%;background:white;border-radius:8px" src="${B}/experiments/${id}/file/plots/cpu-vs-sessions.svg">
    `;
  }

  const runs = analysis.runs || [];
  const stepValues = runs.map(row => Number(row.stepP99Ms)).filter(Number.isFinite);
  const stepMaxMs = stepValues.length ? Math.max(...stepValues) : 0;
  const stepInMicros = stepMaxMs > 0 && stepMaxMs < 0.1;
  const stepScale = stepInMicros ? 1000 : 1;
  const stepUnit = stepInMicros ? 'µs' : 'ms';

  return [
    runChart(runs, {
      title: 'p99 simulation-step lateness by run',
      yLabel: `p99 step lateness, ${stepUnit}`,
      metricKey: 'stepP99Ms',
      threshold: analysis.sustainThresholds.stepP99Ms,
      thresholdLabel: `${analysis.sustainThresholds.stepP99Ms} ms`,
      scale: stepScale,
    }),
    runChart(runs, {
      title: 'p99 Action latency by run',
      yLabel: 'p99 Action latency, ms',
      metricKey: 'actionP99Ms',
      threshold: analysis.sustainThresholds.actionP99Ms,
      thresholdLabel: `${analysis.sustainThresholds.actionP99Ms} ms`,
    }),
    runChart(runs, {
      title: 'CPU by run',
      yLabel: 'CPU, % host budget',
      cpu: true,
    }),
  ].join('');
}

async function openExperiment(id) {
  try {
    const d = await api(`/experiments/${id}`);
    const a = d.analysis;
    if (!a) {
      $('analysis').innerHTML = '<p class="muted">Анализ появится после завершения хотя бы одного успешного прогона.</p>';
      return;
    }

    const rows = a.groups || [];
    const req = d.manifest?.request || {};
    const oneSession = req.session_levels?.length === 1 ? req.session_levels[0] : null;
    const perSession = oneSession && req.action_rate != null ? req.action_rate / oneSession : null;
    const plots = experimentPlots(id, a, req);

    $('analysis').innerHTML = `
      <div class="thresholds">
        <span>Нагрузка: ${req.action_rate ?? '—'} Actions/s суммарно${perSession != null ? ` (~${num(perSession, 1)} на session)` : ''}</span>
        <span>sessions: ${(req.session_levels || []).join(', ') || '—'}</span>
        <span>p99 step &lt; ${a.sustainThresholds.stepP99Ms} ms</span>
        <span>p99 Action &lt; ${a.sustainThresholds.actionP99Ms} ms</span>
        <span>reject &lt; ${(a.sustainThresholds.maxRejectionRate * 100).toFixed(2)}%</span>
        <span>tick ≥ ${(a.sustainThresholds.minTickFraction * 100).toFixed(0)}%</span>
      </div>
      <table>
        <thead>
          <tr><th>Runtime</th><th>Sessions</th><th>Runs</th><th>Failed</th><th>p99 Action</th><th>p99 step</th><th>CPU, %</th><th>Generator CPU, %</th><th>Actions/s</th><th>Sustained</th></tr>
        </thead>
        <tbody>
          ${rows.map(r => `<tr><td>${r.runtime}</td><td>${r.sessions}</td><td>${r.n}/${r.plannedRuns}</td><td>${r.failedRuns}</td><td>${latency(r.actionP99Median)}</td><td>${latency(r.stepP99Median)}</td><td>${num(r.cpuMedian, 1)}</td><td>${num(r.generatorCpuMedian, 1)}</td><td>${r.actionsPerSecondMedian == null ? '—' : Math.round(r.actionsPerSecondMedian)}</td><td>${r.sustained ? 'yes' : 'no'}</td></tr>`).join('')}
        </tbody>
      </table>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px;margin-top:16px">${plots}</div>
      <p><a href="${B}/experiments/${id}/file/analysis.csv">analysis.csv</a> · <a href="${B}/experiments/${id}/file/checksums.sha256">SHA-256</a></p>
    `;
  } catch (e) {
    toast(e.message);
  }
}

(async () => {
  try {
    const c = await api('/config');
    presets = c.presets;
    apply(c.defaults);
    await refresh();
    setInterval(refresh, 3000);
  } catch (e) {
    toast(e.message);
  }
})();