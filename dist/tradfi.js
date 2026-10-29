'use strict';
/* Long-only, closed-candle approximation of the first higher high after a pullback. */
function tradfiPattern(raw,end,minImpulse){
 const a=raw.filter(c=>+c[0]<end).sort((a,b)=>+a[0]-+b[0]);if(!a.length||+a.at(-1)[0]!==end-60000)return null;
 for(const triggered of [true,false]){const pe=a.length-(triggered?1:0);for(let n=1;n<=3;n++){const ps=pe-n,pull=a.slice(ps,pe);if(ps<2||pull.length!==n||pull.some(c=>!(+c[4]<+c[1])))continue;
  for(let len=2;len<=6;len++){const start=ps-len,imp=a.slice(start,ps);if(start<0)continue;const segment=a.slice(start);if(segment.some((c,i)=>i&&+c[0]- +segment[i-1][0]!==60000))continue;
   if(imp.filter(c=>+c[4]>+c[1]).length<Math.ceil(len*2/3))continue;const origin=+imp[0][1],peak=Math.max(...imp.map(c=>+c[2])),swing=peak-origin,finish=+imp.at(-1)[4],low=Math.min(...pull.map(c=>+c[3]));if(!(origin>0&&swing>0)||finish<=origin)continue;const impulse=(finish/origin-1)*100,retrace=(peak-low)/swing;if(impulse<minImpulse||retrace<0||retrace>.5||low<=origin)continue;
   const trigger=+pull.at(-1)[2];if(triggered&&!(+a.at(-1)[2]>trigger&&+a.at(-1)[3]>low))continue;
   const vi=imp.reduce((s,c)=>s+ +c[6],0)/len,vp=pull.reduce((s,c)=>s+ +c[6],0)/n;
   return {status:triggered?'triggered':'watch',trigger,low,impulse,retrace,pullbackBars:n,ratio:vi>0?vp/vi:NaN,closedAt:end,candles:a.slice(Math.max(0,start-2)).map(c=>+c[4]),closeAbove:triggered&&+a.at(-1)[4]>trigger};
  }} }
 return null;
}
function renderTradfi(){const query=$('tradfi-search').value.trim().toUpperCase(),min=+$('tradfi-change').value,imp=+$('tradfi-impulse').value,filter=$('tradfi-status').value;
 const candidates=results.filter(r=>Number.isFinite(r.day)&&r.day>=min).map(r=>({r,p:tradfiPattern(r.candles,target,imp)})).filter(({r,p})=>p&&(filter==='all'||p.status===filter)&&r.symbol.includes(query)).sort((a,b)=>(b.p.status==='triggered')-(a.p.status==='triggered')||b.r.day-a.r.day);
 $('tradfi-count').textContent=candidates.length+' Treffer';$('tradfi-summary').textContent=busy?`${scanned} von ${total} Aktien-Perpetuals geprüft · vorläufig`:`${results.length} von ${total} geprüft · ${failures} ohne Daten · ${eligible} nach 24h-Volumenfilter`;
 $('tradfi-window').textContent=target?'Letzte abgeschlossene 1m-Kerze bis '+time(target)+' UTC':'Warte auf Daten';
 $('tradfi-list').innerHTML=candidates.length?candidates.slice(0,30).map(({r,p})=>`<article class="break-item"><div class="break-name"><span class="coin-icon">${esc(r.base.slice(0,2))}</span><div><a href="${url(r)}" target="_blank" rel="noopener noreferrer"><strong>${esc(r.base)}</strong> <small>USDT PERP ↗</small></a><span class="break-state ${p.status==='watch'?'waiting':''}">${p.status==='watch'?'◌ Rücksetzer läuft':'● Neues Hoch berührt'}</span></div></div><div class="break-values"><div><small>24h¹</small><b class="${tone(r.day)}">${pct(r.day)}</b></div><div><small>Trigger-Hoch</small><b>${price(p.trigger)}</b></div><div><small>Rücksetzer-Tief</small><b>${price(p.low)}</b></div><div><small>Rücklauf</small><b>${num(p.retrace*100,1)}%</b></div><div><small>Rücksetzer-Vol.²</small><b>${Number.isFinite(p.ratio)?num(p.ratio,1)+'×':'—'}</b></div><div><small>Spread¹</small><b>${Number.isFinite(r.spread)?num(r.spread,3)+'%':'—'}</b></div></div><div class="break-line">${spark(p.candles)}<small class="tradfi-close">${p.status==='triggered'?(p.closeAbove?'Schluss über Trigger':'Schluss unter Trigger'):'Warte auf neues Hoch'}</small></div></article>`).join(''):`<div class="break-empty"><strong>${busy?'Suche läuft …':'Aktuell kein passendes Muster'}</strong><p>Nur die ausgewerteten Aktien-Perpetuals im gewählten Universum werden berücksichtigt.</p></div>`;
 $('tradfi-more').textContent=candidates.length>30?`Die ersten 30 von ${candidates.length} Treffern · Suche eingrenzen`:'';
}
