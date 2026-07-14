let properties=[];let visible=[];let selected=null;
const map=L.map("map").setView([35.55,139.55],7);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"&copy; OpenStreetMap contributors"}).addTo(map);
const markers=L.layerGroup().addTo(map);
const yen=n=>n==null?"—":`${Number(n).toLocaleString("ja-JP",{maximumFractionDigits:1})}百万円`;
const pct=n=>n==null?"—":`${Number(n).toFixed(1)}%`;
const area=n=>n==null?"—":`${Number(n).toLocaleString("ja-JP")}㎡`;
const text=n=>n==null?"—":Number(n).toLocaleString("ja-JP");
const esc=s=>String(s??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const reitFilter=document.querySelector("#reit"),typeFilter=document.querySelector("#type"),region=document.querySelector("#region");
const metrics={
  cap:{label:"直接還元利回り（CR）",short:"CR",format:pct,color:"#2563eb"},
  noi:{label:"NOI（当期）",short:"NOI",format:yen,color:"#059669"},
  occupancy:{label:"稼働率",short:"稼働率",format:pct,color:"#7c3aed"},
  appraisal:{label:"鑑定評価額",short:"鑑定評価額",format:yen,color:"#dc6b19"}
};

async function loadData(){
  let payload;
  try{const res=await fetch("data/properties.json",{cache:"no-store"});if(!res.ok)throw new Error();payload=await res.json()}
  catch{payload=await (await fetch("data/demo-properties.json")).json()}
  properties=payload.properties.map(p=>({...p,periods:p.periods?.length?p.periods:[{period_no:null,period:"最新",as_of_date:null,cap:p.cap,noi:p.noi,occupancy:p.occupancy,appraisal:p.appraisal}]}));
  visible=[...properties];
  document.querySelector("#dataset").textContent=payload.meta.label;
  document.querySelector("#dataset").classList.toggle("demo",payload.meta.dataset==="demo");
  [...new Set(properties.map(x=>x.reit).filter(Boolean))].sort().forEach(x=>reitFilter.add(new Option(x,x)));
  [...new Set(properties.map(x=>x.type).filter(Boolean))].sort().forEach(x=>typeFilter.add(new Option(x,x)));
  [...new Set(properties.map(x=>x.region).filter(Boolean))].sort().forEach(x=>region.add(new Option(x,x)));
  render();
  const coords=properties.filter(p=>p.lat!=null&&p.lng!=null);
  if(coords.length)map.fitBounds(coords.map(p=>[p.lat,p.lng]),{padding:[30,30]});
}

function haversine(a,b){
  if([a.lat,a.lng,b.lat,b.lng].some(v=>v==null))return null;
  const rad=x=>x*Math.PI/180,dLat=rad(b.lat-a.lat),dLng=rad(b.lng-a.lng);
  const h=Math.sin(dLat/2)**2+Math.cos(rad(a.lat))*Math.cos(rad(b.lat))*Math.sin(dLng/2)**2;
  return 6371*2*Math.atan2(Math.sqrt(h),Math.sqrt(1-h));
}
function scaledDifference(a,b,scale,weight){if(a==null||b==null)return weight*.5;return Math.min(Math.abs(a-b)/scale,1)*weight}
function ratioDifference(a,b,weight){if(!a||!b)return weight*.5;return Math.min(Math.abs(Math.log(a/b))/Math.log(4),1)*weight}
function comparableScore(base,candidate){
  const distance=haversine(base,candidate);
  const penalty=scaledDifference(distance,0,50,35)+ratioDifference(base.leasable_area,candidate.leasable_area,25)+ratioDifference(base.price,candidate.price,15)+scaledDifference(base.cap,candidate.cap,1.5,15)+scaledDifference(base.occupancy,candidate.occupancy,10,10);
  return{property:candidate,score:Math.max(0,Math.round(100-penalty)),distance};
}
function comparablesFor(p){return properties.filter(x=>x.id!==p.id&&x.type===p.type).map(x=>comparableScore(p,x)).sort((a,b)=>b.score-a.score).slice(0,5)}

function selectProperty(p){
  selected=p;
  const src=p.source;
  const evidence=src?Object.entries(src.cells||{}).filter(([,v])=>v).map(([k,v])=>`<li><code>${esc(k)}</code> ${esc(v)}</li>`).join(""):"";
  const defaultMetric=Object.keys(metrics).find(key=>p.periods.some(period=>period[key]!=null))||"appraisal";
  const metricOptions=Object.entries(metrics).map(([key,item])=>`<option value="${key}"${key===defaultMetric?" selected":""}>${item.label}</option>`).join("");
  const comparableCards=comparablesFor(p).map(item=>`<button class="comparable" data-property-id="${esc(item.property.id)}"><span class="score">類似度 ${item.score}</span><b>${esc(item.property.name)}</b><small>${item.distance==null?"距離不明":`${item.distance.toFixed(1)}km`}・CR ${pct(item.property.cap)}・${area(item.property.leasable_area)}</small></button>`).join("");
  document.querySelector("#detail").innerHTML=`<h2>${esc(p.name)}</h2><div class="address">${esc(p.address)}</div><div><span class="pill">${esc(p.type)}</span>${p.geocode?.quality==="automatic"?'<span class="pill neutral">座標：自動取得</span>':""}</div><div class="metrics"><div class="metric"><span>取得価格</span><b>${yen(p.price)}</b></div><div class="metric"><span>鑑定評価額</span><b>${yen(p.appraisal)}</b></div><div class="metric"><span>直接還元利回り（CR）</span><b>${pct(p.cap)}</b></div><div class="metric"><span>稼働率</span><b>${pct(p.occupancy)}</b></div><div class="metric"><span>NOI（当期）</span><b>${yen(p.noi)}</b></div><div class="metric"><span>期末簿価</span><b>${yen(p.book_value)}</b></div><div class="metric"><span>賃貸可能面積</span><b>${area(p.leasable_area)}</b></div><div class="metric"><span>テナント数</span><b>${text(p.tenants)}</b></div></div><section class="analysis"><div class="analysis-heading"><div><span class="eyebrow">HISTORY</span><h3>物件データの推移</h3></div><select id="historyMetric" aria-label="推移指標">${metricOptions}</select></div><canvas id="historyChart" aria-label="物件データ推移グラフ"></canvas><div id="historySummary"></div></section><section class="analysis"><div class="analysis-heading"><div><span class="eyebrow">COMPARABLES</span><h3>類似物件 上位5件</h3></div></div><p class="method">距離35%、面積25%、取得価格15%、CR15%、稼働率10%で算出</p><div class="comparable-list">${comparableCards||'<p class="empty">比較できる物件がありません。</p>'}</div></section>${src?`<div class="source"><b>出典</b><p>${esc(src.document)}・${esc(src.period)}</p><a href="${esc(src.url)}" target="_blank" rel="noopener">公式IRライブラリを開く</a><details><summary>最新期のセル位置</summary><ul>${evidence}</ul></details></div>`:'<div class="source">デモデータ（架空）。実データとして利用しないでください。</div>'}`;
  const selector=document.querySelector("#historyMetric");selector.onchange=()=>drawHistory(p,selector.value);drawHistory(p,selector.value);
  document.querySelectorAll(".comparable").forEach(button=>button.onclick=()=>selectProperty(properties.find(item=>item.id===button.dataset.propertyId)));
  document.querySelectorAll(".item").forEach(item=>item.classList.toggle("active",item.dataset.id===p.id));
  if(p.lat!=null&&p.lng!=null)map.flyTo([p.lat,p.lng],15);
}

function drawHistory(p,metricKey){
  const metric=metrics[metricKey],history=[...p.periods].sort((a,b)=>(a.as_of_date||"").localeCompare(b.as_of_date||""));
  const values=history.map(item=>item[metricKey]);const available=values.filter(v=>v!=null);
  const canvas=document.querySelector("#historyChart");if(!canvas)return;
  const width=Math.max(canvas.clientWidth,320),height=190,dpr=window.devicePixelRatio||1;
  canvas.width=width*dpr;canvas.height=height*dpr;const ctx=canvas.getContext("2d");ctx.scale(dpr,dpr);ctx.clearRect(0,0,width,height);
  const pad={left:48,right:14,top:18,bottom:30},plotW=width-pad.left-pad.right,plotH=height-pad.top-pad.bottom;
  if(!available.length){ctx.fillStyle="#64748b";ctx.font="13px sans-serif";ctx.fillText("この指標の履歴はありません",pad.left,90);return}
  let min=Math.min(...available),max=Math.max(...available);if(min===max){min-=Math.abs(min||1)*.05;max+=Math.abs(max||1)*.05}else{const margin=(max-min)*.12;min-=margin;max+=margin}
  ctx.font="10px sans-serif";ctx.textAlign="right";ctx.textBaseline="middle";
  for(let i=0;i<4;i++){const y=pad.top+plotH*i/3,value=max-(max-min)*i/3;ctx.strokeStyle="#e2e8f0";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(pad.left,y);ctx.lineTo(width-pad.right,y);ctx.stroke();ctx.fillStyle="#64748b";ctx.fillText(metricKey==="noi"||metricKey==="appraisal"?Math.round(value).toLocaleString():value.toFixed(1),pad.left-7,y)}
  const xAt=i=>pad.left+(history.length===1?plotW/2:plotW*i/(history.length-1)),yAt=value=>pad.top+(max-value)/(max-min)*plotH;
  ctx.strokeStyle=metric.color;ctx.lineWidth=2.5;ctx.lineJoin="round";ctx.beginPath();let started=false;
  values.forEach((value,i)=>{if(value==null){started=false;return}const x=xAt(i),y=yAt(value);if(!started){ctx.moveTo(x,y);started=true}else ctx.lineTo(x,y)});ctx.stroke();
  values.forEach((value,i)=>{if(value==null)return;ctx.fillStyle="#fff";ctx.strokeStyle=metric.color;ctx.lineWidth=2;ctx.beginPath();ctx.arc(xAt(i),yAt(value),3.5,0,Math.PI*2);ctx.fill();ctx.stroke()});
  ctx.textAlign="center";ctx.textBaseline="top";ctx.fillStyle="#64748b";history.forEach((item,i)=>{if(history.length<=6||i%2===0||i===history.length-1)ctx.fillText(item.period_no?`${item.period_no}期`:item.period,xAt(i),height-pad.bottom+9)});
  const latest=[...history].reverse().find(item=>item[metricKey]!=null),previous=[...history].reverse().filter(item=>item[metricKey]!=null)[1];
  const delta=latest&&previous?latest[metricKey]-previous[metricKey]:null;
  document.querySelector("#historySummary").innerHTML=`<div class="history-summary"><div><span>最新値</span><b>${latest?metric.format(latest[metricKey]):"—"}</b></div><div><span>前期差</span><b class="${delta>0?"up":delta<0?"down":""}">${delta==null?"—":`${delta>0?"+":""}${metricKey==="noi"||metricKey==="appraisal"?`${delta.toLocaleString("ja-JP",{maximumFractionDigits:1})}百万円`:`${delta.toFixed(1)}pt`}`}</b></div><div><span>データ期間</span><b>${available.length}期</b></div></div>`;
}

function render(){
  const q=document.querySelector("#search").value.toLowerCase(),reit=reitFilter.value,type=typeFilter.value,r=region.value;
  visible=properties.filter(p=>(!reit||p.reit===reit)&&(!type||p.type===type)&&(!r||p.region===r)&&(`${p.name} ${p.address} ${p.reit}`.toLowerCase().includes(q)));
  document.querySelector("#count").textContent=visible.length;
  document.querySelector("#list").innerHTML=visible.map(p=>`<div class="item${selected?.id===p.id?" active":""}" data-id="${esc(p.id)}"><b>${esc(p.name)}</b><small>${esc(p.address)}</small><br><span class="pill">${esc(p.region||p.type)}・CR ${pct(p.cap)}</span></div>`).join("");
  markers.clearLayers();visible.filter(p=>p.lat!=null&&p.lng!=null).forEach(p=>L.marker([p.lat,p.lng]).addTo(markers).bindTooltip(esc(p.name)).on("click",()=>selectProperty(p)));
  document.querySelectorAll(".item").forEach(el=>el.onclick=()=>selectProperty(properties.find(p=>p.id===el.dataset.id)));
}
document.querySelector("#search").oninput=render;reitFilter.onchange=render;typeFilter.onchange=render;region.onchange=render;
document.querySelector("#export").onclick=()=>{if(!visible.length)return;const keys=["id","reit_code","reit","name","type","region","address","lat","lng","price","book_value","appraisal","cap","discount_rate","terminal_cap_rate","occupancy","noi","leasable_area","leased_area","tenants"];const csv=[keys.join(","),...visible.map(p=>keys.map(k=>`"${String(p[k]??"").replaceAll('"','""')}"`).join(","))].join("\n");const a=document.createElement("a");a.href=URL.createObjectURL(new Blob(["\ufeff"+csv],{type:"text/csv"}));a.download="jreit-properties.csv";a.click();URL.revokeObjectURL(a.href)};
window.addEventListener("resize",()=>{if(selected){const metric=document.querySelector("#historyMetric");if(metric)drawHistory(selected,metric.value)}});
loadData().catch(err=>{document.querySelector("#dataset").textContent="読込エラー";document.querySelector("#detail").innerHTML=`<p class="error">データを読み込めませんでした。${esc(err.message)}</p>`});
