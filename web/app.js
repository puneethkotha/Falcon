(function () {
  const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? 'http://localhost/infer'
    : '';

  const input = document.getElementById('input-text');
  const btn = document.getElementById('analyze-btn');
  const result = document.getElementById('result');
  const errorEl = document.getElementById('error');

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

    document.getElementById('prob-neg').style.width = pNeg + '%';
    document.getElementById('prob-neg').style.background = '#f85149';
    document.getElementById('prob-neg-val').textContent = pNeg + '%';

    document.getElementById('prob-neu').style.width = pNeu + '%';
    document.getElementById('prob-neu').style.background = '#d29922';
    document.getElementById('prob-neu-val').textContent = pNeu + '%';

    document.getElementById('prob-pos').style.width = pPos + '%';
    document.getElementById('prob-pos').style.background = '#3fb950';
    document.getElementById('prob-pos-val').textContent = pPos + '%';

    document.getElementById('latency').textContent = Math.round(data.processing_time_ms || 0);
    document.getElementById('worker-id').textContent = data.worker_id || '-';

    const cacheEl = document.getElementById('cache-indicator');
    if (data.cache_hit) {
      cacheEl.classList.remove('hidden');
    } else {
      cacheEl.classList.add('hidden');
    }

    const demoNotice = document.getElementById('demo-mode-notice');
    demoNotice.classList.add('hidden');
  }

  function simulateInference(text) {
    const t = text.toLowerCase();
    let pos = 0.33, neg = 0.33, neu = 0.34;
    const posWords = ['great', 'excellent', 'amazing', 'love', 'best', 'good', 'fantastic'];
    const negWords = ['terrible', 'bad', 'worst', 'hate', 'poor', 'awful', 'disappointing'];

    posWords.forEach(w => { if (t.includes(w)) { pos += 0.15; neg -= 0.05; neu -= 0.1; } });
    negWords.forEach(w => { if (t.includes(w)) { neg += 0.15; pos -= 0.05; neu -= 0.1; } });

    const sum = pos + neg + neu;
    pos /= sum; neg /= sum; neu /= sum;

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

  async function analyze() {
    const text = input.value.trim();
    if (!text) return;

    btn.disabled = true;
    errorEl.classList.add('hidden');

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
          btn.disabled = false;
          return;
        }
      }
      const sim = simulateInference(text);
      showResult(sim);
      if (!API_BASE) {
        document.getElementById('demo-mode-notice').classList.remove('hidden');
      }
    } catch (e) {
      const sim = simulateInference(text);
      showResult(sim);
      document.getElementById('demo-mode-notice').classList.remove('hidden');
    } finally {
      btn.disabled = false;
    }
  }

  btn.addEventListener('click', analyze);

  if (input.value.trim()) {
    analyze();
  }
})();
