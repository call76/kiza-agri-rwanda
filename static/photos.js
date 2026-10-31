/* Real photos from Wikimedia Commons (free licences). Every photo shows its author + licence and links to the source page. Needs internet; hides itself offline. */
window.KZ = window.KZ || {};
(function () {
  var cache = {};
  function txt(h) { try { return new DOMParser().parseFromString(h || '', 'text/html').body.textContent.trim(); } catch (e) { return ''; } }
  KZ.photos = function (query, n) {
    var k = query + '|' + n; if (cache[k]) return Promise.resolve(cache[k]);
    var u = 'https://commons.wikimedia.org/w/api.php?action=query&format=json&origin=*&generator=search&gsrnamespace=6&gsrlimit=40&gsrsearch=' + encodeURIComponent(query + ' filetype:bitmap') +
      '&prop=imageinfo&iiprop=url|mime|extmetadata&iiurlwidth=520&iiextmetadatafilter=Artist|LicenseShortName|ImageDescription';
    return fetch(u).then(function (r) { return r.json(); }).then(function (j) {
      var pg = (j.query || {}).pages || {};
      var p = Object.keys(pg).map(function (i) { return pg[i]; }).filter(function (p) { var ii = p.imageinfo && p.imageinfo[0]; return ii && ii.thumburl && /jpeg/.test(ii.mime || ''); }).slice(0, n);
      return (cache[k] = p);
    });
  };
  KZ.fig = function (x, h) {
    var ii = x.imageinfo[0], m = ii.extmetadata || {}, a = txt((m.Artist || {}).value) || 'Wikimedia Commons', l = txt((m.LicenseShortName || {}).value), d = txt((m.ImageDescription || {}).value).slice(0, 90);
    var f = document.createElement('figure'); f.style.cssText = 'margin:0;border-radius:14px;overflow:hidden;background:#f3f7f4;box-shadow:0 2px 10px #0001';
    var im = document.createElement('img'); im.src = ii.thumburl; im.loading = 'lazy'; im.alt = d || x.title; im.style.cssText = 'width:100%;height:' + (h || 170) + 'px;object-fit:cover;display:block'; im.onerror = function () { f.remove(); };
    var c = document.createElement('figcaption'); c.style.cssText = 'padding:6px 9px;font-size:11.5px;line-height:1.35';
    var lk = document.createElement('a'); lk.href = ii.descriptionurl || '#'; lk.target = '_blank'; lk.rel = 'noopener noreferrer'; lk.textContent = (a.length > 44 ? a.slice(0, 44) + '…' : a) + (l ? ' · ' + l : '');
    c.appendChild(lk); f.appendChild(im); f.appendChild(c); return f;
  };
  /* <div data-kz-strip="query" data-n="4"> fills itself; stays hidden if offline */
  KZ.strips = function () {
    [].forEach.call(document.querySelectorAll('[data-kz-strip]'), function (el) {
      el.style.display = 'none';
      KZ.photos(el.dataset.kzStrip, +el.dataset.n || 4).then(function (p) { if (!p.length) return; el.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px;margin:12px 0'; p.forEach(function (x) { el.appendChild(KZ.fig(x, 120)); }); }).catch(function () { });
    });
  };
  if (document.readyState !== 'loading') KZ.strips(); else document.addEventListener('DOMContentLoaded', KZ.strips);
})();
