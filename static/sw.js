/* KIZA-AGRI service worker: instant repeat loads for static files, friendly offline page. Pages and personal data are never cached. */
var V='kiza-v18',STATIC=['/static/style.css','/static/ui.css','/static/pro.css','/static/landing.css','/static/ui.js','/static/v10.css','/static/v10.js','/static/v11.css','/static/v11.js','/static/v11-auth.js','/static/magic.css','/static/magic.js','/static/magic-plus.js','/static/pro.js','/static/icon-192.png'];
self.addEventListener('install',function(e){e.waitUntil(caches.open(V).then(function(c){return c.addAll(STATIC.concat(['/offline']))}).then(function(){return self.skipWaiting()}))});
self.addEventListener('activate',function(e){e.waitUntil(caches.keys().then(function(k){return Promise.all(k.filter(function(x){return x!==V}).map(function(x){return caches.delete(x)}))}).then(function(){return self.clients.claim()}))});
self.addEventListener('fetch',function(e){var r=e.request,u=new URL(r.url);if(r.method!=='GET'||u.origin!==location.origin)return;
 if(u.pathname.indexOf('/static/')===0){e.respondWith(caches.open(V).then(function(c){return c.match(r).then(function(h){var f=fetch(r).then(function(n){if(n.ok)c.put(r,n.clone());return n}).catch(function(){return h});return h||f})}));return}
 if(r.mode==='navigate'){e.respondWith(fetch(r).catch(function(){return caches.match('/offline')}))}});
