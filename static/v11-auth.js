/* KIZA-AGRI v11: welcome splash + login/register behaviour (no dependencies) */
(function(){var d=document;function $(s,r){return(r||d).querySelector(s)}function $$(s,r){return[].slice.call((r||d).querySelectorAll(s))}
/* ---- welcome splash ---- */
var st=$('.wl-stage');if(st){var skip=d.body.dataset.skip==='1',s1=$('#s1'),s2=$('#s2'),shown=false;
 function open(){if(shown)return;shown=true;st.classList.add('up');(skip?s2:s1).classList.add('on')}
 if(skip){open()}else{var t=setTimeout(open,3300);d.addEventListener('pointerdown',function(){clearTimeout(t);open()},{once:true})}}
/* ---- password eye ---- */
$$('[data-eye]').forEach(function(b){b.addEventListener('click',function(){var i=b.parentNode.querySelector('input');var show=i.type==='password';i.type=show?'text':'password';b.classList.toggle('on',show)})});
var card=$('.av-card');if(card&&$('.av-fl.err,.av-fl.bad,.av-fl.error,.av-fl'))setTimeout(function(){card.classList.add('shake')},500);
/* ---- login: spinner on submit ---- */
var lf=$('#lf');if(lf)lf.addEventListener('submit',function(e){var b=$('.go',lf);if(!lf.checkValidity()){e.preventDefault();$$('input:invalid',lf).forEach(function(i){i.closest('.av-in').classList.add('bad');setTimeout(function(){i.closest('.av-in').classList.remove('bad')},600)});if(card){card.classList.remove('shake');void card.offsetWidth;card.classList.add('shake')}return}b.classList.add('loading')});
/* ---- register wizard ---- */
var f=$('#rf');if(f){var secs=$$('section',f),steps=$('#steps'),dots=$$('i',steps),cur=Math.min(3,+steps.dataset.start||1);
 function show(n,back){cur=n;f.dataset.step=n;f.classList.toggle('back',!!back);secs.forEach(function(s){s.classList.toggle('on',+s.dataset.s===n)});dots.forEach(function(x,i){x.classList.toggle('on',i<n)});steps.style.setProperty('--p',(n-1)/2);
  var fi=$('input:not([type=radio]),select',secs[n-1]);if(fi&&n>1)setTimeout(function(){try{fi.focus({preventScroll:true})}catch(e){}},350)}
 function bad(el){var w=el.closest('.av-in')||el;w.classList.add('bad');setTimeout(function(){w.classList.remove('bad')},700)}
 function valid(n){var ok=true;$$('input[required],select[required]',secs[n-1]).forEach(function(i){if(!i.checkValidity()||!i.value.trim()){ok=false;bad(i)}});
  if(n===3){var a=$('#p1').value,b=$('#p2').value;if(a!==b){ok=false;bad($('#p2'))}if(!(a.length>=8&&/[A-Za-z]/.test(a)&&/\d/.test(a))){ok=false;bad($('#p1'))}}return ok}
 function nope(){if(card){card.classList.remove('shake');void card.offsetWidth;card.classList.add('shake')}}
 $('#nx').addEventListener('click',function(){if(valid(cur))show(cur+1);else nope()});
 $('#bk').addEventListener('click',function(){if(cur>1)show(cur-1,true)});
 f.addEventListener('keydown',function(e){if(e.key==='Enter'&&cur<3&&e.target.tagName!=='BUTTON'){e.preventDefault();$('#nx').click()}});
 f.addEventListener('submit',function(e){for(var n=1;n<=3;n++){if(!valid(n)){e.preventDefault();show(n,n<cur);nope();return}}$('#sb').classList.add('loading')});
 var p1=$('#p1'),p2=$('#p2'),mt=$('#mt'),mm=$('#mm');
 function meter(){var v=p1.value,s=0;if(v.length>=8)s++;if(/[A-Za-z]/.test(v)&&/\d/.test(v))s++;if(v.length>=12||/[^A-Za-z0-9]/.test(v))s++;mt.style.width=(v?Math.max(s,1)*33.4:0)+'%';mt.style.background=['#d64545','#e6a118','#2fb36d','#0f5a35'][s];match()}
 function match(){mm.classList.toggle('on',!!p2.value&&p1.value===p2.value)}
 p1.addEventListener('input',meter);p2.addEventListener('input',match);show(cur)}
})();
