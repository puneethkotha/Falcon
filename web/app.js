(function () {
  const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? 'http://localhost/infer'
    : '';
  const HEALTH_URL = API_BASE ? 'http://localhost/healthz' : '';

  const input = document.getElementById('input-text');
  const btn = document.getElementById('analyze-btn');
  const result = document.getElementById('result');
  const errorEl = document.getElementById('error');
  const historyList = document.getElementById('history-list');

  function showResult(data) {
    errorEl.classList.add('hidden');
    result.classList.remove('hidden');

    const pred = (data.prediction || 'neutral').toLowerCase();
    document.getElementById('prediction-badge').textContent = pred;
    document.getElementById('prediction-badge').className = 'prediction-badge ' + pred;

    const conf = ((data.confidence || 0) * 100).toFixed(1);
    document.getElementById('confidence').textContent = conf;

    const probs = data.probabilities || { negative: 0.33, neutral: 0.34, positive: 0.33 };
    const pNeg = ((probs.negative || 0) * 100).toFixed(0);
    const pNeu = ((probs.neutral || 0) * 100).toFixed(0);
    const pPos = ((probs.positive || 0) * 100).toFixed(0);

    const probNeg = document.getElementById('prob-neg');
    const probNeu = document.getElementById('prob-neu');
    const probPos = document.getElementById('prob-pos');
    if (probNeg) { probNeg.style.width = pNeg + '%'; probNeg.style.minWidth = pNeg > 0 ? '4px' : '0'; }
    if (probNeu) { probNeu.style.width = pNeu + '%'; probNeu.style.minWidth = pNeu > 0 ? '4px' : '0'; }
    if (probPos) { probPos.style.width = pPos + '%'; probPos.style.minWidth = pPos > 0 ? '4px' : '0'; }

    document.getElementById('prob-neg-val').textContent = pNeg + '%';
    document.getElementById('prob-neu-val').textContent = pNeu + '%';
    document.getElementById('prob-pos-val').textContent = pPos + '%';

    document.getElementById('latency').textContent = Math.round(data.processing_time_ms || 0);
    document.getElementById('worker-id').textContent = data.worker_id || '-';

    const cacheEl = document.getElementById('cache-indicator');
    if (cacheEl) {
      cacheEl.classList.toggle('hidden', !data.cache_hit);
    }

    const demoNotice = document.getElementById('demo-mode-notice');
    if (demoNotice) {
      demoNotice.classList.toggle('hidden', !!API_BASE);
    }
  }

  function simulateInference(text) {
    const t = text.toLowerCase();
    let pos = 0.33, neg = 0.33, neu = 0.34;
    const posWords = ['great', 'excellent', 'amazing', 'love', 'best', 'good', 'fantastic', 'exceeded', 'quality', 'wonderful', 'perfect', 'awesome', 'outstanding', 'recommend', 'happy'];
    const negWords = ['terrible', 'bad', 'worst', 'hate', 'poor', 'awful', 'disappointing', 'waste', 'broken', 'disgusting', 'horrible', 'useless', 'garbage', 'rubbish', 'dreadful', 'pathetic'];

    posWords.forEach(function(w) {
      if (t.indexOf(w) !== -1) { pos += 0.15; neg -= 0.05; neu -= 0.1; }
    });
    negWords.forEach(function(w) {
      if (t.indexOf(w) !== -1) { neg += 0.15; pos -= 0.05; neu -= 0.1; }
    });

    const sum = pos + neg + neu;
    pos = pos / sum;
    neg = neg / sum;
    neu = neu / sum;

    const pred = pos > neg && pos > neu ? 'positive' : neg > pos && neg > neu ? 'negative' : 'neutral';
    const conf = Math.max(pos, neg, neu);

    return {
      prediction: pred,
      confidence: conf,
      probabilities: { negative: neg, neutral: neu, positive: pos },
      processing_time_ms: 25 + Math.random() * 15,
      worker_id: 'simulation',
      cache_hit: false
    };
  }

  function showError(msg) {
    result.classList.add('hidden');
    errorEl.classList.remove('hidden');
    document.getElementById('error-msg').textContent = msg;
  }

  function setLoading(loading) {
    btn.disabled = loading;
    const icon = btn.querySelector('i');
    if (icon) {
      icon.className = loading ? 'fas fa-spinner fa-spin' : 'fas fa-play';
    }
    btn.innerHTML = (loading ? '<i class="fas fa-spinner fa-spin"></i> ' : '<i class="fas fa-play"></i> ') + 'Analyze';
  }

  function addToHistory(text, pred, conf) {
    if (!historyList || !text) return;
    const item = document.createElement('div');
    item.className = 'history-item';
    item.innerHTML = '<span class="hist-pred ' + pred + '">' + pred + '</span> ' +
      '<span class="hist-text">' + escapeHtml(text.slice(0, 50)) + (text.length > 50 ? '...' : '') + '</span>';
    historyList.insertBefore(item, historyList.firstChild);
    if (historyList.children.length > 10) {
      historyList.removeChild(historyList.lastChild);
    }
  }

  function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  async function analyze() {
    const text = input.value.trim();
    if (!text) return;

    setLoading(true);
    errorEl.classList.add('hidden');

    var simData;
    try {
      if (API_BASE) {
        const res = await fetch(API_BASE, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text })
        });
        if (res.ok) {
          const data = await res.json();
          showResult(data);
          addToHistory(text, data.prediction, data.confidence);
          setLoading(false);
          return;
        }
      }
      simData = simulateInference(text);
      showResult(simData);
      addToHistory(text, simData.prediction, simData.confidence);
    } catch (err) {
      simData = simulateInference(text);
      showResult(simData);
      addToHistory(text, simData.prediction, simData.confidence);
    } finally {
      setLoading(false);
    }
  }

  btn.addEventListener('click', function() { analyze(); });

  var batchBtn = document.getElementById('batch-btn');
  var batchInput = document.getElementById('batch-input');
  var batchResult = document.getElementById('batch-result');
  if (batchBtn && batchInput && batchResult) {
    batchBtn.addEventListener('click', function() {
      var lines = batchInput.value.split('\n').map(function(s) { return s.trim(); }).filter(Boolean);
      if (!lines.length) return;
      batchResult.classList.remove('hidden');
      batchResult.innerHTML = '<p class="batch-loading"><i class="fas fa-spinner fa-spin"></i> Processing...</p>';
      setTimeout(function() {
        var out = [];
        lines.slice(0, 10).forEach(function(text) {
          var sim = simulateInference(text);
          out.push('<div class="batch-item"><span class="pred ' + sim.prediction + '">' + sim.prediction + '</span> ' + escapeHtml(text.slice(0, 60)) + (text.length > 60 ? '...' : '') + '</div>');
        });
        batchResult.innerHTML = out.join('') || '<p>No valid input</p>';
      }, 300);
    });
  }

  document.querySelectorAll('.sample-btn').forEach(function(el) {
    el.addEventListener('click', function() {
      input.value = this.dataset.text || '';
      analyze();
    });
  });

  var statusEl = document.getElementById('api-status');
  if (statusEl && HEALTH_URL) {
    fetch(HEALTH_URL).then(function(r) {
      statusEl.textContent = r.ok ? 'Online' : 'Unknown';
      statusEl.className = 'status-badge ' + (r.ok ? 'online' : '');
    }).catch(function() {
      statusEl.textContent = 'Offline';
      statusEl.className = 'status-badge offline';
    });
  }
})();
