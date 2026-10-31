/* KIZA-AGRI v9: contrast + zoom (A- / A+) controls shared by header and phone menu */
(function(){var d=document,h=d.documentElement,Z=[.85,1,1.15,1.3,1.5,1.75];
function g(k){try{return localStorage.getItem(k)}catch(e){return null}}function s(k,v){try{localStorage.setItem(k,v)}catch(e){}}
var i=+g('kz');if(!(i>=0&&i<Z.length))i=1;
function paint(){h.style.zoom=Z[i];d.querySelectorAll('[data-zoom]').forEach(function(b){var up=+b.dataset.zoom>0;b.disabled=up?i>=Z.length-1:i<=0;b.style.opacity=b.disabled?.4:1;b.title=(up?'Zoom in':'Zoom out')+' · '+Math.round(Z[i]*100)+'%'})}
if(g('kc'))h.dataset.hc='1';
d.addEventListener('click',function(e){var z=e.target.closest('[data-zoom]');
 if(z){i=Math.max(0,Math.min(Z.length-1,i+(+z.dataset.zoom)));s('kz',i);paint();return}
 if(e.target.closest('[data-hc]')){var on=!h.dataset.hc;on?(h.dataset.hc='1',s('kc','1')):(delete h.dataset.hc,s('kc',''))}});
paint();
})();
/* open the assistant when the page is opened as /#assistant (guest accounts only: the widget does not exist otherwise) */
(function(){function go(){if(location.hash==='#assistant'){var f=document.getElementById('ka-fab');if(f)f.click()}}
window.addEventListener('load',go);window.addEventListener('hashchange',go)})();
