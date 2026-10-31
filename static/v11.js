/* KIZA-AGRI v11 app layer: ripple, count-up, reveal, confetti, bottom-bar indicator, create sheet, command palette,
   farm-health ring + sheet, daily plan sheet, live weather (Open-Meteo, fetched by the browser). */
(function(){'use strict';var d=document,w=window,H=d.documentElement,LG=(H.lang||'en').slice(0,2);
function $(s,r){return(r||d).querySelector(s)}function $$(s,r){return[].slice.call((r||d).querySelectorAll(s))}
function esc(t){return String(t==null?'':t).replace(/[&<>"']/g,function(x){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]})}
var RM=w.matchMedia&&w.matchMedia('(prefers-reduced-motion: reduce)').matches;
var S={en:{spray:'Spray planner',badges:'Achievements',plan:'Daily plan',close:'Close',health:'Farm health',create:'Create',sell:'Sell harvest',scan:'Scan crop',report:'Report problem',farms:'My farms',profit:'Profit simulator',cal:'Calendar',live:'Live farm',search:'Search pages, crops, districts…',pages:'Pages',crops:'Crops',districts:'Districts',market:'Market',nores:'No results',hint:'↑↓ to move · Enter to open · Esc to close',good:'All good',watch:'Watch',risk:'At risk',great:'Excellent',nofield:'Register a field to see your farm health.',offline:'Live data needs internet. Showing saved data.',loading:'Loading…',moist:'Soil moisture',gm:'Good morning',ga:'Good afternoon',ge:'Good evening',rain:'Rain'},
rw:{spray:'Gutera umuti',badges:'Ibyo wagezeho',plan:'Gahunda y\'uyu munsi',close:'Funga',health:'Ubuzima bw\'umurima',create:'Kora',sell:'Gurisha umusaruro',scan:'Genzura igihingwa',report:'Menyesha ikibazo',farms:'Imirima yanjye',profit:'Kubara inyungu',cal:'Kalendari',live:'Umurima uri live',search:'Shakisha amapaji, ibihingwa, uturere…',pages:'Amapaji',crops:'Ibihingwa',districts:'Uturere',market:'Isoko',nores:'Nta bisubizo',hint:'↑↓ kugenda · Enter gufungura · Esc gufunga',good:'Byose ni byiza',watch:'Reba neza',risk:'Biri mu kaga',great:'Byiza cyane',nofield:'Andikisha umurima kugira ngo ubone ubuzima bwawo.',offline:'Amakuru ya live akenera internet. Herekanywe ayabitswe.',loading:'Biraza…',moist:'Ubushuhe bw\'ubutaka',gm:'Mwaramutse',ga:'Mwiriwe',ge:'Mwiriwe',rain:'Imvura'},
fr:{spray:'Planificateur de traitements',badges:'Succès',plan:'Plan du jour',close:'Fermer',health:'Santé de la ferme',create:'Créer',sell:'Vendre la récolte',scan:'Scanner une culture',report:'Signaler un problème',farms:'Mes fermes',profit:'Simulateur de profit',cal:'Calendrier',live:'Ferme en direct',search:'Rechercher pages, cultures, districts…',pages:'Pages',crops:'Cultures',districts:'Districts',market:'Marché',nores:'Aucun résultat',hint:'↑↓ naviguer · Entrée ouvrir · Échap fermer',good:'Tout va bien',watch:'À surveiller',risk:'À risque',great:'Excellent',nofield:'Enregistrez un champ pour voir la santé de votre ferme.',offline:'Les données en direct nécessitent internet.',loading:'Chargement…',moist:'Humidité du sol',gm:'Bonjour',ga:'Bon après-midi',ge:'Bonsoir',rain:'Pluie'}};
function t(k){return(S[LG]||S.en)[k]||S.en[k]||k}w.kizaT=t;
function vib(n){try{navigator.vibrate&&navigator.vibrate(n||8)}catch(e){}}
function csrf(){return d.body.dataset.csrf||''}

/* ---------- ripple ---------- */
d.addEventListener('pointerdown',function(e){var el=e.target.closest('.btn,.q a,.magic a,.magic button,.kh-c,#bnav a,.cr a,.cr button,button.go');if(!el||RM)return;el.classList.add('rpl');var r=el.getBoundingClientRect(),s=Math.max(r.width,r.height)*2,o=d.createElement('span');o.className='rpl-d';o.style.cssText='width:'+s+'px;height:'+s+'px;left:'+(e.clientX-r.left-s/2)+'px;top:'+(e.clientY-r.top-s/2)+'px';el.appendChild(o);setTimeout(function(){o.remove()},650)},{passive:true});

/* ---------- count-up ---------- */
function countUp(el){var to=parseFloat(el.dataset.count),dec=+(el.dataset.dec||0),suf=el.dataset.suf||'';if(isNaN(to))return;if(RM||to===0){el.textContent=to.toLocaleString(undefined,{maximumFractionDigits:dec})+suf;return}
 var t0=performance.now(),D=1100;function f(n){var p=Math.min(1,(n-t0)/D),e=1-Math.pow(1-p,3);el.textContent=(to*e).toLocaleString(undefined,{minimumFractionDigits:dec,maximumFractionDigits:dec})+suf;if(p<1)requestAnimationFrame(f)}requestAnimationFrame(f)}
w.kizaCount=countUp;$$('[data-count]').forEach(countUp);

/* ---------- scroll reveal (progressive: content stays visible without JS) ---------- */
if('IntersectionObserver' in w&&!RM){var io=new IntersectionObserver(function(es){es.forEach(function(x){if(x.isIntersecting){x.target.classList.add('in');io.unobserve(x.target)}})},{threshold:.06});
 $$('main .card,main .sec,main .grid>*,.q>*').slice(0,60).forEach(function(el,i){el.classList.add('rv');el.style.transitionDelay=Math.min(i%6,5)*50+'ms';io.observe(el)});
 setTimeout(function(){$$('.rv:not(.in)').forEach(function(x){x.classList.add('in')})},2500)}

/* ---------- confetti ---------- */
w.kizaConfetti=function(){if(RM)return;var c=d.createElement('canvas');c.id='confetti';c.width=innerWidth;c.height=innerHeight;d.body.appendChild(c);var g=c.getContext('2d'),cols=['#2f9a50','#ffc933','#c8693a','#8ee0a6','#ffffff','#4b9ad1'],P=[];
 for(var i=0;i<110;i++)P.push({x:innerWidth/2+(Math.random()-.5)*120,y:innerHeight*.62,vx:(Math.random()-.5)*13,vy:-Math.random()*15-5,r:Math.random()*6+3,c:cols[i%cols.length],a:Math.random()*6,va:(Math.random()-.5)*.4});
 var t0=performance.now();(function f(n){var e=n-t0;g.clearRect(0,0,c.width,c.height);P.forEach(function(p){p.vy+=.45;p.x+=p.vx;p.y+=p.vy;p.vx*=.99;p.a+=p.va;g.save();g.translate(p.x,p.y);g.rotate(p.a);g.fillStyle=p.c;g.globalAlpha=Math.max(0,1-e/2200);g.fillRect(-p.r,-p.r/2,p.r*2,p.r);g.restore()});if(e<2300)requestAnimationFrame(f);else c.remove()})(t0);vib([12,40,12])};
var okf=$('main .flash.ok');if(okf&&okf.textContent.length<160&&!/language|welcome back/i.test(okf.textContent))setTimeout(w.kizaConfetti,350);

/* ---------- bottom bar: sliding indicator ---------- */
var bn=$('#bnav');if(bn){var ind=d.createElement('span');ind.className='bn-ind';bn.insertBefore(ind,bn.firstChild);
 function place(){var a=$('a.active',bn);if(!a){ind.classList.remove('on');return}var b=bn.getBoundingClientRect(),r=a.getBoundingClientRect();ind.style.setProperty('--x',(r.left-b.left)+'px');ind.style.setProperty('--w',r.width+'px');ind.classList.add('on')}
 place();w.addEventListener('resize',place);setTimeout(place,300);bn.addEventListener('click',function(e){if(e.target.closest('a,button'))vib(8)})}

/* ---------- sheets ---------- */
function sheet(id,title,html){var s=d.getElementById(id);if(!s){s=d.createElement('div');s.id=id;s.className='sh';s.innerHTML='<div class="sh-in" role="dialog" aria-modal="true"><div class="sh-h"><h3></h3><button type="button" data-x aria-label="'+esc(t('close'))+'">✕</button></div><div class="sh-b"></div></div>';d.body.appendChild(s);
 s.addEventListener('click',function(e){if(e.target===s||e.target.closest('[data-x]'))s.classList.remove('on')})}
 $('h3',s).textContent=title;$('.sh-b',s).innerHTML=html;s.classList.add('on');return s}
d.addEventListener('keydown',function(e){if(e.key==='Escape')$$('.sh.on').forEach(function(s){s.classList.remove('on')})});

/* create sheet */
var CR=[['🛒',t('sell'),'/market'],['🔬',t('scan'),'/scan'],['📢',t('report'),'/distress'],['🏡',t('farms'),'/farms'],['🧴',t('spray'),'/care'],['💹',t('profit'),'/profit'],['🏅',t('badges'),'/badges'],['✨',t('plan'),'#plan']];
d.addEventListener('click',function(e){var b=e.target.closest('[data-create]');if(b){e.preventDefault();vib(12);sheet('sh-create',t('create'),'<div class="cr">'+CR.map(function(x){return x[2]==='#plan'?'<button type="button" data-plan><b>'+x[0]+'</b>'+esc(x[1])+'</button>':'<a href="'+x[2]+'"><b>'+x[0]+'</b>'+esc(x[1])+'</a>'}).join('')+'</div>');return}
 var p=e.target.closest('[data-plan]');if(p){e.preventDefault();$$('.sh.on').forEach(function(s){s.classList.remove('on')});openPlan()}});

/* ---------- daily plan ---------- */
function openPlan(){var s=sheet('sh-plan','✨ '+t('plan'),'<div class="sk" style="height:60px;margin:8px 0"></div><div class="sk" style="height:60px;margin:8px 0"></div><div class="sk" style="height:60px"></div>');
 fetch('/api/v11/plan',{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(j){$('h3',s).textContent='✨ '+(j.hello||t('plan'));
  $('.sh-b',s).innerHTML=(j.items||[]).map(function(x,i){return'<a class="pl '+esc(x.level)+'" style="animation-delay:'+(i*110)+'ms" href="'+esc(x.link||'#')+'"><span>'+esc(x.icon)+'</span><b>'+esc(x.text)+'</b></a>'}).join('')||'<p>—</p>'}).catch(function(){$('.sh-b',s).innerHTML='<p>'+esc(t('offline'))+'</p>'})}
w.kizaPlan=openPlan;

/* ---------- farm health ring ---------- */
var ring=$('#kh-ring');if(ring){var fg=$('.fg',ring),num=$('b',ring),lab=$('#kh-label'),chip=$('#kh-chip'),HD=null;
 fetch('/api/v11/health',{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(j){var h=j.health;HD=h;
  if(!h||h.score==null){num.textContent='–';lab.textContent=t('nofield');chip.remove();return}
  var C=213.6,col=h.score>=85?'#2f9a50':h.score>=70?'#4cb06a':h.score>=50?'#e6a118':'#d64545';fg.style.stroke=col;requestAnimationFrame(function(){fg.style.strokeDashoffset=C*(1-h.score/100)});
  num.dataset.count=h.score;countUp(num);lab.textContent=h.label;chip.textContent=h.score>=70?t('good'):h.score>=50?t('watch'):t('risk');chip.className='kh-ok '+(h.score>=70?'':h.score>=50?'w':'b')}).catch(function(){});
 $('#kh-health').addEventListener('click',function(){if(!HD||HD.score==null){location.href='/farms';return}
  var col=function(s){return s>=85?'#2f9a50':s>=70?'#4cb06a':s>=50?'#e6a118':'#d64545'};
  var s=sheet('sh-health','🌱 '+t('health')+' · '+HD.score+'%',HD.comps.map(function(c){return'<div class="hb"><div class="r"><span>'+esc(c.icon)+' '+esc(c.label)+'</span><span>'+c.score+'%</span></div><div class="bar"><i style="background:'+col(c.score)+'" data-w="'+c.score+'"></i></div><p>'+esc(c.note)+'</p></div>'}).join('')+'<p class="mut" style="font-size:12px;margin-top:12px">'+esc(LG==='rw'?'Bibarwa ku makuru y\'imirima, ikirere, ubutaka n\'ibiciro byawe.':LG==='fr'?'Calculé à partir de vos champs, météo, sol et prix.':'Calculated from your fields, weather, soil and prices.')+'</p>');
  setTimeout(function(){$$('.bar i',s).forEach(function(i){i.style.width=i.dataset.w+'%'})},60)})}

/* ---------- live weather (browser -> Open-Meteo, no key). Offline = silent fallback ---------- */
var WMO=function(c){return c===0?['☀️',{en:'Clear',rw:'Izuba',fr:'Dégagé'}]:c<=2?['🌤️',{en:'Partly cloudy',rw:'Ibicu bike',fr:'Peu nuageux'}]:c===3?['☁️',{en:'Cloudy',rw:'Ibicu',fr:'Nuageux'}]:c<=48?['🌫️',{en:'Fog',rw:'Igihu',fr:'Brouillard'}]:c<=57?['🌦️',{en:'Drizzle',rw:'Agashyuhe',fr:'Bruine'}]:c<=67?['🌧️',{en:'Rain',rw:'Imvura',fr:'Pluie'}]:c<=82&&c>=80?['🌦️',{en:'Showers',rw:'Imvura y\'umuhengeri',fr:'Averses'}]:c>=95?['⛈️',{en:'Thunderstorm',rw:'Inkuba',fr:'Orage'}]:['🌥️',{en:'Mixed',rw:'Ibicu n\'izuba',fr:'Variable'}]};
w.kizaWx={wmo:function(c){var x=WMO(c);return{ic:x[0],tx:x[1][LG]||x[1].en}},
 get:function(lat,lng){var k='kwx2'+lat.toFixed(2)+','+lng.toFixed(2);try{var c=JSON.parse(sessionStorage.getItem(k)||'null');if(c&&Date.now()-c.t<9e5)return Promise.resolve(c.v)}catch(e){}
  var u='https://api.open-meteo.com/v1/forecast?latitude='+lat+'&longitude='+lng+'&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,precipitation&hourly=soil_moisture_3_to_9cm,precipitation_probability,wind_speed_10m,temperature_2m,relative_humidity_2m,is_day&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,et0_fao_evapotranspiration,uv_index_max,sunrise,sunset&timezone=Africa%2FKigali&forecast_days=7';
  var ac=w.AbortController?new AbortController():null,to=setTimeout(function(){ac&&ac.abort()},9000);
  return fetch(u,ac?{signal:ac.signal}:{}).then(function(r){clearTimeout(to);if(!r.ok)throw 0;return r.json()}).then(function(v){try{sessionStorage.setItem(k,JSON.stringify({t:Date.now(),v:v}))}catch(e){}return v})}};
var kw=$('#kh-w');if(kw&&kw.dataset.lat){var la=+kw.dataset.lat,lo=+kw.dataset.lng;
 w.kizaWx.get(la,lo).then(function(v){var c=v.current,m=w.kizaWx.wmo(c.weather_code),h=v.hourly,i=Math.max(0,h.time.indexOf(c.time.slice(0,13)+':00'));
  $('.t',kw).textContent=Math.round(c.temperature_2m)+'°C';$('.ic',kw).textContent=m.ic;$('.cond',kw).innerHTML='<i class="live"></i>'+esc(m.tx);
  $('.m',kw).innerHTML='<span>💧 '+Math.round(c.relative_humidity_2m)+'%</span><span>🌧 '+(v.daily.precipitation_probability_max[0]||0)+'%</span><span>💨 '+Math.round(c.wind_speed_10m)+'</span>';
  var sm=h.soil_moisture_3_to_9cm&&h.soil_moisture_3_to_9cm[i];var el=$('#q-moist');if(el&&sm!=null){el.dataset.count=Math.round(sm*100);el.dataset.suf='%';countUp(el)}}).catch(function(){var el=$('#q-moist');if(el)el.textContent='–'})}

/* ---------- ticker (price movers) ---------- */
var tk=$('#tick');if(tk)fetch('/api/v10/today',{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(j){var p=j.prices||[];if(!p.length)return;var h=p.concat(p).map(function(x){return'<span>'+esc(x.crop)+' <b>'+Math.round(x.p).toLocaleString()+'</b> <span class="'+(x.c>0?'up':'dn')+'">'+(x.c>0?'▲':'▼')+Math.abs(x.c).toFixed(1)+'%</span></span>'}).join('');tk.innerHTML='<div>'+h+'</div><div aria-hidden="true">'+h+'</div>';tk.hidden=false}).catch(function(){});

/* ---------- command palette ---------- */
var pal=null,items=[],sel=0,timer=null;
function pages(){var seen={},out=[];$$('body>nav a[href],#msheet a[href]').forEach(function(a){var h=a.getAttribute('href');if(!h||h==='#'||/^\/(lang|logout)/.test(h)||h.charAt(0)==='#'||seen[h])return;seen[h]=1;var tx=a.textContent.replace(/\s+/g,' ').trim();if(tx&&tx.length<44)out.push({n:tx,l:h})});
 [['🌱',t('profit'),'/profit'],['🗓️',t('cal'),'/calendar'],['📡',t('live'),'/live'],['🌱','Season & inputs','/season']].forEach(function(x){if(!seen[x[2]])out.push({n:x[0]+' '+x[1],l:x[2]})});return out}
function openPal(){if(!pal){pal=d.createElement('div');pal.id='pal';pal.innerHTML='<div class="pal-b" role="dialog" aria-modal="true"><input type="search" autocomplete="off" aria-label="Search"><div class="pal-l"></div><div class="pal-f"></div></div>';d.body.appendChild(pal);
  $('input',pal).placeholder=t('search');$('.pal-f',pal).textContent=t('hint');pal.addEventListener('click',function(e){if(e.target===pal)closePal()});
  $('input',pal).addEventListener('input',function(){render(this.value)});$('input',pal).addEventListener('keydown',function(e){if(e.key==='ArrowDown'){sel=Math.min(items.length-1,sel+1);hl();e.preventDefault()}else if(e.key==='ArrowUp'){sel=Math.max(0,sel-1);hl();e.preventDefault()}else if(e.key==='Enter'&&items[sel]){location.href=items[sel].l}else if(e.key==='Escape')closePal()})}
 pal.classList.add('on');var i=$('input',pal);i.value='';render('');setTimeout(function(){i.focus()},30)}
function closePal(){pal&&pal.classList.remove('on')}
function hl(){$$('.pal-l a',pal).forEach(function(a,i){a.classList.toggle('sel',i===sel);if(i===sel)a.scrollIntoView({block:'nearest'})})}
function draw(groups){items=[];var h='';groups.forEach(function(g){if(!g.rows.length)return;h+='<h6>'+esc(g.t)+'</h6>';g.rows.forEach(function(r){items.push(r);h+='<a href="'+esc(r.l)+'">'+esc(r.n)+(r.s?'<small>'+esc(r.s)+'</small>':'')+'</a>'})});
 $('.pal-l',pal).innerHTML=h||'<h6>'+esc(t('nores'))+'</h6>';sel=0;hl()}
function render(q){q=q.trim().toLowerCase();var P=pages().filter(function(p){return!q||p.n.toLowerCase().indexOf(q)>-1}).slice(0,q?6:10);draw([{t:t('pages'),rows:P}]);clearTimeout(timer);
 if(q.length>=2)timer=setTimeout(function(){fetch('/api/v11/search?q='+encodeURIComponent(q),{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(j){if(!pal.classList.contains('on')||$('input',pal).value.trim().toLowerCase()!==q)return;
  draw([{t:t('pages'),rows:P},{t:t('crops'),rows:(j.crops||[]).map(function(x){return{n:'🌾 '+x.name,l:x.link}})},{t:t('districts'),rows:(j.districts||[]).map(function(x){return{n:'📍 '+x.name,s:x.sub,l:x.link}})},{t:t('market'),rows:(j.listings||[]).map(function(x){return{n:'🛒 '+x.name,s:x.sub,l:x.link}})}])}).catch(function(){})},180)}
d.addEventListener('keydown',function(e){var tg=(e.target.tagName||'');if((e.key==='k'||e.key==='K')&&(e.ctrlKey||e.metaKey)){e.preventDefault();openPal()}else if(e.key==='/'&&!/INPUT|TEXTAREA|SELECT/.test(tg)&&!e.target.isContentEditable&&d.body.dataset.role){e.preventDefault();openPal()}});
d.addEventListener('click',function(e){if(e.target.closest('[data-pal]')){e.preventDefault();openPal()}});
if(d.body.dataset.role){var sp=$('body>nav .sp');if(sp){var b=d.createElement('button');b.type='button';b.className='iconbtn';b.setAttribute('data-pal','');b.setAttribute('aria-label','Search');b.title='Ctrl K';b.textContent='🔍';sp.parentNode.insertBefore(b,sp.nextSibling)}}
w.kizaPalette=openPal;
})();
/* greeting by local time */
(function(){var g=document.getElementById('greet');if(g&&g.dataset.h){var a=g.dataset.h.split('|'),h=new Date().getHours();g.textContent=a[h<12?0:h<17?1:2]}})();

/* ===== v11b: spray windows from the live hourly forecast, weather-reactive scene, badges toast ===== */
(function(){'use strict';var d=document,w=window,LG=(d.documentElement.lang||'en').slice(0,2);
function $(s,r){return(r||d).querySelector(s)}function $$(s,r){return[].slice.call((r||d).querySelectorAll(s))}
var DN={en:['Sun','Mon','Tue','Wed','Thu','Fri','Sat'],rw:['Cyu','Mbe','Kab','Gtt','Kan','Gnu','Gnd'],fr:['Dim','Lun','Mar','Mer','Jeu','Ven','Sam']}[LG]||['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
var TD={en:['Today','Tomorrow'],rw:['Uyu munsi','Ejo'],fr:["Aujourd'hui",'Demain']}[LG]||['Today','Tomorrow'];
/* rule of thumb: calm (<=12 km/h), no rain risk for the next 3 h, <=28C and daylight = good; <=20 km/h, rain <50%, <=32C = careful */
w.kizaSpray={
 dayName:function(ds){return DN[new Date(ds+'T12:00').getDay()]},
 dayLabel:function(S,ds){var i=S.days.findIndex(function(x){return x.date===ds});return i===0?TD[0]:i===1?TD[1]:this.dayName(ds)},
 analyse:function(v){var h=v.hourly,n=h.time.length,i0=Math.max(0,h.time.indexOf(v.current.time.slice(0,13)+':00')),arr=[];
  for(var i=0;i<n;i++){var hh=+h.time[i].slice(11,13),day=h.is_day?h.is_day[i]===1:(hh>=6&&hh<18),pp=Math.max(h.precipitation_probability[i]||0,h.precipitation_probability[i+1]||0,h.precipitation_probability[i+2]||0),wd=h.wind_speed_10m[i]||0,tp=h.temperature_2m[i]||0;
   var cls=i<i0?'past':!day?'past':(wd<=12&&pp<30&&tp<=28)?'good':(wd<=20&&pp<50&&tp<=32)?'ok':'bad';arr.push({i:i,date:h.time[i].slice(0,10),hh:('0'+hh).slice(-2),cls:cls,wind:wd,pp:pp,temp:tp})}
  var days=[],ds=[];arr.forEach(function(x){var g=days.find(function(y){return y.date===x.date});if(!g){g={date:x.date,hours:[]};days.push(g)}g.hours.push(x)});
  days=days.filter(function(g){return g.hours.length===24}).slice(0,3);
  var wins=[],cur=null;arr.forEach(function(x){if(x.i<i0||x.i>i0+72)return;if(x.cls==='good'||x.cls==='ok'){if(cur&&cur.last===x.i-1&&cur.date===x.date){cur.last=x.i;cur.hs.push(x)}else{cur={date:x.date,first:x.i,last:x.i,hs:[x]};wins.push(cur)}}else cur=null});
  wins=wins.filter(function(g){return g.hs.length>=2}).map(function(g){var q=g.hs.every(function(x){return x.cls==='good'})?'good':'ok';return{date:g.date,from:g.hs[0].hh+':00',to:('0'+((+g.hs[g.hs.length-1].hh+1)%24)).slice(-2)+':00',q:q,len:g.hs.length,in:g.first-i0,wind:Math.max.apply(0,g.hs.map(function(x){return x.wind})),pp:Math.max.apply(0,g.hs.map(function(x){return x.pp}))}});
  var best=null;wins.forEach(function(x){if(x.q==='good'&&(!best||x.len>best.len||(x.len===best.len&&x.in<best.in)))best=x});if(best)best.best=true;
  return{days:days,windows:wins.slice(0,6),i0:i0,next:wins[0]||null}},
 notify:function(S){try{if(localStorage.getItem('kzn')!=='1'||!w.Notification||Notification.permission!=='granted')return;
  var x=S.windows.find(function(y){return y.q==='good'&&y.in<=1});if(!x)return;var k='kzn_'+x.date+'_'+x.from;if(localStorage.getItem(k))return;localStorage.setItem(k,'1');
  new Notification('KIZA-AGRI 🧴',{body:({en:'Good spraying window: ',rw:'Igihe cyiza cyo gutera umuti: ',fr:'Bonne fenêtre : '}[LG]||'')+x.from+'–'+x.to,icon:'/static/icon-192.png'})}catch(e){}}};

/* dashboard: next spray window */
var sn=$('#spr-next');if(sn&&w.kizaWx){var kw=$('#kh-w');
 w.kizaWx.get(+(kw?kw.dataset.lat:sn.dataset.lat),+(kw?kw.dataset.lng:sn.dataset.lng)).then(function(v){var S=w.kizaSpray.analyse(v),x=S.next,T={en:['Next spray window','None in the next 3 days'],rw:['Igihe gikurikira cyo gutera umuti','Nta cyiza mu minsi 3'],fr:['Prochaine fenêtre','Aucune sous 3 jours']}[LG]||['Next spray window','None in the next 3 days'];
  sn.querySelector('b').textContent=x?(w.kizaSpray.dayLabel(S,x.date)+' '+x.from+'–'+x.to):T[1];sn.classList.add(x?x.q:'bad');sn.querySelector('small').textContent=T[0];w.kizaSpray.notify(S)}).catch(function(){sn.hidden=true})}

/* weather- and time-reactive scene */
function rainfx(host){if($('.rainfx',host))return;var r=d.createElement('div');r.className='rainfx';for(var i=0;i<46;i++){var e=d.createElement('i');e.style.cssText='left:'+(Math.random()*100)+'%;animation-duration:'+(.55+Math.random()*.5)+'s;animation-delay:'+(-Math.random()*1.2)+'s;opacity:'+(.35+Math.random()*.5);r.appendChild(e)}host.appendChild(r)}
var hr=new Date().getHours(),night=hr<6||hr>=18;
var kh=$('.kh');if(kh){if(night)kh.classList.add('is-night');if(kh.dataset.rain==='1'){kh.classList.add('is-rain');rainfx($('.kh-scene',kh))}
 var kw2=$('#kh-w');if(kw2&&w.kizaWx)w.kizaWx.get(+kw2.dataset.lat,+kw2.dataset.lng).then(function(v){var c=v.current;if((c.weather_code>=51&&c.weather_code<=82)||c.precipitation>0.2){kh.classList.add('is-rain');rainfx($('.kh-scene',kh))}else{kh.classList.remove('is-rain')}}).catch(function(){})}
var aw=$('.av-wrap');if(aw&&night)aw.classList.add('is-night');
var ws=$('.wl-stage');if(ws&&night)ws.classList.add('is-night');

/* toast + achievements */
w.kizaToast=function(m){var t=d.createElement('div');t.className='kz-toast';t.textContent=m;d.body.appendChild(t);requestAnimationFrame(function(){t.classList.add('on')});setTimeout(function(){t.classList.remove('on');setTimeout(function(){t.remove()},400)},4200)};
if(/^\/(farmer|buyer|badges)$/.test(location.pathname)&&d.body.dataset.role){fetch('/api/v11/badges',{credentials:'same-origin'}).then(function(r){return r.ok?r.json():null}).then(function(j){if(!j)return;var old=null;try{old=JSON.parse(localStorage.getItem('kzb'))}catch(e){}
 if(old){var nw=j.earned.filter(function(c){return old.indexOf(c)<0});if(nw.length){w.kizaConfetti&&w.kizaConfetti();w.kizaToast('🏅 '+nw.map(function(c){return j.titles[c]}).join(', '))}}
 try{localStorage.setItem('kzb',JSON.stringify(j.earned))}catch(e){}var c=$('#bd-count');if(c)c.textContent=j.earned.length+'/'+j.total}).catch(function(){})}
})();
