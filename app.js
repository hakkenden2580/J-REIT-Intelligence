let properties=[];let visible=[];let selected=null;
const map=L.map("map").setView([35.55,139.55],7);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"&copy; OpenStreetMap contributors"}).addTo(map);
const markers=L.layerGroup().addTo(map);
const yen=n=>n==null?"—":`${Number(n).toLocaleString("ja-JP",{maximumFractionDigits:1})}百万円`;
const pct=n=>n==null?"—":`${Number(n).toFixed(1)}%`;
const area=n=>n==null?"—":`${Number(n).toLocaleString("ja-JP")}㎡`;
const text=n=>n==null?"—":Number(n).toLocaleString("ja-JP");
const esc=s=>String(s??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const region=document.querySelector("#region");

async function loadData(){
  let payload;
  try{const res=await fetch("data/properties.json",{cache:"no-store"});if(!res.ok)throw new Error();payload=await res.json()}
  catch{payload=await (await fetch("data/demo-properties.json")).json()}
  properties=payload.properties;visible=[...properties];
  document.querySelector("#dataset").textContent=payload.meta.label;
  document.querySelector("#dataset").classList.toggle("demo",payload.meta.dataset==="demo");
  [...new Set(properties.map(x=>x.region).filter(Boolean))].forEach(x=>region.add(new Option(x,x)));
  render();
  const coords=properties.filter(p=>p.lat!=null&&p.lng!=null);
  if(coords.length)map.fitBounds(coords.map(p=>[p.lat,p.lng]),{padding:[30,30]});
}

function selectProperty(p){
  selected=p;
  const src=p.source;
  const evidence=src?Object.entries(src.cells||{}).filter(([,v])=>v).map(([k,v])=>`<li><code>${esc(k)}</code> ${esc(v)}</li>`).join(""):"";
  document.querySelector("#detail").innerHTML=`<h2>${esc(p.name)}</h2><div class="address">${esc(p.address)}</div><div><span class="pill">${esc(p.type)}</span>${p.geocode?.quality==="automatic"?'<span class="pill neutral">座標：自動取得</span>':""}</div><div class="metrics"><div class="metric"><span>取得価格</span><b>${yen(p.price)}</b></div><div class="metric"><span>鑑定評価額</span><b>${yen(p.appraisal)}</b></div><div class="metric"><span>直接還元利回り（CR）</span><b>${pct(p.cap)}</b></div><div class="metric"><span>稼働率</span><b>${pct(p.occupancy)}</b></div><div class="metric"><span>NOI（当期）</span><b>${yen(p.noi)}</b></div><div class="metric"><span>期末簿価</span><b>${yen(p.book_value)}</b></div><div class="metric"><span>賃貸可能面積</span><b>${area(p.leasable_area)}</b></div><div class="metric"><span>テナント数</span><b>${text(p.tenants)}</b></div><div class="metric"><span>割引率（DR）</span><b>${pct(p.discount_rate)}</b></div><div class="metric"><span>最終還元利回り</span><b>${pct(p.terminal_cap_rate)}</b></div></div>${src?`<div class="source"><b>出典</b><p>${esc(src.document)}・${esc(src.period)}</p><a href="${esc(src.url)}" target="_blank" rel="noopener">公式IRライブラリを開く</a><details><summary>セル位置</summary><ul>${evidence}</ul></details></div>`:'<div class="source">デモデータ（架空）。実データとして利用しないでください。</div>'}`;
  if(p.lat!=null&&p.lng!=null)map.flyTo([p.lat,p.lng],15);
}

function render(){
  const q=document.querySelector("#search").value.toLowerCase(),r=region.value;
  visible=properties.filter(p=>(!r||p.region===r)&&(`${p.name} ${p.address} ${p.reit}`.toLowerCase().includes(q)));
  document.querySelector("#count").textContent=visible.length;
  document.querySelector("#list").innerHTML=visible.map(p=>`<div class="item${selected?.id===p.id?" active":""}" data-id="${esc(p.id)}"><b>${esc(p.name)}</b><small>${esc(p.address)}</small><br><span class="pill">${esc(p.region||p.type)}・CR ${pct(p.cap)}</span></div>`).join("");
  markers.clearLayers();visible.filter(p=>p.lat!=null&&p.lng!=null).forEach(p=>L.marker([p.lat,p.lng]).addTo(markers).bindTooltip(esc(p.name)).on("click",()=>selectProperty(p)));
  document.querySelectorAll(".item").forEach(el=>el.onclick=()=>selectProperty(properties.find(p=>p.id===el.dataset.id)));
}
document.querySelector("#search").oninput=render;region.onchange=render;
document.querySelector("#export").onclick=()=>{if(!visible.length)return;const keys=["id","reit_code","reit","name","type","region","address","lat","lng","price","book_value","appraisal","cap","discount_rate","terminal_cap_rate","occupancy","noi","leasable_area","leased_area","tenants"];const csv=[keys.join(","),...visible.map(p=>keys.map(k=>`"${String(p[k]??"").replaceAll('"','""')}"`).join(","))].join("\n");const a=document.createElement("a");a.href=URL.createObjectURL(new Blob(["\ufeff"+csv],{type:"text/csv"}));a.download="jreit-properties.csv";a.click();URL.revokeObjectURL(a.href)};
loadData().catch(err=>{document.querySelector("#dataset").textContent="読込エラー";document.querySelector("#detail").innerHTML=`<p class="error">データを読み込めませんでした。${esc(err.message)}</p>`});
