(function () {
  var CFG = window.FALCON_CONFIG || {};
  var API = CFG.apiBase || '';

  var els = {
    prompt: document.getElementById('prompt'),
    run: document.getElementById('run'),
    output: document.getElementById('output'),
    ttft: document.getElementById('m-ttft'),
    itl: document.getElementById('m-itl'),
    tokens: document.getElementById('m-tokens'),
    tps: document.getElementById('m-tps'),
    spark: document.getElementById('spark'),
    model: document.getElementById('model-id'),
    pMax: document.getElementById('p-maxtokens'),
    pTemp: document.getElementById('p-temp'),
    engineState: document.getElementById('engine-state'),
    cold: document.getElementById('coldstart'),
    kvArc: document.getElementById('kv-arc'),
    kvVal: document.getElementById('kv-val'),
    qRun: document.getElementById('q-running'),
    qWait: document.getElementById('q-waiting'),
  };

  els.model.textContent = CFG.model || 'model';
  els.pMax.textContent = CFG.maxTokens || 128;
  els.pTemp.textContent = CFG.temperature != null ? CFG.temperature : 0.7;

  var itlSeries = [];

  function fmt(n) { return n == null ? '--' : Math.round(n); }

  function resetMetrics() {
    els.output.innerHTML = '';
    els.ttft.textContent = '--';
    els.itl.textContent = '--';
    els.tokens.textContent = '0';
    els.tps.textContent = '--';
    itlSeries = [];
    drawSpark();
  }

  function drawSpark() {
    var c = els.spark;
    var w = c.clientWidth || 400, h = c.height;
    if (c.width !== w) c.width = w;
    var ctx = c.getContext('2d');
    ctx.clearRect(0, 0, w, h);
    if (itlSeries.length < 2) return;
    var max = Math.max.apply(null, itlSeries) || 1;
    ctx.beginPath();
    ctx.strokeStyle = '#E8A33D';
    ctx.lineWidth = 1.5;
    for (var i = 0; i < itlSeries.length; i++) {
      var x = (i / (itlSeries.length - 1)) * (w - 2) + 1;
      var y = h - 2 - (itlSeries[i] / max) * (h - 4);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  function parseSSE(buffer, onDelta) {
    // Returns the unconsumed tail; calls onDelta(text, usage, done) per frame.
    var parts = buffer.split('\n\n');
    var tail = parts.pop();
    for (var i = 0; i < parts.length; i++) {
      var line = parts[i].trim();
      if (line.indexOf('data:') !== 0) continue;
      var data = line.replace(/^data:\s*/, '');
      if (data === '[DONE]') { onDelta(null, null, true); continue; }
      try {
        var obj = JSON.parse(data);
        var delta = ((obj.choices || [{}])[0].delta || {}).content || '';
        onDelta(delta, obj.usage || null, false);
      } catch (e) { /* ignore keepalives */ }
    }
    return tail;
  }

  async function streamReal(prompt) {
    var t0 = performance.now();
    var first = null, last = t0, count = 0;
    var cursor = document.createElement('span');
    cursor.className = 'cursor';
    els.output.appendChild(cursor);

    var res = await fetch(API + '/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
      body: JSON.stringify({
        prompt: prompt,
        max_tokens: CFG.maxTokens || 128,
        temperature: CFG.temperature != null ? CFG.temperature : 0.7,
        stream: true,
      }),
    });
    if (!res.ok || !res.body) throw new Error('HTTP ' + res.status);

    var reader = res.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';
    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      buffer = parseSSE(buffer, function (delta, usage, done) {
        if (done) return;
        if (!delta) return;
        var now = performance.now();
        if (first === null) {
          first = now - t0;
          els.ttft.textContent = fmt(first);
        } else {
          var gap = now - last;
          els.itl.textContent = fmt(gap);
          itlSeries.push(gap);
          drawSpark();
        }
        last = now;
        count += 1;
        els.tokens.textContent = count;
        var secs = (now - t0) / 1000;
        if (secs > 0) els.tps.textContent = (count / secs).toFixed(1);
        cursor.insertAdjacentText('beforebegin', delta);
      });
    }
    cursor.remove();
  }

  // Simulated stream so the page never looks broken when the endpoint is cold/unreachable.
  function streamSim(prompt) {
    return new Promise(function (resolve) {
      var text = ('Falcon serves this token stream from a small language model behind ' +
        'Nginx, with the reliability chassis in the loop. This is simulated because the ' +
        'engine is unreachable from here.').split(' ');
      var t0 = performance.now(), first = null, last = t0, i = 0;
      var cursor = document.createElement('span');
      cursor.className = 'cursor';
      els.output.appendChild(cursor);
      var timer = setInterval(function () {
        var now = performance.now();
        if (first === null) { first = now - t0; els.ttft.textContent = fmt(first); }
        else { var gap = now - last; els.itl.textContent = fmt(gap); itlSeries.push(gap); drawSpark(); }
        last = now;
        cursor.insertAdjacentText('beforebegin', (i === 0 ? '' : ' ') + text[i]);
        i += 1;
        els.tokens.textContent = i;
        var secs = (now - t0) / 1000; if (secs > 0) els.tps.textContent = (i / secs).toFixed(1);
        if (i >= text.length) { clearInterval(timer); cursor.remove(); resolve(); }
      }, 45);
    });
  }

  async function run() {
    var prompt = (els.prompt.value || '').trim();
    if (!prompt) return;
    els.run.disabled = true;
    resetMetrics();
    try {
      if (API) { await streamReal(prompt); }
      else { await streamSim(prompt); }
    } catch (e) {
      els.cold.classList.remove('hidden');
      await streamSim(prompt);
    } finally {
      els.run.disabled = false;
    }
  }

  els.run.addEventListener('click', run);
  els.prompt.addEventListener('keydown', function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') run();
  });

  // Observability pane: poll engine serving stats (same-origin via Falcon).
  function setEngine(state, cls) {
    els.engineState.textContent = state;
    els.engineState.className = 'pill ' + cls;
  }

  async function pollStats() {
    if (!API) { setEngine('demo', 'pill-muted'); return; }
    try {
      var r = await fetch(API + '/serving/stats');
      if (!r.ok) throw new Error();
      var s = await r.json();
      setEngine('live', 'pill-live');
      if (s.kv_cache_pct != null) {
        els.kvVal.textContent = s.kv_cache_pct;
        var off = 157 - (Math.min(100, s.kv_cache_pct) / 100) * 157;
        els.kvArc.setAttribute('stroke-dashoffset', off);
      }
      els.qRun.textContent = s.running != null ? s.running : '--';
      els.qWait.textContent = s.waiting != null ? s.waiting : '--';
    } catch (e) {
      setEngine('offline', 'pill-off');
    }
  }
  pollStats();
  setInterval(pollStats, CFG.statsIntervalMs || 2000);
  window.addEventListener('resize', drawSpark);
})();
