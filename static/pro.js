(function(){var d=document,h=d.documentElement;
function st(k,v){try{localStorage.setItem(k,v)}catch(e){}}
/* theme toggle */
d.addEventListener('click',function(e){var b=e.target.closest('[data-theme-toggle]');if(!b)return;var dk=h.dataset.theme==='dark';h.dataset.theme=dk?'light':'dark';st('kt',dk?'light':'dark');b.textContent=dk?'🌙':'☀️'});
var tb=d.querySelector('[data-theme-toggle]');if(tb)tb.textContent=h.dataset.theme==='dark'?'☀️':'🌙';
/* active nav link */
var p=location.pathname;d.querySelectorAll('nav a.l').forEach(function(a){var u=a.getAttribute('href');if(u&&u!=='#'&&(u===p||(u.length>1&&p.indexOf(u)===0)))a.classList.add('active')});
/* flash: close button + auto fade */
d.querySelectorAll('main .flash').forEach(function(f){var x=d.createElement('button');x.type='button';x.setAttribute('aria-label','Close');x.textContent='×';x.onclick=function(){f.remove()};f.appendChild(x);setTimeout(function(){f.classList.add('out');setTimeout(function(){f.remove()},450)},f.classList.contains('err')?12000:7000)});
/* back to top */
var t=d.createElement('button');t.id='totop';t.type='button';t.setAttribute('aria-label','Top');t.textContent='↑';t.onclick=function(){window.scrollTo({top:0,behavior:'smooth'})};d.body.appendChild(t);
window.addEventListener('scroll',function(){t.classList.toggle('on',window.scrollY>500)},{passive:true});
/* prevent double submit */
d.addEventListener('submit',function(e){var f=e.target;if(f.dataset.busy){e.preventDefault();return}f.dataset.busy='1';setTimeout(function(){delete f.dataset.busy},4000)});
})();
/* phone: bottom bar active state + "More" sheet built from the top menu */
(function(){var d=document,p=location.pathname;
d.querySelectorAll('#bnav a').forEach(function(a){var u=a.getAttribute('href');if(u===p||(u.length>1&&p.indexOf(u)===0))a.classList.add('active')});
var s=d.getElementById('msheet');if(!s)return;
function build(){if(s.dataset.b)return;s.dataset.b='1';var seen={},g=d.createElement('div');g.className='ms-g';
 d.querySelectorAll('body>nav>a.l,body>nav>.dd .menu a').forEach(function(a){var h=a.getAttribute('href');if(!h||seen[h]||/^\/lang\//.test(h))return;seen[h]=1;var c=a.cloneNode(true),IC={'/farmer':'🏠','/distress':'📢','/verify':'✔','/gov':'📊','/imihigo':'🗺️','/distress/inbox':'📢','/support/inbox':'✉️','/notifications':'🔔'};
  if(!c.querySelector('i')&&IC[h]&&c.textContent.trim().indexOf(IC[h])!==0)c.insertAdjacentHTML('afterbegin','<i>'+IC[h]+'</i>&nbsp;');
  if(h==='/notifications'&&a.getAttribute('aria-label'))c.insertAdjacentHTML('beforeend','&nbsp;'+a.getAttribute('aria-label'));g.appendChild(c)});
 [['data-hc','◐ Contrast'],['data-zoom-m','A− Text'],['data-zoom-p','A+ Text']].forEach(function(x){var b=d.createElement('button');b.type='button';b.setAttribute(x[0].indexOf('zoom')>0?'data-zoom':x[0],x[0]==='data-zoom-m'?'-1':x[0]==='data-zoom-p'?'1':'');b.textContent=x[1];g.appendChild(b)});
 d.querySelectorAll('body>nav .menu form').forEach(function(f){g.appendChild(f.cloneNode(true))});
 var w=d.createElement('div');w.className='ms-in';w.innerHTML='<div class="ms-h"><b>☰ Menu</b><button type="button" data-close aria-label="Close">✕</button></div>';w.appendChild(g);s.appendChild(w)}
d.addEventListener('click',function(e){
 if(e.target.closest('[data-more]')){build();s.classList.add('on');return}
 if(s.classList.contains('on')){var a=e.target.closest('#msheet a');
  if(e.target===s||e.target.closest('[data-close]')){s.classList.remove('on');return}
  if(a&&a.hasAttribute('data-ka')){e.preventDefault();s.classList.remove('on');var f=d.getElementById('ka-fab');if(f)f.click()}}});
})();
