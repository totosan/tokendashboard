'use strict';
/* Scanner for recent closed 5-minute candles. A breakout is descriptive, not a prediction. */
function detectBreakout(raw,end,side,minVolume){
 const bars=PulsePattern.aggregate(raw,5,end),duration=300000,aligned=Math.floor(end/duration)*duration;
 if(!bars.length||bars.at(-1)[0]+duration!==aligned)return null;
 const sign=side==='long'?1:-1,cv=c=>({t:c[0],o:sign*c[1],h:sign*(sign===1?c[2]:c[3]),l:sign*(sign===1?c[3]:c[2]),c:sign*c[4],v:c[6],raw:c});
 const a=bars.map(cv);
 for(const confirmed of [true,false]){
  const offset=confirmed?1:0,endHandle=a.length-offset,startHandle=endHandle-4,startImpulse=startHandle-6;
  if(startImpulse<0)continue;
  const imp=a.slice(startImpulse,startHandle),handle=a.slice(startHandle,endHandle),all=a.slice(startImpulse);
  if(all.some((c,i)=>i&&c.t-all[i-1].t!==duration))continue;
  if(imp.at(-1).c<=imp[0].o||imp.slice(1).filter((c,i)=>c.c>imp[i].c).length<4)continue;
  const origin=imp[0].o,peak=Math.max(...imp.map(c=>c.h)),swing=peak-origin,low=Math.min(...handle.map(c=>c.l)),top=Math.max(...handle.map(c=>c.h));
  const retrace=(peak-low)/swing;if(!(swing>0)||retrace<.05||retrace>.5||low<=origin||top>peak+Math.abs(peak)*.002)continue;
  const avgHandle=handle.reduce((s,c)=>s+c.v,0)/4,avgImp=imp.reduce((s,c)=>s+c.v,0)/6;
  let ratio=NaN;if(confirmed){const c=a.at(-1);ratio=avgHandle>0?c.v/avgHandle:NaN;if(c.c<=c.o||c.c<=top||!Number.isFinite(ratio)||ratio<minVolume)continue}
  return {side,status:confirmed?'confirmed':'watch',level:sign*top,invalidation:sign*low,retrace,quiet:avgImp>0?avgHandle/avgImp:NaN,volume:ratio,closedAt:aligned,prices:all.map(c=>c.raw[4]),minutes:5,impulse:(imp.at(-1).c-origin)/Math.abs(origin)*100*sign};
 }
 return null;
}
function breakoutCandidates(){return results.map(r=>({r,s:detectBreakout(r.candles,target,direction,+$('breakout-volume').value)})).filter(x=>x.s&&($('breakout-status').value==='all'||x.s.status===$('breakout-status').value)).sort((a,b)=>(b.s.status==='confirmed')-(a.s.status==='confirmed')||b.s.closedAt-a.s.closedAt||b.r.dayVolume-a.r.dayVolume)}
function renderBreakout(){
 const list=breakoutCandidates(),q=$('breakout-search').value.trim().toUpperCase(),visible=list.filter(x=>x.r.symbol.includes(q));
 $('breakout-count').textContent=list.length+' Treffer';$('breakout-summary').textContent=busy?`${scanned} von ${total} Kontrakten geprüft · Ergebnisse vorläufig`:`${results.length} von ${total} Kontrakten geprüft · ${failures} ohne Daten · ${eligible} erfüllen den Volumenfilter`;
 $('breakout-window').textContent=target?'Letzte abgeschlossene 5m-Kerze bis '+time(Math.floor(target/300000)*300000)+' UTC':'Warte auf Daten';
 $('breakout-list').innerHTML=visible.length?visible.slice(0,30).map(({r,s})=>`<article class="break-item"><div class="break-name"><span class="coin-icon">${esc(r.base.slice(0,2))}</span><div><a href="${url(r)}" target="_blank" rel="noopener noreferrer"><strong>${esc(r.base)}</strong> <small>USDT PERP ↗</small></a><span class="break-state ${s.status==='watch'?'waiting':''}">${s.status==='confirmed'?'● Ausbruch bestätigt':'◌ Konsolidierung'}</span></div></div><div class="break-values"><div><small>Ausbruchsniveau</small><b>${price(s.level)}</b></div><div><small>Strukturtief / -hoch</small><b>${price(s.invalidation)}</b></div><div><small>Rücklauf</small><b>${num(s.retrace*100,1)}%</b></div><div><small>Ausbruchsvolumen</small><b>${Number.isFinite(s.volume)?num(s.volume,1)+'×':'—'}</b></div><div><small>Rücksetzer-Vol.</small><b>${Number.isFinite(s.quiet)?num(s.quiet,1)+'×':'—'}</b></div><div><small>Spread¹</small><b>${Number.isFinite(r.spread)?num(r.spread,3)+'%':'—'}</b></div></div><div class="break-line">${spark(s.prices,s.side==='long'?'#bbf96b':'#f28183')}</div></article>`).join(''):`<div class="break-empty"><strong>${busy?'Suche läuft …':'Aktuell kein passendes Muster'}</strong><p>${q?'Für diese Suche gibt es keinen Treffer.':'Der Scanner zeigt Ergebnisse, sobald die gewählten Bedingungen erfüllt sind.'}</p></div>`;
 $('breakout-more').textContent=visible.length>30?`Die ersten 30 von ${visible.length} Treffern · Suche eingrenzen`:'';
}
