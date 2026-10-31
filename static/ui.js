(function(){
var d=document,h=d.documentElement,ls=window.localStorage||{};
function g(k){try{return ls.getItem(k)}catch(e){return null}}function s(k,v){try{ls.setItem(k,v)}catch(e){}}
if(g('kc'))h.dataset.hc='1';if(g('kf'))h.dataset.fs=g('kf');
d.addEventListener('click',function(e){
 var t=e.target.closest('.dd>button.dt');
 d.querySelectorAll('.dd.open').forEach(function(x){if(!t||x!==t.parentNode)x.classList.remove('open')});
 if(t){t.parentNode.classList.toggle('open');t.setAttribute('aria-expanded',t.parentNode.classList.contains('open'))}
 if(e.target.closest('.menu-btn'))d.querySelector('.top nav').classList.toggle('show');
});
var io=window.IntersectionObserver&&new IntersectionObserver(function(es){es.forEach(function(x){if(x.isIntersecting){x.target.classList.add('in');io.unobserve(x.target)}})},{threshold:.1});
d.querySelectorAll('.rv').forEach(function(e){io?io.observe(e):e.classList.add('in')});
/* assistant (v10): history, markdown-lite, typing dots, mic, new chat */
var box=d.getElementById('ka-box');if(!box)return;
var log=d.getElementById('ka-log'),chips=d.getElementById('ka-chips'),form=d.getElementById('ka-form'),inp=form.q,fab=d.getElementById('ka-fab'),mic=d.getElementById('ka-mic'),hist=[],busy=false;
try{hist=JSON.parse(sessionStorage.getItem('kh')||'[]')}catch(e){}
function save(){try{sessionStorage.setItem('kh',JSON.stringify(hist.slice(-20)))}catch(e){}}
function esc(t){return String(t).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function md(t){t=esc(t).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/(^|\n)\s*[-*•]\s+/g,'$1• ').replace(/\n/g,'<br>');return t.replace(/(^|[\s(>])(\/[a-z][a-z0-9\/_-]*)/g,'$1<a class="in" href="$2">$2</a>')}
function add(c,html,raw){var m=d.createElement('div');m.className='km '+c;m.innerHTML=html;log.appendChild(m);log.scrollTop=log.scrollHeight;return m}
function setChips(a){chips.innerHTML='';(a||[]).forEach(function(c){var b=d.createElement('button');b.type='button';b.textContent=c;b.onclick=function(){ask(c)};chips.appendChild(b)})}
function ask(q){if(busy)return;busy=true;add('u',esc(q));var w=add('b','<span class="dots"><i></i><i></i><i></i></span>');var fd=new FormData();fd.append('q',q);fd.append('_csrf',box.dataset.csrf);fd.append('h',JSON.stringify(hist.slice(-6)));
 var to=setTimeout(function(){},0);
 fetch('/api/assistant',{method:'POST',body:fd,credentials:'same-origin'}).then(function(r){return r.json()}).then(function(j){
  var l=(j.links||[]).map(function(x){return'<a class="pill" href="'+x.h+'">'+esc(x.l)+' →</a>'}).join('');
  w.innerHTML=md(j.reply)+(l?'<div class="lk">'+l+'</div>':'')+(j.ai?'<small class="aib">✨ AI</small>':'');
  hist.push({r:'u',t:q},{r:'b',t:j.reply});save();setChips(j.chips&&j.chips.length?j.chips:null);log.scrollTop=log.scrollHeight;busy=false;
 }).catch(function(){w.textContent=box.dataset.err;busy=false})}
function hello(){add('b',md(box.dataset.hello));setChips(JSON.parse(box.dataset.chips))}
var first=true;
function open(){box.classList.add('on');fab.style.display='none';if(first){first=false;if(hist.length){hist.forEach(function(x){add(x.r==='u'?'u':'b',x.r==='u'?esc(x.t):md(x.t))})}else hello()}inp.focus()}
fab.onclick=open;d.getElementById('ka-x').onclick=function(){box.classList.remove('on');fab.style.display='flex'};
var nw=d.getElementById('ka-new');if(nw)nw.onclick=function(){hist=[];save();log.innerHTML='';hello()};
form.onsubmit=function(e){e.preventDefault();var q=inp.value.trim();if(q){inp.value='';ask(q)}};
var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
if(mic){if(!SR)mic.style.display='none';else mic.onclick=function(){var r=new SR(),lg=d.documentElement.lang;r.lang=lg==='rw'?'rw-RW':(lg==='fr'?'fr-FR':'en-US');r.interimResults=false;mic.classList.add('rec');
 r.onresult=function(e){inp.value=e.results[0][0].transcript;mic.classList.remove('rec');form.onsubmit(new Event('s'))};r.onerror=r.onend=function(){mic.classList.remove('rec')};try{r.start()}catch(x){mic.classList.remove('rec')}}}
if(location.hash==='#assistant')open();
d.querySelectorAll('[data-ka]').forEach(function(b){b.addEventListener('click',function(e){e.preventDefault();open()})});
window.kizaAsk=function(q){open();ask(q)};
})();
/* geolocation + photo preview/resize */
(function(){var d=document;
d.addEventListener('click',function(e){var b=e.target.closest('[data-geo]');if(!b)return;e.preventDefault();var f=b.closest('form'),st=f.querySelector('.geo');
 if(!navigator.geolocation){st.querySelector('span').textContent=b.dataset.fail;return}
 b.disabled=true;navigator.geolocation.getCurrentPosition(function(p){f.querySelector('[name=lat]').value=p.coords.latitude.toFixed(6);f.querySelector('[name=lng]').value=p.coords.longitude.toFixed(6);st.classList.add('ok');st.querySelector('span').textContent='✓ '+b.dataset.ok+' ('+p.coords.latitude.toFixed(4)+', '+p.coords.longitude.toFixed(4)+')';b.disabled=false},
 function(){st.querySelector('span').textContent=b.dataset.fail;b.disabled=false},{enableHighAccuracy:true,timeout:15000})});
d.addEventListener('change',function(e){var i=e.target;if(!(i.type==='file'&&i.files&&i.files[0]))return;var f=i.files[0],box=i.closest('.drop');if(!/^image\//.test(f.type))return;
 var url=URL.createObjectURL(f),im=new Image();im.onload=function(){
  if(box){var pv=box.querySelector('img');pv.src=url;box.classList.add('has')}
  var m=1280,s=Math.min(1,m/Math.max(im.width,im.height));if(s>=1&&f.size<1.5e6)return;
  var c=d.createElement('canvas');c.width=Math.round(im.width*s);c.height=Math.round(im.height*s);c.getContext('2d').drawImage(im,0,0,c.width,c.height);
  c.toBlob(function(b){try{var dt=new DataTransfer();dt.items.add(new File([b],'photo.jpg',{type:'image/jpeg'}));i.files=dt.files}catch(x){}},'image/jpeg',.85)};im.src=url});
})();

;try{if('serviceWorker' in navigator&&location.protocol!=='file:')navigator.serviceWorker.register('/sw.js').catch(function(){})}catch(e){}
