/* Deterministic price/volume heuristic, not a continuation probability. */
(function(root){
'use strict';
const MINUTE=60000;
function aggregate(raw,minutes,end){const duration=minutes*MINUTE,groups=new Map();for(const row of raw){const c=row.slice(0,7).map(Number);if(c.length<7||c.some(v=>!Number.isFinite(v))||c[0]%MINUTE||c[0]+MINUTE>end||c[1]<=0||c[4]<=0||c[2]<Math.max(c[1],c[4])||c[3]>Math.min(c[1],c[4])||c[6]<0)continue;const t=Math.floor(c[0]/duration)*duration;if(t+duration>end)continue;if(!groups.has(t))groups.set(t,new Map());groups.get(t).set(c[0],c)}const result=[];for(const [t,g]of groups){if(g.size!==minutes)continue;const rows=[];for(let i=0;i<minutes;i++){const c=g.get(t+i*MINUTE);if(!c)break;rows.push(c)}if(rows.length!==minutes)continue;result.push([t,rows[0][1],Math.max(...rows.map(c=>c[2])),Math.min(...rows.map(c=>c[3])),rows.at(-1)[4],rows.reduce((s,c)=>s+c[5],0),rows.reduce((s,c)=>s+c[6],0)])}return result.sort((a,b)=>a[0]-b[0])}
function detect(raw,end,options={}){
 const opts={minutes:1,pullbackBars:3,minImpulse:1,minVolume:1.5,maxRetracement:.5,requireQuiet:true,...options};const {minutes,pullbackBars}=opts;
 if(![1,5].includes(minutes)||![2,3,4].includes(pullbackBars))return [];
 const candles=aggregate(raw,minutes,end),duration=minutes*MINUTE,lastClosed=Math.floor(end/duration)*duration;if(!candles.length||candles.at(-1)[0]+duration!==lastClosed)return [];
 const found=[];
 for(const side of ['long','short']){const sign=side==='long'?1:-1,convert=c=>({t:c[0],o:sign*c[1],h:sign*(sign===1?c[2]:c[3]),l:sign*(sign===1?c[3]:c[2]),c:sign*c[4],v:c[6]}),bars=candles.map(convert);
 for(const confirmed of [false,true]){const pbEnd=bars.length-(confirmed?1:0),pbStart=pbEnd-pullbackBars;if(pbStart<12)continue;const pb=bars.slice(pbStart,pbEnd);if(pb.some((b,i)=>b.c>=b.o||(i>0&&b.c>=pb[i-1].c)))continue;
 for(let length=2;length<=6;length++){const start=pbStart-length;if(start<10)continue;const baseline=bars.slice(start-10,start),impulse=bars.slice(start,pbStart),segment=bars.slice(start-10);if(segment.some((b,i)=>i>0&&b.t-segment[i-1].t!==duration))continue;
 const origin=impulse[0].o,finish=impulse.at(-1).c,peak=Math.max(...impulse.map(b=>b.h)),low=Math.min(...pb.map(b=>b.l)),swing=peak-origin,impulsePct=(finish-origin)/Math.abs(origin)*100,baselineLevel=Math.max(...baseline.map(b=>b.h));
 if(!(swing>0)||impulsePct<opts.minImpulse||finish<=baselineLevel||origin>baselineLevel||impulse.filter(b=>b.c>b.o).length<Math.ceil(length*2/3)||finish<peak-swing*.2)continue;
 const impAvg=impulse.reduce((s,b)=>s+b.v,0)/length,baseAvg=baseline.reduce((s,b)=>s+b.v,0)/10,pbAvg=pb.reduce((s,b)=>s+b.v,0)/pullbackBars,volumeRatio=baseAvg>0?impAvg/baseAvg:0,retracement=(peak-low)/swing,bodyRatio=(pb.reduce((s,b)=>s+Math.abs(b.c-b.o),0)/pullbackBars)/(impulse.reduce((s,b)=>s+Math.abs(b.c-b.o),0)/length||Infinity);
 if(volumeRatio<opts.minVolume||retracement<.05||retracement>opts.maxRetracement||low<=origin||bodyRatio>=.8||(opts.requireQuiet&&pbAvg>=impAvg))continue;
 const trigger=pb.at(-1).h,last=bars.at(-1);if(confirmed&&!(last.c>last.o&&last.c>trigger&&last.l>low))continue;
 found.push({side,status:confirmed?'confirmed':'pullback',minutes,pullbackBars,impulseBars:length,impulsePct:sign*impulsePct,volumeRatio,pullbackVolumeRatio:impAvg>0?pbAvg/impAvg:NaN,retracement,trigger:sign*trigger,invalidation:sign*low,impulseExtreme:sign*peak,rangeLevel:sign*baselineLevel,start:impulse[0].t,pullbackStart:pb[0].t,pullbackEnd:pb.at(-1).t+duration,end:lastClosed,setupMinutes:(length+pullbackBars+(confirmed?1:0))*minutes,candles:candles.slice(Math.max(0,start-4))});
 }
 }
 }
 return found.sort((a,b)=>(b.status==='confirmed')-(a.status==='confirmed')||b.volumeRatio-a.volumeRatio||Math.abs(b.impulsePct)-Math.abs(a.impulsePct)).filter((a,i,all)=>all.findIndex(b=>b.side===a.side)===i);
}
root.PulsePattern={aggregate,detect};
})(typeof globalThis!=='undefined'?globalThis:this);
