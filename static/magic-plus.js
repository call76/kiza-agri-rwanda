/* KIZA MAGIC+ — quick navigation, offline awareness, install help, and back-to-top. */
(function () {
  'use strict';
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var lang = (document.documentElement.lang || 'en').toLowerCase();
  var rw = lang === 'rw';
  var labels = rw
    ? {search:'Shakisha muri Kiza Agri',hint:'Andika icyo ushaka…',empty:'Nta gikorwa gihuye n’ishakisha.',online:'Wongeye kubona internet.',offline:'Uri offline. Amakuru amwe ashobora kutaboneka.',install:'Shyira Kiza Agri kuri telefone cyangwa mudasobwa',back:'Subira hejuru',close:'Funga'}
    : {search:'Search Kiza Agri',hint:'Search pages and tools…',empty:'No matching tools found.',online:'You are back online.',offline:'You are offline. Some features may be unavailable.',install:'Install Kiza Agri on this device',back:'Back to top',close:'Close'};
  var style = document.createElement('style');
  style.textContent = `
  #kz-magic-launch{position:fixed;left:16px;bottom:22px;z-index:65;border:1px solid rgba(212,175,55,.55);border-radius:999px;padding:10px 15px;background:linear-gradient(135deg,#082b1b,#08784e);color:#fff;font:800 12px Manrope,system-ui;letter-spacing:.3px;box-shadow:0 10px 30px #052b1d55;cursor:pointer}
  #kz-magic-launch:hover{transform:translateY(-2px);box-shadow:0 14px 34px #052b1d77}
  #kz-magic-panel{display:none;position:fixed;inset:0;z-index:120;background:#06140e99;backdrop-filter:blur(8px);align-items:flex-start;justify-content:center;padding: min(13vh,100px) 14px 20px}
  #kz-magic-panel.open{display:flex}
  #kz-magic-dialog{width:min(620px,100%);max-height:75vh;overflow:hidden;border:1px solid rgba(16,185,129,.3);border-radius:22px;background:var(--mg-glass,#fff);color:inherit;box-shadow:0 30px 90px #0008}
  #kz-magic-head{padding:16px 18px;border-bottom:1px solid var(--mg-bd, #ddd);display:flex;justify-content:space-between;align-items:center;font-weight:800}
  #kz-magic-search{width:calc(100% - 28px);margin:14px;padding:13px 15px;border:1px solid var(--mg-bd,#ddd);background:transparent;color:inherit;font:600 15px Manrope,system-ui}
  #kz-magic-results{padding:0 12px 14px;overflow:auto;max-height:48vh}
  .kz-magic-link{display:flex;gap:12px;align-items:center;padding:11px 13px;border-radius:13px;text-decoration:none;color:inherit;font-weight:700}
  .kz-magic-link:hover,.kz-magic-link:focus{background:rgba(16,185,129,.13);outline:2px solid #10b981}
  .kz-magic-link small{display:block;opacity:.65;font-weight:500}
  #kz-magic-empty{padding:20px;text-align:center;opacity:.65}
  #kz-net-status{position:fixed;top:12px;left:50%;transform:translate(-50%,-150%);z-index:130;padding:10px 16px;border-radius:999px;background:#123d2a;color:white;font:700 12px Manrope,system-ui;box-shadow:0 8px 30px #0004;transition:transform .25s}
  #kz-net-status.show{transform:translate(-50%,0)}
  #kz-backtop{position:fixed;right:16px;bottom:22px;z-index:55;width:44px;height:44px;border:1px solid var(--mg-bd,#ddd);border-radius:50%;background:var(--mg-glass,#fff);color:inherit;font-size:20px;box-shadow:0 8px 24px #0002;display:none;cursor:pointer}
  #kz-backtop.show{display:block}
  #kz-install{position:fixed;left:16px;bottom:74px;z-index:64;border:0;border-radius:999px;padding:10px 14px;background:#d4af37;color:#092719;font:800 12px Manrope,system-ui;box-shadow:0 8px 24px #0003;display:none;cursor:pointer}
  #kz-install.show{display:block}
  @media(max-width:640px){#kz-magic-launch{bottom:86px;left:10px}#kz-backtop{bottom:86px;right:10px}#kz-install{bottom:138px;left:10px}}
  `;
  document.head.appendChild(style);

  var links = [];
  document.querySelectorAll('nav a[href],#bnav a[href],#msheet a[href]').forEach(function (a) {
    var href = a.getAttribute('href'), text = (a.innerText || a.textContent || '').trim().replace(/\s+/g, ' ');
    if (!href || href.charAt(0) === '#' || href.indexOf('javascript:') === 0 || !text) return;
    if (!links.some(function (x) { return x.href === href; })) links.push({href: href, text: text});
  });
  // Useful tools already supported by the app, exposed in one searchable place.
  var extra = [
    ['/farmer','🌾','Farmer dashboard'], ['/farms','🚜','My farms'], ['/weather','⛅','Weather forecast'],
    ['/soil','🌱','Soil health'], ['/scan','🔬','Crop doctor / scanner'], ['/fertilizer','🧪','Fertilizer guide'],
    ['/market','🛒','Marketplace'], ['/prices','📈','Market prices'], ['/profit','💹','Profit calculator'],
    ['/calendar','🗓️','Planting calendar'], ['/learning','🎓','Learning center'], ['/support','🛟','Help center']
  ];
  extra.forEach(function (x) {
    if (!links.some(function (l) { return l.href === x[0]; })) links.push({href:x[0],text:x[1]+' '+x[2]});
  });

  var launch = document.createElement('button');
  launch.id = 'kz-magic-launch'; launch.type = 'button';
  launch.textContent = '✦ KIZA MAGIC'; launch.setAttribute('aria-haspopup','dialog');
  launch.setAttribute('aria-label', labels.search + ' (Ctrl+K)');
  document.body.appendChild(launch);

  var panel = document.createElement('div');
  panel.id = 'kz-magic-panel';
  panel.innerHTML = '<div id="kz-magic-dialog" role="dialog" aria-modal="true" aria-label="'+labels.search+'"><div id="kz-magic-head"><span>✦ '+labels.search+'</span><span style="opacity:.6;font-size:12px">CTRL K · ESC</span></div><input id="kz-magic-search" type="search" autocomplete="off" placeholder="'+labels.hint+'"><div id="kz-magic-results" role="listbox"></div></div>';
  document.body.appendChild(panel);
  var input = panel.querySelector('input'), results = panel.querySelector('#kz-magic-results');
  function render(q) {
    q = (q || '').toLowerCase().trim();
    var found = links.filter(function (l) { return !q || l.text.toLowerCase().indexOf(q) >= 0 || l.href.toLowerCase().indexOf(q) >= 0; }).slice(0,16);
    results.innerHTML = '';
    if (!found.length) { var empty=document.createElement('div');empty.id='kz-magic-empty';empty.textContent=labels.empty;results.appendChild(empty);return; }
    found.forEach(function (l) {
      var a=document.createElement('a');a.className='kz-magic-link';a.href=l.href;
      var title=document.createElement('span');title.textContent=l.text;
      var sub=document.createElement('small');sub.textContent=l.href;
      var wrap=document.createElement('span');wrap.appendChild(title);wrap.appendChild(sub);a.appendChild(wrap);results.appendChild(a);
    });
  }
  function open(){panel.classList.add('open');input.value='';render('');window.setTimeout(function(){input.focus();},20);}
  function close(){panel.classList.remove('open');launch.focus();}
  launch.addEventListener('click',open);
  panel.addEventListener('click',function(e){if(e.target===panel)close();});
  input.addEventListener('input',function(){render(input.value);});
  document.addEventListener('keydown',function(e){
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase()==='k') {e.preventDefault();panel.classList.contains('open')?close():open();}
    if(e.key==='Escape'&&panel.classList.contains('open'))close();
  });

  var net=document.createElement('div');net.id='kz-net-status';net.setAttribute('role','status');document.body.appendChild(net);
  var netTimer;
  function notify(text){net.textContent=text;net.classList.add('show');clearTimeout(netTimer);netTimer=setTimeout(function(){net.classList.remove('show');},2600);}
  window.addEventListener('offline',function(){notify('⚠ '+labels.offline);});
  window.addEventListener('online',function(){notify('✓ '+labels.online);});

  var top=document.createElement('button');top.id='kz-backtop';top.type='button';top.textContent='↑';top.title=labels.back;top.setAttribute('aria-label',labels.back);document.body.appendChild(top);
  window.addEventListener('scroll',function(){top.classList.toggle('show',window.scrollY>500);},{passive:true});
  top.addEventListener('click',function(){window.scrollTo({top:0,behavior:reduced?'auto':'smooth'});});

  var deferred=null;
  window.addEventListener('beforeinstallprompt',function(e){e.preventDefault();deferred=e;var b=document.createElement('button');b.id='kz-install';b.type='button';b.textContent='＋ '+(rw?'Shyira kuri telefone':'Install app');b.title=labels.install;document.body.appendChild(b);b.classList.add('show');b.addEventListener('click',function(){if(!deferred)return;deferred.prompt();deferred.userChoice.then(function(){deferred=null;b.remove();});});});
  if('serviceWorker' in navigator && location.protocol.indexOf('http')===0){window.addEventListener('load',function(){navigator.serviceWorker.register('/sw.js').catch(function(){});});}
})();
