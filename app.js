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
const evidenceLabels={price:"取得価格",book_value:"期末簿価",appraisal:"鑑定評価額",leasable_area:"賃貸可能面積",leased_area:"賃貸面積",tenants:"テナント数",occupancy:"稼働率",cap:"直接還元利回り",discount_rate:"割引率",terminal_cap_rate:"最終還元利回り",noi:"NOI"};
const checkLabels={unique_property_id:"物件ID重複",required_fields:"必須項目",numeric_ranges:"数値範囲",evidence_completeness:"Evidence",coordinates:"座標",leased_area_consistency:"面積整合"};

async function loadImportStatus(){
  const badge=document.querySelector("#engineStatus");
  try{
    const res=await fetch("runtime-data/import-status.json",{cache:"no-store"});if(!res.ok)return;
    const status=await res.json(),totals=status.totals||{};
    const layout=status.layout_status==="changed"?"レイアウト変更あり":status.layout_status==="unchanged"?"レイアウト正常":"初回レイアウト";
    badge.textContent=`取込成功・${totals.properties??0}物件・${layout}`;
    badge.classList.toggle("warning",status.layout_status==="changed");badge.hidden=false;
  }catch{badge.hidden=true}
}

async function loadQualityStatus(){
  const button=document.querySelector("#qualityButton"),dialog=document.querySelector("#qualityDialog"),content=document.querySelector("#qualityContent");
  try{
    const res=await fetch("runtime-data/quality-status.json",{cache:"no-store"});if(!res.ok)return;
    const report=await res.json(),totals=report.totals||{};
    const statusText=report.status==="passed"?"合格":report.status==="warning"?"要確認":"不合格";
    button.textContent=`品質 ${statusText}・Evidence ${Number(totals.evidence_coverage_percent||0).toFixed(1)}%`;
    button.className=`quality-button ${report.status||"failed"}`;button.hidden=false;
    const cards=[
      ["物件",`${Number(totals.properties||0).toLocaleString("ja-JP")}件`],
      ["時点データ",`${Number(totals.periods||0).toLocaleString("ja-JP")}件`],
      ["Evidence",`${Number(totals.evidence_coverage_percent||0).toFixed(1)}%`],
      ["座標",`${Number(totals.coordinate_coverage_percent||0).toFixed(1)}%`],
      ["エラー",Number(totals.errors||0).toLocaleString("ja-JP")],
      ["警告",Number(totals.warnings||0).toLocaleString("ja-JP")],
    ].map(([label,value])=>`<div><span>${esc(label)}</span><b>${esc(value)}</b></div>`).join("");
    const checks=(report.checks||[]).map(item=>`<tr><td>${esc(checkLabels[item.code]||item.message||item.code)}</td><td><span class="check-status ${esc(item.status)}">${item.status==="passed"?"正常":item.status==="warning"?"要確認":"エラー"}</span></td><td>${Number(item.count||0).toLocaleString("ja-JP")}</td></tr>`).join("");
    const reits=Object.entries(report.by_reit||{}).map(([name,item])=>`<tr><td>${esc(name)}</td><td>${Number(item.properties||0).toLocaleString("ja-JP")}</td><td>${Number(item.periods||0).toLocaleString("ja-JP")}</td><td>${Number(item.evidence_coverage_percent||0).toFixed(1)}%</td><td>${Number(item.coordinate_coverage_percent||0).toFixed(1)}%</td></tr>`).join("");
    const metricRows=Object.entries(report.metrics||{}).filter(([,item])=>item.available).map(([code,item])=>`<tr><td>${esc(evidenceLabels[code]||code)}</td><td>${Number(item.available||0).toLocaleString("ja-JP")}</td><td>${Number(item.evidence_complete||0).toLocaleString("ja-JP")}</td><td>${Number(item.coverage_percent||0).toFixed(1)}%</td></tr>`).join("");
    const generated=report.generated_at?new Date(report.generated_at).toLocaleString("ja-JP"):"未記録";
    content.innerHTML=`<div class="quality-summary ${esc(report.status)}"><div><span>判定</span><b>${statusText}</b></div><small>検証日時 ${esc(generated)}</small></div><div class="quality-cards">${cards}</div><section class="quality-section"><h3>品質Gate</h3><table><thead><tr><th>検査</th><th>結果</th><th>件数</th></tr></thead><tbody>${checks}</tbody></table></section><section class="quality-section"><h3>投資法人別</h3><div class="table-scroll"><table><thead><tr><th>投資法人</th><th>物件</th><th>時点</th><th>Evidence</th><th>座標</th></tr></thead><tbody>${reits}</tbody></table></div></section><section class="quality-section"><h3>指標別Evidence</h3><div class="table-scroll"><table><thead><tr><th>指標</th><th>数値</th><th>完全</th><th>充足率</th></tr></thead><tbody>${metricRows}</tbody></table></div></section><p class="privacy-note">物件別の問題内容、原本URL、ファイル名、ハッシュはこの画面用APIへ出していません。詳細はMac内のprivate-data/reportsで管理します。</p>`;
    button.onclick=()=>dialog.showModal();
  }catch{button.hidden=true}
}

function sourcePanel(p){
  const src=p.source;if(!src)return'<div class="source">デモデータ（架空）。実データとして利用しないでください。</div>';
  const entries=Object.entries(p.evidence||{}).map(([field,item])=>{const loc=item.locator||{};const position=[loc.page?`p.${loc.page}`:"",loc.sheet||"",loc.cell||loc.cell_range||""].filter(Boolean).join(" / ");return`<li><b>${esc(evidenceLabels[field]||field)}</b><br><code>${esc(position||"位置情報なし")}</code>・${esc(item.unit||"")}・${esc(item.review?.status||"未確認")}</li>`}).join("");
  const legacy=!entries?Object.entries(src.cells||{}).filter(([,v])=>v).map(([k,v])=>`<li><b>${esc(evidenceLabels[k]||k)}</b><br><code>${esc(v)}</code></li>`).join(""):"";
  const retrieved=src.retrieved_at?new Date(src.retrieved_at).toLocaleString("ja-JP"):"未記録";
  return`<div class="source"><b>出典・Evidence</b><p>${esc(src.document||src.title)}・${esc(src.period)}</p><p>取得日時：${esc(retrieved)}<br>SHA-256：<code>${esc((src.sha256||"").slice(0,16))}${src.sha256?"…":"未記録"}</code></p><a href="${esc(src.url)}" target="_blank" rel="noopener">公式IRライブラリを開く</a><details><summary>数値ごとの抽出位置</summary><ul>${entries||legacy||"<li>位置情報なし</li>"}</ul></details></div>`;
}

async function loadData(){
  let payload;
  try{const res=await fetch("runtime-data/properties.json",{cache:"no-store"});if(!res.ok)throw new Error();payload=await res.json()}
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
  const defaultMetric=Object.keys(metrics).find(key=>p.periods.some(period=>period[key]!=null))||"appraisal";
  const metricOptions=Object.entries(metrics).map(([key,item])=>`<option value="${key}"${key===defaultMetric?" selected":""}>${item.label}</option>`).join("");
  const comparableCards=comparablesFor(p).map(item=>`<button class="comparable" data-property-id="${esc(item.property.id)}"><span class="score">類似度 ${item.score}</span><b>${esc(item.property.name)}</b><small>${item.distance==null?"距離不明":`${item.distance.toFixed(1)}km`}・CR ${pct(item.property.cap)}・${area(item.property.leasable_area)}</small></button>`).join("");
  document.querySelector("#detail").innerHTML=`<h2>${esc(p.name)}</h2><div class="address">${esc(p.address)}</div><div><span class="pill">${esc(p.type)}</span>${p.geocode?.quality==="automatic"?'<span class="pill neutral">座標：自動取得</span>':""}</div><div class="metrics"><div class="metric"><span>取得価格</span><b>${yen(p.price)}</b></div><div class="metric"><span>鑑定評価額</span><b>${yen(p.appraisal)}</b></div><div class="metric"><span>直接還元利回り（CR）</span><b>${pct(p.cap)}</b></div><div class="metric"><span>稼働率</span><b>${pct(p.occupancy)}</b></div><div class="metric"><span>NOI（当期）</span><b>${yen(p.noi)}</b></div><div class="metric"><span>期末簿価</span><b>${yen(p.book_value)}</b></div><div class="metric"><span>賃貸可能面積</span><b>${area(p.leasable_area)}</b></div><div class="metric"><span>テナント数</span><b>${text(p.tenants)}</b></div></div><section class="analysis"><div class="analysis-heading"><div><span class="eyebrow">HISTORY</span><h3>物件データの推移</h3></div><select id="historyMetric" aria-label="推移指標">${metricOptions}</select></div><canvas id="historyChart" aria-label="物件データ推移グラフ"></canvas><div id="historySummary"></div></section><section class="analysis"><div class="analysis-heading"><div><span class="eyebrow">COMPARABLES</span><h3>類似物件 上位5件</h3></div></div><p class="method">距離35%、面積25%、取得価格15%、CR15%、稼働率10%で算出</p><div class="comparable-list">${comparableCards||'<p class="empty">比較できる物件がありません。</p>'}</div></section>${sourcePanel(p)}`;
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
loadImportStatus();
loadQualityStatus();
