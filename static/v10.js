/* KIZA-AGRI v10: live "Today" card on dashboards (weather, price movers, season, subsidy) + ask-KIZA shortcut */
(function(){var d=document,P=location.pathname;if(['/farmer','/buyer','/advisor/home'].indexOf(P)<0)return;
var host=d.querySelector('.hero2');if(!host||d.getElementById('td'))return;
var c=d.createElement('div');c.className='td';c.id='td';c.innerHTML='<div class="td-g"><div><div class="td-sk"></div></div><div><div class="td-sk"></div></div><div><div class="td-sk"></div></div></div>';host.parentNode.insertBefore(c,host.nextSibling);
function e(t){return String(t==null?'':t).replace(/[&<>"]/g,function(x){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[x]})}
fetch('/api/v10/today',{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(j){var t=j.t,w=j.weather,pr=j.prices||[];
 var wh=w?'<b>'+Math.round(w.temp)+'°C · '+w.rain_prob+'% 🌧️</b><p>'+e(w.advice)+'</p>'+(w.demo?'<p class="mut">⚠ DEMO</p>':''):'<p class="mut">'+e(t.none_w)+'</p>';
 var ph=pr.length?pr.map(function(x){return'<p><b>'+e(x.crop)+'</b> '+Math.round(x.p).toLocaleString()+' RWF/kg <span class="'+(x.c>0?'up':'dn')+'">'+(x.c>0?'▲':'▼')+Math.abs(x.c).toFixed(1)+'%</span></p>'}).join(''):'<p class="mut">'+e(t.none_p)+'</p>';
 c.innerHTML='<div class="td-h">📍 '+e(t.today)+' '+e(j.district)+' <small>· '+e(j.season)+'</small><button type="button" data-ask>'+e(t.ask)+' 🤖</button></div><div class="td-g"><div><span>⛅ '+e(t.weather)+'</span>'+wh+'</div><div><span>📈 '+e(t.prices)+'</span>'+ph+'</div><div><span>🌱 '+e(t.season)+' '+e(j.season)+'</span><p>'+e(j.urea)+'</p><p><a href="/season"><b>'+e(t.more)+' →</b></a></p></div></div>';
 c.querySelector('[data-ask]').onclick=function(){window.kizaAsk&&window.kizaAsk(t.today+' '+j.district+'?')};
}).catch(function(){c.remove()})})();
