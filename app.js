let properties=[];let visible=[];let selected=null;let pdfCatalog=null;let comparisonMetric="cap";
const comparisonIds=new Set(),comparisonLimit=8;
const comparisonColors=["#2563eb","#db2777","#059669","#d97706","#7c3aed","#0891b2","#dc2626","#4f46e5"];
const map=L.map("map").setView([35.55,139.55],7);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"&copy; OpenStreetMap contributors"}).addTo(map);
const markers=L.layerGroup().addTo(map);
const yen=n=>n==null?"—":`${Number(n).toLocaleString("ja-JP",{maximumFractionDigits:1})}百万円`;
const pct=n=>n==null?"—":`${Number(n).toFixed(1)}%`;
const area=n=>n==null?"—":`${Number(n).toLocaleString("ja-JP")}㎡`;
const text=n=>n==null?"—":Number(n).toLocaleString("ja-JP");
const esc=s=>String(s??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const safeUrl=value=>{try{const url=new URL(String(value||""));return ["https:","http:"].includes(url.protocol)?url.href:""}catch{return""}};
const reitFilter=document.querySelector("#reit"),typeFilter=document.querySelector("#type"),region=document.querySelector("#region");
const metrics={
  cap:{label:"直接還元利回り（CR）",short:"CR",format:pct,color:"#2563eb"},
  noi:{label:"NOI（当期）",short:"NOI",format:yen,color:"#059669"},
  occupancy:{label:"稼働率",short:"稼働率",format:pct,color:"#7c3aed"},
  appraisal:{label:"鑑定評価額",short:"鑑定評価額",format:yen,color:"#dc6b19"}
};
const evidenceLabels={price:"取得価格",book_value:"期末簿価",appraisal:"鑑定評価額",leasable_area:"賃貸可能面積",leased_area:"賃貸面積",tenants:"テナント数",occupancy:"稼働率",cap:"直接還元利回り",discount_rate:"割引率",terminal_cap_rate:"最終還元利回り",noi:"NOI"};
const checkLabels={unique_property_id:"物件ID重複",required_fields:"必須項目",numeric_ranges:"数値範囲",evidence_completeness:"Evidence",coordinates:"座標",leased_area_consistency:"面積整合"};
const pdfMetricLabels={rental_income_million_yen:"不動産賃貸収入",occupancy_rate_percent:"期中平均稼働率",portfolio_noi_million_yen:"賃貸NOI",acquisition_price_million_yen:"取得価格",disposal_price_million_yen:"譲渡価格",noi_yield_percent:"NOI利回り"};
const eventLabels={acquisition_planned:"取得予定",additional_acquisition_planned:"追加取得予定",acquisition:"取得",disposal_planned:"譲渡予定"};

const normalizedPropertyName=value=>String(value||"").normalize("NFKC").replace(/[\s　]/g,"").replace(/[（(]追加取得[）)]/g,"");
const eventPage=event=>Object.values(event.evidence||{}).map(item=>item.locator?.page).find(Boolean);
const pdfDocuments=()=>pdfCatalog?.supplements||[];
const allPdfEvents=()=>pdfDocuments().flatMap(supplement=>(supplement.property_events||[]).map(event=>({...event,_source:supplement.meta?.source||{}})));
const pdfEventsFor=p=>{const name=normalizedPropertyName(p.name);return allPdfEvents().filter(event=>{const eventName=normalizedPropertyName(event.property_name);return name===eventName||name.includes(eventName)||eventName.includes(name)})};
const pdfValue=(metricCode,value)=>metricCode.includes("percent")?pct(value):yen(value);
const reviewLabel=status=>({approved:"確認済み",rejected:"却下",not_required:"確認不要",pending:"未確認"}[status]||"未確認");

function pdfEvidenceList(evidence){
  return Object.values(evidence||{}).map(item=>{const page=item.locator?.page?`p.${item.locator.page}`:"ページ不明";const confidence=item.extraction?.confidence==null?"":`・信頼度 ${(Number(item.extraction.confidence)*100).toFixed(0)}%`;const review=reviewLabel(item.review?.status);return`<li><b>${esc(pdfMetricLabels[item.metric_code]||evidenceLabels[item.metric_code]||item.metric_code)}</b><br><code>${esc(page)}</code>${esc(confidence)}・${esc(review)}</li>`}).join("");
}

function pdfEventCard(event,{compact=false}={}){
  const page=eventPage(event),label=eventLabels[event.event_type]||event.event_type;
  return`<article class="pdf-event-card ${esc(event.event_type)}"><div class="pdf-event-heading"><span class="event-type">${esc(label)}</span><b>${esc(event.property_name)}</b></div><div class="pdf-event-metrics"><div><span>取引価格</span><b>${yen(event.price_million_yen)}</b></div><div><span>NOI利回り</span><b>${pct(event.noi_yield_percent)}</b></div></div><small>${esc(event.announced_period||"")}${page?`・PDF p.${page}`:""}</small>${compact?"":`<details><summary>数値ごとのPDF Evidence</summary><ul>${pdfEvidenceList(event.evidence)}</ul></details>`}</article>`;
}

function pdfEventPanel(p){
  const events=pdfEventsFor(p);if(!events.length)return"";
  const sources=[...new Map(events.map(event=>[`${event._source.document||""}|${event._source.url||""}`,event._source])).values()];
  const sourceLines=sources.map(source=>{const url=safeUrl(source.url),retrieved=source.retrieved_at?new Date(source.retrieved_at).toLocaleString("ja-JP"):"未記録";return`${esc(source.document||"決算説明会資料")}・取得日時 ${esc(retrieved)}${url?`・<a href="${esc(url)}" target="_blank" rel="noopener">公式IR</a>`:""}`}).join("<br>");
  return`<section class="analysis pdf-events"><div class="analysis-heading"><div><span class="eyebrow">DISCLOSURE EVENT</span><h3>取得・売却イベント</h3></div></div>${events.map(event=>pdfEventCard(event)).join("")}<p class="pdf-source-line">${sourceLines}</p><p class="method">PDF抽出値は確認状態を表示しています。投資・融資判断前に原資料と照合してください。</p></section>`;
}

function renderPdfDashboard(){
  const button=document.querySelector("#pdfStatus"),dialog=document.querySelector("#pdfDialog"),content=document.querySelector("#pdfContent");
  const documents=pdfDocuments();if(!documents.length){button.hidden=true;return}
  const review=pdfCatalog.meta?.review_summary||{},eventCount=Number(pdfCatalog.meta?.event_count||allPdfEvents().length);
  const reviewCards=[["Evidence",review.total||0],["確認済み",review.approved||0],["未確認",review.pending||0],["却下",review.rejected||0]].map(([label,value])=>`<div><span>${esc(label)}</span><b>${Number(value).toLocaleString("ja-JP")}</b></div>`).join("");
  const documentSections=documents.map(supplement=>{const metrics=(supplement.portfolio_metrics||[]).map(item=>`<div><span>${esc(pdfMetricLabels[item.metric_code]||item.metric_code)}</span><b>${pdfValue(item.metric_code,item.value)}</b><small>${item.evidence?.locator?.page?`PDF p.${item.evidence.locator.page}`:""}・${esc(reviewLabel(item.evidence?.review?.status))}</small></div>`).join("");const events=(supplement.property_events||[]).map(event=>pdfEventCard(event,{compact:true})).join("");const source=supplement.meta?.source||{},url=safeUrl(source.url),retrieved=source.retrieved_at?new Date(source.retrieved_at).toLocaleString("ja-JP"):"未記録";return`<section class="pdf-document-section"><div class="pdf-document"><div><span>資料</span><b>${esc(source.document||"決算説明会資料")}</b><small>${esc(supplement.meta?.period||"")}・取得日時 ${esc(retrieved)}</small></div>${url?`<a href="${esc(url)}" target="_blank" rel="noopener">公式IRライブラリ</a>`:""}</div><section class="quality-section"><h3>ポートフォリオ指標</h3><div class="pdf-metric-cards">${metrics}</div></section><section class="quality-section"><h3>取得・売却イベント</h3><div class="pdf-event-list">${events}</div></section></section>`}).join("");
  button.textContent=`PDF開示 ${eventCount}件`;button.hidden=false;
  content.innerHTML=`<section class="quality-section pdf-review-summary"><h3>人手確認状況</h3><div class="pdf-review-cards">${reviewCards}</div><p class="method">確認操作はMacのターミナルで行い、履歴はprivate-data/reviewsだけに保存します。</p></section>${documentSections}<p class="privacy-note">原本PDF、SHA-256、ダウンロードURL、正規化済み実データ、確認者名、確認メモはブラウザへ公開していません。この表示はMac内のprivate-dataをlocalhost専用APIでサニタイズしたものです。</p>`;
  button.onclick=()=>dialog.showModal();
}

async function loadPdfSupplement(){
  try{let res=await fetch("runtime-data/pdf-supplements.json",{cache:"no-store"});if(res.ok){pdfCatalog=await res.json()}else{res=await fetch("runtime-data/nbf-pdf.json",{cache:"no-store"});if(!res.ok)return;const legacy=await res.json();pdfCatalog={meta:{supplement_count:1,event_count:legacy.property_events?.length||0,review_summary:legacy.review_summary||{}},supplements:[legacy]}}renderPdfDashboard()}
  catch{pdfCatalog=null;renderPdfDashboard()}
}

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

async function loadChangeStatus(){
  const button=document.querySelector("#changeButton"),dialog=document.querySelector("#changeDialog"),content=document.querySelector("#changeContent");
  try{
    const res=await fetch("runtime-data/change-status.json",{cache:"no-store"});if(!res.ok)return;
    const report=await res.json(),totals=report.totals||{};
    const affected=Number(totals.properties_added||0)+Number(totals.properties_removed||0)+Number(totals.properties_changed||0);
    const statusText=report.status==="baseline"?"基準作成":report.status==="changed"?`${affected}物件更新`:"変更なし";
    button.textContent=`差分 ${statusText}`;button.className=`change-button ${report.status||"baseline"}`;button.hidden=false;
    const cards=[
      ["更新前",`${Number(totals.previous_properties||0).toLocaleString("ja-JP")}物件`],
      ["更新後",`${Number(totals.current_properties||0).toLocaleString("ja-JP")}物件`],
      ["新規",`${Number(totals.properties_added||0).toLocaleString("ja-JP")}物件`],
      ["除外候補",`${Number(totals.properties_removed||0).toLocaleString("ja-JP")}物件`],
      ["変更物件",`${Number(totals.properties_changed||0).toLocaleString("ja-JP")}物件`],
      ["追加時点",`${Number(totals.periods_added||0).toLocaleString("ja-JP")}件`],
      ["数値変更",`${Number(totals.metric_values_changed||0).toLocaleString("ja-JP")}件`],
      ["出典更新",`${Number(totals.evidence_relinked||0).toLocaleString("ja-JP")}件`],
    ].map(([label,value])=>`<div><span>${esc(label)}</span><b>${esc(value)}</b></div>`).join("");
    const reits=Object.entries(report.by_reit||{}).map(([name,item])=>`<tr><td>${esc(name)}</td><td>${Number(item.properties_added||0).toLocaleString("ja-JP")}</td><td>${Number(item.properties_removed||0).toLocaleString("ja-JP")}</td><td>${Number(item.properties_changed||0).toLocaleString("ja-JP")}</td><td>${Number(item.periods_added||0).toLocaleString("ja-JP")}</td><td>${Number(item.metric_values_changed||0).toLocaleString("ja-JP")}</td></tr>`).join("");
    const metricRows=Object.entries(report.by_metric||{}).filter(([,item])=>Object.values(item).some(Number)).map(([code,item])=>`<tr><td>${esc(evidenceLabels[code]||code)}</td><td>${Number(item.added||0).toLocaleString("ja-JP")}</td><td>${Number(item.removed||0).toLocaleString("ja-JP")}</td><td>${Number(item.changed||0).toLocaleString("ja-JP")}</td><td>${Number(item.evidence_relinked||0).toLocaleString("ja-JP")}</td></tr>`).join("");
    const generated=report.generated_at?new Date(report.generated_at).toLocaleString("ja-JP"):"未記録";
    const description=report.status==="baseline"?"今回のデータを今後の比較基準として保存しました。":report.status==="unchanged"?"前回の正常データから業務値の変更はありません。":"前回の正常データとの差分を検出しました。除外は売却と断定せず、確認候補として扱います。";
    content.innerHTML=`<div class="change-summary ${esc(report.status)}"><div><span>判定</span><b>${esc(statusText)}</b></div><small>比較日時 ${esc(generated)}</small></div><p class="change-description">${esc(description)}</p><div class="change-cards">${cards}</div><section class="quality-section"><h3>投資法人別差分</h3><div class="table-scroll"><table><thead><tr><th>投資法人</th><th>新規</th><th>除外候補</th><th>変更物件</th><th>追加時点</th><th>数値変更</th></tr></thead><tbody>${reits||'<tr><td colspan="6">差分なし</td></tr>'}</tbody></table></div></section><section class="quality-section"><h3>指標別差分</h3><div class="table-scroll"><table><thead><tr><th>指標</th><th>追加</th><th>削除</th><th>変更</th><th>出典更新</th></tr></thead><tbody>${metricRows||'<tr><td colspan="5">差分なし</td></tr>'}</tbody></table></div></section><p class="privacy-note">物件名、物件ID、変更前後の数値、出典資料・ページ・シート・セルは画面用APIへ出していません。詳細はMac内のprivate-data/reports/latest-change-report.json、履歴はprivate-data/snapshotsで管理します。</p>`;
    button.onclick=()=>dialog.showModal();
  }catch{button.hidden=true}
}

function sourcePanel(p){
  const src=p.source;if(!src)return'<div class="source">デモデータ（架空）。実データとして利用しないでください。</div>';
  const entries=Object.entries(p.evidence||{}).map(([field,item])=>{const loc=item.locator||{};const position=[loc.page?`p.${loc.page}`:"",loc.sheet||"",loc.cell||loc.cell_range||""].filter(Boolean).join(" / ");return`<li><b>${esc(evidenceLabels[field]||field)}</b><br><code>${esc(position||"位置情報なし")}</code>・${esc(item.unit||"")}・${esc(item.review?.status||"未確認")}</li>`}).join("");
  const legacy=!entries?Object.entries(src.cells||{}).filter(([,v])=>v).map(([k,v])=>`<li><b>${esc(evidenceLabels[k]||k)}</b><br><code>${esc(v)}</code></li>`).join(""):"";
  const retrieved=src.retrieved_at?new Date(src.retrieved_at).toLocaleString("ja-JP"):"未記録";
  const url=safeUrl(src.url);
  return`<div class="source"><b>出典・Evidence</b><p>${esc(src.document||src.title)}・${esc(src.period)}</p><p>取得日時：${esc(retrieved)}<br>SHA-256：<code>${esc((src.sha256||"").slice(0,16))}${src.sha256?"…":"未記録"}</code></p>${url?`<a href="${esc(url)}" target="_blank" rel="noopener">公式IRライブラリを開く</a>`:""}<details><summary>数値ごとの抽出位置</summary><ul>${entries||legacy||"<li>位置情報なし</li>"}</ul></details></div>`;
}

async function loadData(){
  const supplementPromise=loadPdfSupplement();
  let payload;
  try{const res=await fetch("runtime-data/properties.json",{cache:"no-store"});if(!res.ok)throw new Error();payload=await res.json()}
  catch{payload=await (await fetch("data/demo-properties.json")).json()}
  properties=payload.properties.map(p=>({...p,periods:p.periods?.length?p.periods:[{period_no:null,period:"最新",as_of_date:null,cap:p.cap,noi:p.noi,occupancy:p.occupancy,appraisal:p.appraisal}]}));
  await supplementPromise;
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
  const inComparison=comparisonIds.has(p.id);
  document.querySelector("#detail").innerHTML=`<h2>${esc(p.name)}</h2><div class="address">${esc(p.address)}</div><div><span class="pill">${esc(p.type)}</span>${p.geocode?.quality==="automatic"?'<span class="pill neutral">座標：自動取得</span>':""}</div><button id="detailCompare" class="detail-compare-button${inComparison?" selected":""}">${inComparison?"比較対象から外す":"比較分析に追加"}</button><div class="metrics"><div class="metric"><span>取得価格</span><b>${yen(p.price)}</b></div><div class="metric"><span>鑑定評価額</span><b>${yen(p.appraisal)}</b></div><div class="metric"><span>直接還元利回り（CR）</span><b>${pct(p.cap)}</b></div><div class="metric"><span>稼働率</span><b>${pct(p.occupancy)}</b></div><div class="metric"><span>NOI（当期）</span><b>${yen(p.noi)}</b></div><div class="metric"><span>期末簿価</span><b>${yen(p.book_value)}</b></div><div class="metric"><span>賃貸可能面積</span><b>${area(p.leasable_area)}</b></div><div class="metric"><span>テナント数</span><b>${text(p.tenants)}</b></div></div>${pdfEventPanel(p)}<section class="analysis"><div class="analysis-heading"><div><span class="eyebrow">HISTORY</span><h3>物件データの推移</h3></div><select id="historyMetric" aria-label="推移指標">${metricOptions}</select></div><canvas id="historyChart" aria-label="物件データ推移グラフ"></canvas><div id="historySummary"></div></section><section class="analysis"><div class="analysis-heading"><div><span class="eyebrow">COMPARABLES</span><h3>類似物件 上位5件</h3></div></div><p class="method">距離35%、面積25%、取得価格15%、CR15%、稼働率10%で算出</p><div class="comparable-list">${comparableCards||'<p class="empty">比較できる物件がありません。</p>'}</div></section>${sourcePanel(p)}`;
  const selector=document.querySelector("#historyMetric");selector.onchange=()=>drawHistory(p,selector.value);drawHistory(p,selector.value);
  document.querySelector("#detailCompare").onclick=()=>toggleComparison(p.id);
  document.querySelectorAll(".comparable").forEach(button=>button.onclick=()=>selectProperty(properties.find(item=>item.id===button.dataset.propertyId)));
  document.querySelectorAll(".item").forEach(item=>item.classList.toggle("active",item.dataset.id===p.id));
  if(p.lat!=null&&p.lng!=null)map.flyTo([p.lat,p.lng],15);
}

function comparedProperties(){
  return properties.filter(property=>comparisonIds.has(property.id));
}

function toggleComparison(propertyId){
  if(comparisonIds.has(propertyId))comparisonIds.delete(propertyId);
  else if(comparisonIds.size>=comparisonLimit)window.alert(`比較できる物件は最大${comparisonLimit}件です。`);
  else comparisonIds.add(propertyId);
  updateComparisonButton();
  render();
  if(selected?.id===propertyId)selectProperty(selected);
  const dialog=document.querySelector("#comparisonDialog");
  if(dialog.open)renderComparisonAnalysis();
}

function updateComparisonButton(){
  const button=document.querySelector("#comparisonButton"),count=comparisonIds.size;
  button.textContent=`比較分析 ${count}件`;
  button.disabled=count<2;
}

function comparisonValue(metricKey,value){
  if(value==null)return"—";
  return metrics[metricKey].format(value);
}

function comparisonDelta(metricKey,value){
  if(value==null)return"—";
  const sign=value>0?"+":"";
  return metricKey==="noi"||metricKey==="appraisal"
    ?`${sign}${Number(value).toLocaleString("ja-JP",{maximumFractionDigits:1})}百万円`
    :`${sign}${Number(value).toFixed(1)}pt`;
}

function drawComparisonChart(selectedProperties,metricKey){
  const canvas=document.querySelector("#comparisonChart");if(!canvas)return;
  const timeline=PIPAnalysis.buildTimeline(selectedProperties);
  const propertySeries=selectedProperties.map(property=>PIPAnalysis.buildSeries(property,metricKey,timeline));
  const average=PIPAnalysis.averageSeries(propertySeries);
  const available=[...propertySeries.flat(),...average].filter(value=>value!=null);
  const width=Math.max(canvas.clientWidth,640),height=390,dpr=window.devicePixelRatio||1;
  canvas.width=width*dpr;canvas.height=height*dpr;
  const ctx=canvas.getContext("2d");ctx.scale(dpr,dpr);ctx.clearRect(0,0,width,height);
  const pad={left:68,right:22,top:20,bottom:58},plotW=width-pad.left-pad.right,plotH=height-pad.top-pad.bottom;
  if(!timeline.length||!available.length){ctx.fillStyle="#64748b";ctx.font="13px sans-serif";ctx.fillText("選択物件にこの指標の履歴はありません",pad.left,90);return}
  let min=Math.min(...available),max=Math.max(...available);
  if(metricKey==="occupancy"){max=Math.min(100,Math.max(max,100));min=Math.max(0,min-(max-min)*.12)}
  else if(min===max){const spread=Math.abs(min||1)*.08;min-=spread;max+=spread}
  else{const margin=(max-min)*.1;min-=margin;max+=margin}
  const xAt=index=>pad.left+(timeline.length===1?plotW/2:plotW*index/(timeline.length-1));
  const yAt=value=>pad.top+(max-value)/(max-min)*plotH;
  ctx.font="11px sans-serif";ctx.textBaseline="middle";ctx.textAlign="right";
  for(let index=0;index<5;index++){
    const y=pad.top+plotH*index/4,value=max-(max-min)*index/4;
    ctx.strokeStyle="#e2e8f0";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(pad.left,y);ctx.lineTo(width-pad.right,y);ctx.stroke();
    ctx.fillStyle="#64748b";
    const label=metricKey==="noi"||metricKey==="appraisal"?Math.round(value).toLocaleString("ja-JP"):value.toFixed(1);
    ctx.fillText(label,pad.left-9,y);
  }
  const drawSeries=(series,color,{dashed=false,width:lineWidth=2.3}={})=>{
    ctx.save();ctx.strokeStyle=color;ctx.lineWidth=lineWidth;ctx.lineJoin="round";ctx.setLineDash(dashed?[7,5]:[]);
    ctx.beginPath();let active=false;
    series.forEach((value,index)=>{if(value==null){active=false;return}const x=xAt(index),y=yAt(value);if(!active){ctx.moveTo(x,y);active=true}else ctx.lineTo(x,y)});
    ctx.stroke();ctx.restore();
    if(!dashed)series.forEach((value,index)=>{if(value==null)return;ctx.fillStyle="#fff";ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();ctx.arc(xAt(index),yAt(value),3,0,Math.PI*2);ctx.fill();ctx.stroke()});
  };
  propertySeries.forEach((series,index)=>drawSeries(series,comparisonColors[index%comparisonColors.length]));
  drawSeries(average,"#0f172a",{dashed:true,width:2.8});
  const step=Math.max(1,Math.ceil(timeline.length/8));ctx.textAlign="right";ctx.textBaseline="top";ctx.fillStyle="#64748b";ctx.font="10px sans-serif";
  timeline.forEach((point,index)=>{if(index%step!==0&&index!==timeline.length-1)return;ctx.save();ctx.translate(xAt(index),height-pad.bottom+10);ctx.rotate(-Math.PI/4);ctx.fillText(point.label,0,0);ctx.restore()});
  ctx.save();ctx.translate(16,pad.top+plotH/2);ctx.rotate(-Math.PI/2);ctx.textAlign="center";ctx.textBaseline="top";ctx.fillStyle="#475569";ctx.font="11px sans-serif";ctx.fillText(metrics[metricKey].label,0,0);ctx.restore();
}

function renderComparisonAnalysis(){
  const selectedProperties=comparedProperties(),content=document.querySelector("#comparisonContent");
  if(selectedProperties.length<2){content.innerHTML='<p class="empty">比較する物件を2件以上選択してください。</p>';return}
  const metric=metrics[comparisonMetric];
  const tabs=Object.entries(metrics).map(([key,item])=>`<button class="comparison-tab${key===comparisonMetric?" active":""}" data-comparison-metric="${key}">${esc(item.short)}</button>`).join("");
  const legend=selectedProperties.map((property,index)=>`<span><i class="comparison-swatch" style="background:${comparisonColors[index%comparisonColors.length]}"></i>${esc(property.name)}</span>`).join("");
  const rows=selectedProperties.map((property,index)=>{
    const summary=PIPAnalysis.summary(property,comparisonMetric);
    return`<tr><td><div class="comparison-property"><i class="comparison-swatch" style="background:${comparisonColors[index%comparisonColors.length]}"></i><b>${esc(property.name)}</b><button data-remove-comparison="${esc(property.id)}" aria-label="${esc(property.name)}を比較から外す">×</button></div><small>${esc(property.reit)}</small></td><td>${comparisonValue(comparisonMetric,summary.first)}</td><td><b>${comparisonValue(comparisonMetric,summary.latest)}</b></td><td>${comparisonDelta(comparisonMetric,summary.change)}</td><td>${summary.count}期</td></tr>`;
  }).join("");
  content.innerHTML=`<div class="comparison-intro"><p>選択した物件を同じ時間軸で比較します。黒い破線は、各時点で値が開示されている選択物件の平均です。</p><span class="comparison-count">${selectedProperties.length} / ${comparisonLimit}物件</span></div><div class="comparison-tabs" role="tablist" aria-label="比較指標">${tabs}</div><div class="comparison-future"><span>専有坪単価：データ契約準備中</span><span>貸室賃料収入単価：定義統一後に追加</span></div><div class="comparison-chart-card"><div class="comparison-legend">${legend}<span><i class="comparison-swatch average"></i>平均値</span></div><canvas id="comparisonChart" aria-label="${esc(metric.label)}の複数物件比較グラフ"></canvas></div><section class="comparison-table"><h3>${esc(metric.label)} サマリー</h3><div class="table-scroll"><table><thead><tr><th>物件</th><th>開始値</th><th>最新値</th><th>期間変化</th><th>開示時点</th></tr></thead><tbody>${rows}</tbody></table></div></section><p class="privacy-note">比較値は各物件のEvidence付き時系列を使用します。平均は欠損値を除外して算出し、未開示値の補間は行いません。</p>`;
  document.querySelectorAll("[data-comparison-metric]").forEach(button=>button.onclick=()=>{comparisonMetric=button.dataset.comparisonMetric;renderComparisonAnalysis()});
  document.querySelectorAll("[data-remove-comparison]").forEach(button=>button.onclick=()=>toggleComparison(button.dataset.removeComparison));
  requestAnimationFrame(()=>drawComparisonChart(selectedProperties,comparisonMetric));
}

function openComparisonAnalysis(){
  if(comparisonIds.size<2)return;
  renderComparisonAnalysis();
  document.querySelector("#comparisonDialog").showModal();
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
  document.querySelector("#list").innerHTML=visible.map(p=>`<div class="item${selected?.id===p.id?" active":""}" data-id="${esc(p.id)}"><b>${esc(p.name)}</b><small>${esc(p.address)}</small><br><span class="pill">${esc(p.region||p.type)}・CR ${pct(p.cap)}</span><button class="compare-toggle${comparisonIds.has(p.id)?" selected":""}" data-compare-id="${esc(p.id)}" aria-pressed="${comparisonIds.has(p.id)}">${comparisonIds.has(p.id)?"✓ 比較":"＋ 比較"}</button></div>`).join("");
  markers.clearLayers();visible.filter(p=>p.lat!=null&&p.lng!=null).forEach(p=>L.marker([p.lat,p.lng]).addTo(markers).bindTooltip(esc(p.name)).on("click",()=>selectProperty(p)));
  document.querySelectorAll(".item").forEach(el=>el.onclick=()=>selectProperty(properties.find(p=>p.id===el.dataset.id)));
  document.querySelectorAll("[data-compare-id]").forEach(button=>button.onclick=event=>{event.stopPropagation();toggleComparison(button.dataset.compareId)});
}
document.querySelector("#search").oninput=render;reitFilter.onchange=render;typeFilter.onchange=render;region.onchange=render;
document.querySelector("#comparisonButton").onclick=openComparisonAnalysis;
document.querySelector("#clearComparison").onclick=()=>{comparisonIds.clear();updateComparisonButton();render();if(selected)selectProperty(selected);document.querySelector("#comparisonDialog").close()};
document.querySelector("#export").onclick=()=>{if(!visible.length)return;const keys=["id","reit_code","reit","name","type","region","address","lat","lng","price","book_value","appraisal","cap","discount_rate","terminal_cap_rate","occupancy","noi","leasable_area","leased_area","tenants"];const csv=[keys.join(","),...visible.map(p=>keys.map(k=>`"${String(p[k]??"").replaceAll('"','""')}"`).join(","))].join("\n");const a=document.createElement("a");a.href=URL.createObjectURL(new Blob(["\ufeff"+csv],{type:"text/csv"}));a.download="jreit-properties.csv";a.click();URL.revokeObjectURL(a.href)};
window.addEventListener("resize",()=>{if(selected){const metric=document.querySelector("#historyMetric");if(metric)drawHistory(selected,metric.value)}if(document.querySelector("#comparisonDialog").open)drawComparisonChart(comparedProperties(),comparisonMetric)});
loadData().catch(err=>{document.querySelector("#dataset").textContent="読込エラー";document.querySelector("#detail").innerHTML=`<p class="error">データを読み込めませんでした。${esc(err.message)}</p>`});
loadImportStatus();
loadQualityStatus();
loadChangeStatus();
