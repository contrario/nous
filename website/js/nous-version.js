// NOUS version display -- fetches /v1/health and rewrites [data-nous-version] elements.
// Graceful degradation: on failure, keeps server-rendered fallback in HTML.
(function () {
  try {
    fetch('/v1/health', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && typeof d.version === 'string') {
          var els = document.querySelectorAll('[data-nous-version]');
          for (var i = 0; i < els.length; i++) {
            els[i].textContent = 'v' + d.version;
          }
        }
      })
      .catch(function () { /* keep fallback */ });
  } catch (e) { /* keep fallback */ }
})();
