// Demo endpoint configuration. Edit for deployment; app.js reads window.FALCON_CONFIG.
//
// apiBase: the Falcon edge that serves POST /generate and GET /serving/stats.
//   - local dev:   http://localhost:8001 (worker) or http://localhost (Nginx)
//   - deployed:    your Falcon URL, or a scale-to-zero endpoint's Falcon front
// When apiBase is unreachable, the demo falls back to a simulated stream so a cold
// GPU never shows a broken page (mirrors the graceful-fallback instinct of the old demo).
(function () {
  var local = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  window.FALCON_CONFIG = {
    apiBase: local ? 'http://localhost:8001' : '',
    model: 'Qwen/Qwen3-0.6B',
    maxTokens: 128,
    temperature: 0.7,
    statsIntervalMs: 2000,
  };
})();
