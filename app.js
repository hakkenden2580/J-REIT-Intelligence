let properties=[];let visible=[];let selected=null;let pdfCatalog=null;let comparisonMetric="cap";let comparisonSeriesMode="auto";let workspaceView="map";let mapBoundsFilter=null;let radiusFilter=null;let radiusCircle=null;let radiusHandle=null;let radiusPickMode=false;let boxSelectionMode=false;let boxStart=null;let selectionBox=null;
const comparisonIds=new Set(),comparisonLimit=50;
const individualSeriesLimit=8;
const comparisonStorageKey="pip-comparison-ids-v0.14",workspaceViewStorageKey="pip-workspace-view-v0.14";
const comparisonColors=["#2563eb","#db2777","#059669","#d97706","#7c3aed","#0891b2","#dc2626","#4f46e5","#65a30d","#ea580c","#9333ea","#0f766e","#be123c","#0369a1","#a16207","#15803d","#c026d3","#4338ca","#b91c1c","#047857"];
const comparisonColor=index=>index<comparisonColors.length?comparisonColors[index]:`hsl(${Math.round((index*137.508)%360)} 72% ${42+(index%3)*8}%)`;
const map=L.map("map").setView([35.55,139.55],7);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"&copy; OpenStreetMap contributors"}).addTo(map);
const markers=L.layerGroup().addTo(map);
const yen=n=>n==null?"—":`${Number(n).toLocaleString("ja-JP",{maximumFractionDigits:1})}百万円`;
const pct=n=>n==null?"—":`${Number(n).toFixed(1)}%`;
const area=n=>n==null?"—":`${Number(n).toLocaleString("ja-JP")}㎡`;
const text=n=>n==null?"—":Number(n).toLocaleString("ja-JP");
const radiusText=n=>Number(n).toLocaleString("ja-JP",{maximumFractionDigits:1});
const esc=s=>String(s??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const safeUrl=value=>{try{const url=new URL(String(value||""));return ["https:","http:"].includes(url.protocol)?url.href:""}catch{return""}};
const reitFilter=document.querySelector("#reit"),typeFilter=document.querySelector("#type"),region=document.querySelector("#region");
const numericFilterIds=["capMin","capMax","occupancyMin","occupancyMax","priceMin","priceMax","areaMin","areaMax"];
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

function renderCapLegend(){
  document.querySelector("#capLegend").innerHTML=`<b>鑑定CR（%）</b>${PIPMapAnalysis.bands.map(band=>`<span><i style="background:${band.unknown?"repeating-linear-gradient(135deg,#94a3b8 0 3px,#cbd5e1 3px 6px)":band.color}"></i>${esc(band.label)}</span>`).join("")}`;
}

function currentMapBounds(){
  const bounds=map.getBounds();
  return{south:bounds.getSouth(),north:bounds.getNorth(),west:bounds.getWest(),east:bounds.getEast()};
}

function updateMapAnalysisControls(message=""){
  const filterButton=document.querySelector("#filterMapBounds"),clearButton=document.querySelector("#clearMapBounds"),radiusButton=document.querySelector("#toggleRadiusSearch"),boxButton=document.querySelector("#toggleBoxSelection"),clearBoxButton=document.querySelector("#clearBoxSelection"),selectButton=document.querySelector("#selectVisible"),status=document.querySelector("#mapActionStatus");
  filterButton.classList.toggle("active",Boolean(mapBoundsFilter));
  filterButton.textContent=mapBoundsFilter?"この地図範囲で更新":"この地図範囲で検索";
  clearButton.hidden=!mapBoundsFilter;
  radiusButton.classList.toggle("active",Boolean(radiusFilter));
  boxButton.classList.toggle("active",boxSelectionMode);
  boxButton.setAttribute("aria-pressed",String(boxSelectionMode));
  boxButton.textContent=boxSelectionMode?"地図をドラッグ":"範囲をドラッグ選択";
  clearBoxButton.hidden=!selectionBox;
  selectButton.disabled=!visible.length||comparisonIds.size>=comparisonLimit;
  const activeFilters=[mapBoundsFilter?"地図範囲":"",radiusFilter?`半径${radiusText(radiusFilter.radiusKm)}km`:""].filter(Boolean);
  status.textContent=message||(activeFilters.length?`${activeFilters.join("＋")}・${visible.length.toLocaleString("ja-JP")}件`:(map.getZoom()>=9?"鑑定CRを数値表示":"拡大すると鑑定CRを数値表示"));
  updateRadiusControls();
}

function renderMapMarkers(){
  markers.clearLayers();
  const compact=map.getZoom()<9;
  visible.filter(property=>property.lat!=null&&property.lng!=null).forEach(property=>{
    const band=PIPMapAnalysis.bandFor(property.cap),unknown=Boolean(band.unknown),active=selected?.id===property.id;
    const markerClass=["cap-marker",compact?"compact":"",unknown?"unknown":"",active?"selected":""].filter(Boolean).join(" ");
    const label=unknown?"—":Number(property.cap).toFixed(1);
    const icon=L.divIcon({className:"cap-marker-shell",html:`<span class="${markerClass}" style="--cap-color:${band.color}">${compact?"":label}</span>`,iconSize:compact?[35,25]:[48,32],iconAnchor:[24,28]});
    L.marker([property.lat,property.lng],{icon}).addTo(markers).bindTooltip(`${esc(property.name)}・CR ${pct(property.cap)}`).on("click",()=>selectProperty(property));
  });
}

function applyMapBoundsFilter(){
  mapBoundsFilter=currentMapBounds();
  render();
  updateMapAnalysisControls(`現在の地図範囲で ${visible.length.toLocaleString("ja-JP")}件`);
}

function clearMapBoundsFilter(){
  mapBoundsFilter=null;
  render();
}

function selectVisibleForComparison(){
  const before=comparisonIds.size,selectedIds=PIPMapAnalysis.selectIds(visible,comparisonIds,comparisonLimit);
  comparisonIds.clear();selectedIds.forEach(id=>comparisonIds.add(id));
  persistComparison();render();
  const added=comparisonIds.size-before,remaining=Math.max(0,visible.filter(property=>!comparisonIds.has(property.id)).length);
  updateMapAnalysisControls(`${added}件を比較へ追加${remaining?`・上限${comparisonLimit}件`:""}`);
}

function updateRadiusControls(){
  const panel=document.querySelector("#radiusPanel"),button=document.querySelector("#toggleRadiusSearch"),clearButton=document.querySelector("#clearRadius"),status=document.querySelector("#radiusStatus");
  button.setAttribute("aria-expanded",String(!panel.hidden));
  clearButton.hidden=!radiusFilter;
  if(radiusPickMode)status.textContent="地図上で検索の中心をクリックしてください。";
  else if(radiusFilter)status.textContent=`${radiusFilter.label}・半径${radiusText(radiusFilter.radiusKm)}km・${visible.length.toLocaleString("ja-JP")}件`;
  else status.textContent="中心位置を指定してください。検索後は円周のハンドルもドラッグできます。";
  syncRadiusInput();
  document.querySelector("#mapView").classList.toggle("radius-picking",radiusPickMode);
  document.querySelector("#mapView").classList.toggle("box-selecting",boxSelectionMode);
}

function syncRadiusInput(){
  const input=document.querySelector("#radiusKm"),output=document.querySelector("#radiusValue");
  const value=radiusFilter?.radiusKm??PIPSpatialAnalysis.normalizeRadiusKm(input.value);
  input.value=value;output.value=`${radiusText(value)} km`;output.textContent=output.value;
}

function renderRadiusOverlay(){
  if(radiusCircle){map.removeLayer(radiusCircle);radiusCircle=null}
  if(radiusHandle){map.removeLayer(radiusHandle);radiusHandle=null}
  if(!radiusFilter)return;
  radiusCircle=L.circle([radiusFilter.lat,radiusFilter.lng],{radius:radiusFilter.radiusKm*1000,color:"#2563eb",weight:2,fillColor:"#60a5fa",fillOpacity:.2,className:"radius-circle"}).addTo(map);
  const handlePoint=PIPSpatialAnalysis.destinationPoint(radiusFilter,radiusFilter.radiusKm);
  const icon=L.divIcon({className:"radius-resize-handle-shell",html:'<span class="radius-resize-handle"></span>',iconSize:[24,24],iconAnchor:[12,12]});
  radiusHandle=L.marker([handlePoint.lat,handlePoint.lng],{icon,draggable:true,zIndexOffset:1000}).addTo(map).bindTooltip("ドラッグして半径を調整",{direction:"top"});
  radiusHandle.on("drag",event=>{
    const radiusKm=PIPSpatialAnalysis.normalizeRadiusKm(PIPSpatialAnalysis.haversineKm(radiusFilter,event.target.getLatLng()));
    radiusFilter={...radiusFilter,radiusKm};radiusCircle.setRadius(radiusKm*1000);syncRadiusInput();
    document.querySelector("#radiusStatus").textContent=`半径${radiusText(radiusKm)}kmに調整中`;
  });
  radiusHandle.on("dragend",()=>{
    renderRadiusOverlay();render();
    updateMapAnalysisControls(`半径${radiusText(radiusFilter.radiusKm)}km・${visible.length.toLocaleString("ja-JP")}件`);
  });
}

function applyRadiusFilter(center,label="指定地点"){
  const point=PIPSpatialAnalysis.coordinates(center);
  if(!point)return;
  radiusFilter={...point,radiusKm:PIPSpatialAnalysis.normalizeRadiusKm(document.querySelector("#radiusKm").value),label};
  radiusPickMode=false;
  renderRadiusOverlay();
  render();
  updateMapAnalysisControls(`${label}から半径${radiusText(radiusFilter.radiusKm)}km・${visible.length.toLocaleString("ja-JP")}件`);
}

function beginRadiusPick(){
  if(boxSelectionMode)setBoxSelectionMode(false);
  radiusPickMode=true;
  updateRadiusControls();
}

function clearRadiusFilter(){
  radiusFilter=null;radiusPickMode=false;renderRadiusOverlay();render();
}

function toggleRadiusPanel(force){
  const panel=document.querySelector("#radiusPanel");
  panel.hidden=typeof force==="boolean"?!force:!panel.hidden;
  if(panel.hidden)radiusPickMode=false;
  updateRadiusControls();
}

function clearSelectionBox(){
  if(selectionBox){map.removeLayer(selectionBox);selectionBox=null}
  boxStart=null;updateMapAnalysisControls();
}

function setBoxSelectionMode(enabled){
  boxSelectionMode=Boolean(enabled);boxStart=null;
  if(boxSelectionMode){
    toggleRadiusPanel(false);radiusPickMode=false;clearSelectionBox();map.dragging.disable();
  }else map.dragging.enable();
  updateMapAnalysisControls();
}

function finishBoxSelection(bounds){
  const box={south:bounds.getSouth(),north:bounds.getNorth(),west:bounds.getWest(),east:bounds.getEast()};
  const candidates=visible.filter(property=>PIPMapAnalysis.boundsContain(property,box));
  const before=comparisonIds.size,selectedIds=PIPMapAnalysis.selectIds(candidates,comparisonIds,comparisonLimit);
  comparisonIds.clear();selectedIds.forEach(id=>comparisonIds.add(id));
  const added=comparisonIds.size-before,truncated=Math.max(0,candidates.length-added);
  persistComparison();setBoxSelectionMode(false);render();
  updateMapAnalysisControls(`範囲内${candidates.length.toLocaleString("ja-JP")}件・${added}件を比較へ追加${truncated?`・上限${comparisonLimit}件`:""}`);
}

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

function persistComparison(){
  try{localStorage.setItem(comparisonStorageKey,JSON.stringify([...comparisonIds]))}catch{}
}

function restoreWorkspaceState(){
  try{
    const saved=JSON.parse(localStorage.getItem(comparisonStorageKey)||"[]");
    saved.filter(id=>properties.some(property=>property.id===id)).slice(0,comparisonLimit).forEach(id=>comparisonIds.add(id));
    const savedView=localStorage.getItem(workspaceViewStorageKey);
    if(["map","table","analysis"].includes(savedView))workspaceView=savedView;
  }catch{}
}

async function loadData(){
  const supplementPromise=loadPdfSupplement();
  let payload;
  try{const res=await fetch("runtime-data/properties.json",{cache:"no-store"});if(!res.ok)throw new Error();payload=await res.json()}
  catch{payload=await (await fetch("data/demo-properties.json")).json()}
  properties=payload.properties.map(p=>({...p,periods:p.periods?.length?p.periods:[{period_no:null,period:"最新",as_of_date:null,cap:p.cap,noi:p.noi,occupancy:p.occupancy,appraisal:p.appraisal}]}));
  await supplementPromise;
  restoreWorkspaceState();
  visible=[...properties];
  document.querySelector("#dataset").textContent=payload.meta.label;
  document.querySelector("#dataset").classList.toggle("demo",payload.meta.dataset==="demo");
  [...new Set(properties.map(x=>x.reit).filter(Boolean))].sort().forEach(x=>reitFilter.add(new Option(x,x)));
  [...new Set(properties.map(x=>x.type).filter(Boolean))].sort().forEach(x=>typeFilter.add(new Option(x,x)));
  [...new Set(properties.map(x=>x.region).filter(Boolean))].sort().forEach(x=>region.add(new Option(x,x)));
  render();updateComparisonButton();setWorkspaceView(workspaceView,{persist:false});
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
  if(!p)return;
  selected=p;
  const latestPeriod=[...(p.periods||[])].sort((a,b)=>(a.as_of_date||String(a.period_no||"")).localeCompare(b.as_of_date||String(b.period_no||""))).at(-1)||{};
  const periodLabel=latestPeriod.period||p.period||(latestPeriod.as_of_date?String(latestPeriod.as_of_date).slice(0,10):"最新");
  const geocodeQuality={verified:"確認済み",manual:"手動確認",automatic:"自動取得",unknown:"未確認"}[p.geocode?.quality]||p.geocode?.quality||"未記録";
  const evidenceCount=Object.keys(latestPeriod.evidence||p.evidence||{}).length;
  const defaultMetric=Object.keys(metrics).find(key=>p.periods.some(period=>period[key]!=null))||"appraisal";
  const metricOptions=Object.entries(metrics).map(([key,item])=>`<option value="${key}"${key===defaultMetric?" selected":""}>${item.label}</option>`).join("");
  const comparableCards=comparablesFor(p).map(item=>`<button class="comparable" data-property-id="${esc(item.property.id)}"><span class="score">類似度 ${item.score}</span><b>${esc(item.property.name)}</b><small>${item.distance==null?"距離不明":`${item.distance.toFixed(1)}km`}・CR ${pct(item.property.cap)}・${area(item.property.leasable_area)}</small></button>`).join("");
  const inComparison=comparisonIds.has(p.id);
  document.querySelector("#detail").innerHTML=`<section class="property-detail-hero"><div><span class="eyebrow">PROPERTY DETAIL</span><h2>${esc(p.name)}</h2><div class="address">${esc(p.address)}</div><div class="property-badges"><span class="pill">${esc(p.type)}</span><span class="pill neutral">${esc(p.reit)}</span><span class="pill neutral">座標：${esc(geocodeQuality)}</span></div></div><div class="detail-period"><span>最新開示</span><b>${esc(periodLabel)}</b></div></section><div class="detail-actions"><button id="detailCompare" class="detail-compare-button${inComparison?" selected":""}">${inComparison?"比較対象から外す":"比較分析に追加"}</button>${p.lat!=null&&p.lng!=null?'<button id="detailRadiusSearch" class="detail-spatial-button">この物件を中心に半径検索</button>':""}</div><section class="detail-section"><div class="detail-section-heading"><div><span class="eyebrow">KEY METRICS</span><h3>最新指標</h3></div><span class="evidence-count">Evidence ${evidenceCount}項目</span></div><div class="metrics"><div class="metric primary"><span>直接還元利回り（CR）</span><b>${pct(p.cap)}</b></div><div class="metric primary"><span>鑑定評価額</span><b>${yen(p.appraisal)}</b></div><div class="metric"><span>稼働率</span><b>${pct(p.occupancy)}</b></div><div class="metric"><span>NOI（当期）</span><b>${yen(p.noi)}</b></div><div class="metric"><span>取得価格</span><b>${yen(p.price)}</b></div><div class="metric"><span>期末簿価</span><b>${yen(p.book_value)}</b></div></div></section><section class="detail-section"><div class="detail-section-heading"><div><span class="eyebrow">OVERVIEW</span><h3>物件概要</h3></div></div><dl class="property-overview"><div><dt>投資法人</dt><dd>${esc(p.reit)}</dd></div><div><dt>証券コード</dt><dd>${esc(p.reit_code||"—")}</dd></div><div><dt>アセットタイプ</dt><dd>${esc(p.type||"—")}</dd></div><div><dt>地域</dt><dd>${esc(p.region||"—")}</dd></div><div><dt>賃貸可能面積</dt><dd>${area(p.leasable_area)}</dd></div><div><dt>賃貸面積</dt><dd>${area(p.leased_area)}</dd></div><div><dt>テナント数</dt><dd>${text(p.tenants)}</dd></div><div><dt>割引率</dt><dd>${pct(p.discount_rate)}</dd></div><div><dt>最終還元利回り</dt><dd>${pct(p.terminal_cap_rate)}</dd></div><div><dt>座標</dt><dd>${p.lat==null||p.lng==null?"—":`${Number(p.lat).toFixed(5)}, ${Number(p.lng).toFixed(5)}`}</dd></div></dl></section>${pdfEventPanel(p)}<section class="analysis history-card"><div class="analysis-heading"><div><span class="eyebrow">HISTORY</span><h3>物件データの推移</h3></div><select id="historyMetric" aria-label="推移指標">${metricOptions}</select></div><div class="history-chart-stage"><canvas id="historyChart" class="history-chart-base" aria-label="物件データ推移グラフ"></canvas><canvas class="history-chart-overlay" aria-hidden="true"></canvas><div id="historyTooltip" class="history-chart-tooltip" hidden></div></div><p class="chart-help">グラフをなぞると、開示時点と正確な値を確認できます。点線区間は未開示期間で、値は推定していません。</p><div id="historySummary"></div></section><section class="analysis"><div class="analysis-heading"><div><span class="eyebrow">COMPARABLES</span><h3>類似物件 上位5件</h3></div></div><p class="method">距離35%、面積25%、取得価格15%、CR15%、稼働率10%で算出</p><div class="comparable-list">${comparableCards||'<p class="empty">比較できる物件がありません。</p>'}</div></section>${sourcePanel(p)}`;
  const selector=document.querySelector("#historyMetric");selector.onchange=()=>drawHistory(p,selector.value);drawHistory(p,selector.value);
  document.querySelector("#detailCompare").onclick=()=>toggleComparison(p.id);
  const radiusButton=document.querySelector("#detailRadiusSearch");if(radiusButton)radiusButton.onclick=()=>{toggleRadiusPanel(true);applyRadiusFilter(p,`${p.name}中心`)};
  document.querySelectorAll(".comparable").forEach(button=>button.onclick=()=>selectProperty(properties.find(item=>item.id===button.dataset.propertyId)));
  document.querySelectorAll(".item").forEach(item=>item.classList.toggle("active",item.dataset.id===p.id));
  renderMapMarkers();
  if(p.lat!=null&&p.lng!=null)map.flyTo([p.lat,p.lng],15);
}

function comparedProperties(){
  return properties.filter(property=>comparisonIds.has(property.id));
}

function toggleComparison(propertyId){
  if(comparisonIds.has(propertyId))comparisonIds.delete(propertyId);
  else if(comparisonIds.size>=comparisonLimit)window.alert(`比較できる物件は最大${comparisonLimit}件です。`);
  else comparisonIds.add(propertyId);
  persistComparison();
  updateComparisonButton();
  render();
  if(selected?.id===propertyId)selectProperty(selected);
  const dialog=document.querySelector("#comparisonDialog");
  if(dialog.open)renderComparisonAnalysis();
  if(workspaceView==="analysis")renderWorkspaceAnalysis();
}

function updateComparisonButton(){
  const button=document.querySelector("#comparisonButton"),count=comparisonIds.size;
  button.textContent=`比較分析 ${count}件`;
  button.disabled=count<2;
  const panel=document.querySelector("#selectionPanel"),analysisButton=document.querySelector("#openSelectedAnalysis");
  document.querySelector("#selectionCount").textContent=count;
  panel.hidden=count===0;
  analysisButton.disabled=count<2;
  document.querySelector("#exportSelected").disabled=count===0;
  document.querySelector("#selectionChips").innerHTML=comparedProperties().map(property=>`<span class="selection-chip">${esc(property.name)}<button type="button" data-selection-remove="${esc(property.id)}" aria-label="${esc(property.name)}を選択解除">×</button></span>`).join("");
  document.querySelectorAll("[data-selection-remove]").forEach(remove=>remove.onclick=()=>toggleComparison(remove.dataset.selectionRemove));
  document.querySelector("#workspaceSummary").textContent=`${visible.length.toLocaleString("ja-JP")}物件を表示・${count}件を選択`;
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

function latestDistributionSnapshot(distribution,timeline,totalProperties){
  for(let index=timeline.length-1;index>=0;index--){
    if(distribution.median[index]==null)continue;
    const count=distribution.counts[index]||0;
    return{
      period:timeline[index]?.label||timeline[index]?.key||"—",
      average:distribution.average[index],
      median:distribution.median[index],
      q1:distribution.q1[index],
      q3:distribution.q3[index],
      count,
      coveragePercent:totalProperties?Math.round(count/totalProperties*100):0,
    };
  }
  return null;
}

function bindStableChartResize(stage,render){
  stage._pipChartRender=render;
  if(typeof ResizeObserver==="undefined"||stage._pipResizeObserver)return;
  let lastWidth=Math.round(stage.getBoundingClientRect().width);
  let frame=null;
  stage._pipResizeObserver=new ResizeObserver(entries=>{
    const width=Math.round(entries[0]?.contentRect?.width||0);
    if(!width||Math.abs(width-lastWidth)<2)return;
    lastWidth=width;
    if(frame)cancelAnimationFrame(frame);
    frame=requestAnimationFrame(()=>stage._pipChartRender?.());
  });
  stage._pipResizeObserver.observe(stage);
}

function drawComparisonHover(canvas,overlay,index){
  const model=canvas._pipChartModel;if(!model)return;
  const ctx=overlay.getContext("2d");
  ctx.clearRect(0,0,model.width,model.height);
  if(index==null||!model.timeline[index])return;
  const x=model.xAt(index);
  ctx.save();
  ctx.strokeStyle="#64748b";ctx.lineWidth=1;ctx.setLineDash([4,4]);
  ctx.beginPath();ctx.moveTo(x,model.pad.top);ctx.lineTo(x,model.pad.top+model.plotH);ctx.stroke();
  ctx.restore();
  const highlight=(value,color,radius=5)=>{
    if(value==null)return;
    ctx.fillStyle="#fff";ctx.strokeStyle=color;ctx.lineWidth=3;
    ctx.beginPath();ctx.arc(x,model.yAt(value),radius,0,Math.PI*2);ctx.fill();ctx.stroke();
  };
  model.renderedSeries.forEach((series,seriesIndex)=>highlight(series[index],comparisonColor(seriesIndex),4));
  highlight(model.median[index],"#172554",4.8);
  highlight(model.average[index],"#2457e6",5.5);
}

function bindComparisonInteraction(canvas,overlay){
  if(overlay.dataset.chartInteractionBound)return;
  overlay.dataset.chartInteractionBound="true";
  const inspect=event=>{
    const model=canvas._pipChartModel;if(!model?.timeline.length)return;
    const rect=overlay.getBoundingClientRect();
    const pointerX=(event.clientX-rect.left)*(model.width/Math.max(rect.width,1));
    const index=PIPAnalysis.nearestTimelineIndex(pointerX,model.pad.left,model.plotW,model.timeline.length);
    drawComparisonHover(canvas,overlay,index);
    showComparisonTooltip(canvas,index,event.clientX-rect.left,event.clientY-rect.top);
  };
  overlay.addEventListener("pointerdown",inspect);
  overlay.addEventListener("pointermove",inspect);
  overlay.addEventListener("pointerleave",()=>{
    hideComparisonTooltip(canvas);
    drawComparisonHover(canvas,overlay,null);
  });
}

function drawComparisonChart(selectedProperties,metricKey,canvasId="comparisonChart"){
  const canvas=document.querySelector(`#${canvasId}`);if(!canvas)return;
  const stage=canvas.parentElement,overlay=stage.querySelector(".comparison-chart-overlay");if(!overlay)return;
  const resolvedMode=PIPAnalysis.resolveSeriesMode(comparisonSeriesMode,selectedProperties.length,individualSeriesLimit);
  const timeline=PIPAnalysis.buildComparisonTimeline(selectedProperties);
  const propertySeries=selectedProperties.map(property=>PIPAnalysis.buildComparisonSeries(property,metricKey,timeline));
  const aggregate=PIPAnalysis.distributionSeries(propertySeries);
  const average=aggregate.average,median=aggregate.median,q1=aggregate.q1,q3=aggregate.q3;
  const sampleCounts=aggregate.counts,minimumSampleCount=aggregate.minimumCount;
  const renderedSeries=resolvedMode==="individual"?propertySeries:[];
  const available=[...renderedSeries.flat(),...q1,...q3,...average,...median].filter(value=>value!=null);
  const preferredHeight=window.innerWidth<700?300:canvasId==="workspaceComparisonChart"?470:430;
  const {width,height}=PIPChart.stageSize(stage,preferredHeight,window.innerWidth-24);
  const ctx=PIPChart.prepareCanvas(canvas,width,height,window.devicePixelRatio);
  PIPChart.prepareCanvas(overlay,width,height,window.devicePixelRatio);
  const pad={left:70,right:24,top:24,bottom:62},plotW=width-pad.left-pad.right,plotH=height-pad.top-pad.bottom;
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
  if(selectedProperties.length>=3){
    PIPChart.drawRangeBand(ctx,q1,q3,xAt,yAt,{
      fill:"#dbeafe",stroke:"#93c5fd",opacity:.62,
    });
  }
  renderedSeries.forEach((series,index)=>PIPChart.drawSegmentedSeries(ctx,series,xAt,yAt,{
    color:comparisonColor(index),width:2,points:true,pointRadius:2.8,opacity:.76,
  }));
  PIPChart.drawSegmentedSeries(ctx,median,xAt,yAt,{
    color:"#172554",gapColor:"#172554",width:2.4,points:false,opacity:.9,
  });
  PIPChart.drawSegmentedSeries(ctx,average,xAt,yAt,{
    color:"#2457e6",gapColor:"#2457e6",width:3.4,points:true,pointRadius:3.7,
  });
  const step=Math.max(1,Math.ceil(timeline.length/8));ctx.textAlign="right";ctx.textBaseline="top";ctx.fillStyle="#64748b";ctx.font="10px sans-serif";
  timeline.forEach((point,index)=>{if(index%step!==0&&index!==timeline.length-1)return;ctx.save();ctx.translate(xAt(index),height-pad.bottom+10);ctx.rotate(-Math.PI/4);ctx.fillText(point.label,0,0);ctx.restore()});
  ctx.save();ctx.translate(16,pad.top+plotH/2);ctx.rotate(-Math.PI/2);ctx.textAlign="center";ctx.textBaseline="top";ctx.fillStyle="#475569";ctx.font="11px sans-serif";ctx.fillText(metrics[metricKey].label,0,0);ctx.restore();
  canvas._pipChartModel={selectedProperties,metricKey,timeline,propertySeries,renderedSeries,average,median,q1,q3,sampleCounts,minimumSampleCount,resolvedMode,pad,plotW,plotH,width,height,xAt,yAt};
  bindComparisonInteraction(canvas,overlay);
  bindStableChartResize(stage,()=>drawComparisonChart(selectedProperties,metricKey,canvasId));
}

function showComparisonTooltip(canvas,index,pointerX,pointerY){
  const model=canvas._pipChartModel,tooltip=canvas.parentElement.querySelector(".comparison-chart-tooltip");
  if(!model||!tooltip||index==null)return;
  const average=model.average[index],date=model.timeline[index]?.label||model.timeline[index]?.key;
  const median=model.median[index],q1=model.q1[index],q3=model.q3[index];
  const sampleCount=model.sampleCounts[index]||0;
  const coveragePercent=model.selectedProperties.length
    ?Math.round(sampleCount/model.selectedProperties.length*100)
    :0;
  const averageLabel=average==null&&sampleCount<model.minimumSampleCount?"母数不足":"平均値";
  const lines=model.resolvedMode==="individual"
    ?model.selectedProperties.map((property,propertyIndex)=>({name:property.name,value:model.propertySeries[propertyIndex][index],color:comparisonColor(propertyIndex)})).filter(item=>item.value!=null)
    :[];
  tooltip.innerHTML=`<b>${esc(date)}</b><div class="tooltip-average"><i></i><span>${averageLabel}</span><strong>${comparisonValue(model.metricKey,average)}</strong><small>${sampleCount} / ${model.selectedProperties.length}物件（${coveragePercent}%）</small></div><div class="tooltip-median"><i></i><span>中央値</span><strong>${comparisonValue(model.metricKey,median)}</strong></div><div class="tooltip-band"><i></i><span>中央50%（Q1–Q3）</span><strong>${q1==null||q3==null?"—":`${comparisonValue(model.metricKey,q1)} – ${comparisonValue(model.metricKey,q3)}`}</strong></div>${lines.map(item=>`<div><i style="background:${item.color}"></i><span>${esc(item.name)}</span><strong>${comparisonValue(model.metricKey,item.value)}</strong></div>`).join("")}`;
  tooltip.hidden=false;
  const stage=canvas.parentElement,maxLeft=Math.max(8,stage.clientWidth-tooltip.offsetWidth-8),maxTop=Math.max(8,stage.clientHeight-tooltip.offsetHeight-8);
  tooltip.style.left=`${Math.max(8,Math.min(maxLeft,pointerX+14))}px`;
  tooltip.style.top=`${Math.max(8,Math.min(maxTop,pointerY-tooltip.offsetHeight/2))}px`;
}

function hideComparisonTooltip(canvas){
  const tooltip=canvas.parentElement.querySelector(".comparison-chart-tooltip");
  if(tooltip)tooltip.hidden=true;
}

function renderComparisonAnalysis({contentId="comparisonContent",canvasId="comparisonChart",embedded=false}={}){
  const selectedProperties=comparedProperties(),content=document.querySelector(`#${contentId}`);
  if(selectedProperties.length<2){content.innerHTML=`<div class="analysis-empty"><div><b>比較する物件を2件以上選択してください</b><span>地図・一覧・物件リストの「＋ 比較」から最大${comparisonLimit}件を選択できます。</span></div></div>`;return}
  const metric=metrics[comparisonMetric];
  const resolvedMode=PIPAnalysis.resolveSeriesMode(comparisonSeriesMode,selectedProperties.length,individualSeriesLimit);
  const timeline=PIPAnalysis.buildComparisonTimeline(selectedProperties);
  const propertySeries=selectedProperties.map(property=>PIPAnalysis.buildComparisonSeries(property,comparisonMetric,timeline));
  const distribution=PIPAnalysis.distributionSeries(propertySeries);
  const latestDistribution=latestDistributionSnapshot(distribution,timeline,selectedProperties.length);
  const tabs=Object.entries(metrics).map(([key,item])=>`<button class="comparison-tab${key===comparisonMetric?" active":""}" data-comparison-metric="${key}">${esc(item.short)}</button>`).join("");
  const modeButtons=[["auto","自動"],["average","平均のみ"],["individual","個別＋平均"]].map(([mode,label])=>`<button type="button" class="${comparisonSeriesMode===mode?"active":""}" data-series-mode="${mode}">${label}</button>`).join("");
  const legend=resolvedMode==="individual"?selectedProperties.map((property,index)=>`<span><i class="comparison-swatch" style="background:${comparisonColor(index)}"></i>${esc(property.name)}</span>`).join(""):"";
  const minimumSampleCount=PIPAnalysis.minimumAverageSampleSize(selectedProperties.length);
  const distributionSummary=latestDistribution?`<section class="distribution-summary" aria-label="最新時点の分布サマリー"><div><span>最新比較時点</span><strong>${esc(latestDistribution.period)}</strong></div><div><span>平均値</span><strong>${comparisonValue(comparisonMetric,latestDistribution.average)}</strong></div><div><span>中央値</span><strong>${comparisonValue(comparisonMetric,latestDistribution.median)}</strong></div><div><span>中央50%</span><strong>${comparisonValue(comparisonMetric,latestDistribution.q1)} – ${comparisonValue(comparisonMetric,latestDistribution.q3)}</strong></div><div><span>開示カバレッジ</span><strong>${latestDistribution.count} / ${selectedProperties.length}件</strong><small>${latestDistribution.coveragePercent}%</small></div></section>`:"";
  const rows=selectedProperties.map((property,index)=>{
    const summary=PIPAnalysis.summary(property,comparisonMetric);
    return`<tr><td><div class="comparison-property"><i class="comparison-swatch" style="background:${comparisonColor(index)}"></i><b>${esc(property.name)}</b><button data-remove-comparison="${esc(property.id)}" aria-label="${esc(property.name)}を比較から外す">×</button></div><small>${esc(property.reit)}</small></td><td>${comparisonValue(comparisonMetric,summary.first)}</td><td><b>${comparisonValue(comparisonMetric,summary.latest)}</b></td><td>${comparisonDelta(comparisonMetric,summary.change)}</td><td>${summary.count}期</td></tr>`;
  }).join("");
  const modeMessage=resolvedMode==="average"
    ?`${selectedProperties.length}物件を暦年の上期・下期に揃えて平均表示中。母数${minimumSampleCount}件未満の半期は平均線から除外します。`
    :`${selectedProperties.length}物件を暦年の上期・下期に揃え、個別推移と平均を表示中。`;
  content.innerHTML=`${embedded?'<div class="workspace-analysis-heading"><div><span class="eyebrow">ANALYSIS WORKSPACE</span><h2>選択物件の時系列比較</h2></div><button id="openFullscreenAnalysis" class="secondary-button" type="button">全画面表示</button></div>':""}<div class="comparison-intro"><p>選択数に応じて見やすい表示へ自動調整します。グラフ上をマウスでなぞると、各時点の正確な値・分布・母数を確認できます。</p><span class="comparison-count">${selectedProperties.length} / ${comparisonLimit}物件</span></div><div class="comparison-control-row"><div class="comparison-tabs" role="tablist" aria-label="比較指標">${tabs}</div><div class="series-mode-control" role="group" aria-label="系列表示">${modeButtons}</div></div><p class="series-mode-status">${esc(modeMessage)}${comparisonSeriesMode==="auto"?`（自動基準：${individualSeriesLimit}物件以下は個別表示）`:""}</p>${distributionSummary}<div class="comparison-future"><span>専有坪単価：データ契約準備中</span><span>貸室賃料収入単価：定義統一後に追加</span></div><div class="comparison-chart-card"><div class="chart-card-heading"><div><span class="eyebrow">TIME SERIES</span><h3>${esc(metric.label)}推移</h3></div><div class="chart-card-notes"><span>${selectedProperties.length}物件</span><span>半期単位で整列</span><span><i class="gap-sample"></i>点線は未開示期間</span></div></div><div class="comparison-legend">${legend}<span><i class="comparison-swatch range"></i>中央50%</span><span><i class="comparison-swatch median"></i>中央値</span><span><i class="comparison-swatch average"></i>平均値</span></div><div class="comparison-chart-stage"><canvas id="${esc(canvasId)}" class="comparison-chart-base" aria-label="${esc(metric.label)}の複数物件比較グラフ"></canvas><canvas class="comparison-chart-overlay" data-chart-overlay-for="${esc(canvasId)}" aria-hidden="true"></canvas><div class="comparison-chart-tooltip" hidden></div></div></div><section class="comparison-table"><h3>${esc(metric.label)} サマリー</h3><div class="table-scroll"><table><thead><tr><th>物件</th><th>開始値</th><th>最新値</th><th>期間変化</th><th>開示時点</th></tr></thead><tbody>${rows}</tbody></table></div></section><p class="privacy-note">比較値は各物件のEvidence付き時系列を使用します。法人ごとに異なる決算月は暦年の上期・下期へ整列し、同じ物件に同一半期の開示が複数ある場合は最新の開示値を使います。平均・中央値・中央50%は欠損値を除外し、選択数が9件以上の場合は母数10%（最低3件）未満の半期を表示しません。未開示値の補間は行いません。点線は前後の開示値を視覚的に結ぶだけで、その期間の数値を推定しません。グラフ操作で公開値が変更されることはありません。</p>`;
  content.querySelectorAll("[data-comparison-metric]").forEach(button=>button.onclick=()=>{comparisonMetric=button.dataset.comparisonMetric;embedded?renderWorkspaceAnalysis():renderComparisonAnalysis()});
  content.querySelectorAll("[data-series-mode]").forEach(button=>button.onclick=()=>{comparisonSeriesMode=button.dataset.seriesMode;embedded?renderWorkspaceAnalysis():renderComparisonAnalysis()});
  content.querySelectorAll("[data-remove-comparison]").forEach(button=>button.onclick=()=>toggleComparison(button.dataset.removeComparison));
  const fullscreen=content.querySelector("#openFullscreenAnalysis");if(fullscreen)fullscreen.onclick=openComparisonAnalysis;
  requestAnimationFrame(()=>drawComparisonChart(selectedProperties,comparisonMetric,canvasId));
}

function openComparisonAnalysis(){
  if(comparisonIds.size<2)return;
  renderComparisonAnalysis();
  document.querySelector("#comparisonDialog").showModal();
}

function renderWorkspaceAnalysis(){
  renderComparisonAnalysis({contentId:"workspaceAnalysis",canvasId:"workspaceComparisonChart",embedded:true});
}

function drawHistoryHover(canvas,overlay,index){
  const model=canvas._pipHistoryModel;if(!model)return;
  const ctx=overlay.getContext("2d");
  ctx.clearRect(0,0,model.width,model.height);
  if(index==null||!model.history[index])return;
  const x=model.xAt(index),value=model.values[index];
  ctx.save();ctx.strokeStyle="#64748b";ctx.lineWidth=1;ctx.setLineDash([4,4]);
  ctx.beginPath();ctx.moveTo(x,model.pad.top);ctx.lineTo(x,model.pad.top+model.plotH);ctx.stroke();ctx.restore();
  if(value!=null){
    ctx.fillStyle="#fff";ctx.strokeStyle=model.metric.color;ctx.lineWidth=3;
    ctx.beginPath();ctx.arc(x,model.yAt(value),5.5,0,Math.PI*2);ctx.fill();ctx.stroke();
  }
}

function bindHistoryInteraction(canvas,overlay){
  if(overlay.dataset.historyInteractionBound)return;
  overlay.dataset.historyInteractionBound="true";
  const inspect=event=>{
    const model=canvas._pipHistoryModel;if(!model?.history.length)return;
    const rect=overlay.getBoundingClientRect();
    const pointerX=(event.clientX-rect.left)*(model.width/Math.max(rect.width,1));
    const index=PIPAnalysis.nearestTimelineIndex(pointerX,model.pad.left,model.plotW,model.history.length);
    drawHistoryHover(canvas,overlay,index);
    const tooltip=document.querySelector("#historyTooltip"),point=model.history[index],value=model.values[index];
    tooltip.innerHTML=`<b>${esc(point.as_of_date||point.period||`${point.period_no||"—"}期`)}</b><span>${esc(metrics[model.metricKey].label)}</span><strong>${comparisonValue(model.metricKey,value)}</strong>`;
    tooltip.hidden=false;
    const stage=canvas.parentElement,maxLeft=Math.max(8,stage.clientWidth-tooltip.offsetWidth-8),maxTop=Math.max(8,stage.clientHeight-tooltip.offsetHeight-8);
    tooltip.style.left=`${Math.max(8,Math.min(maxLeft,event.clientX-rect.left+12))}px`;
    tooltip.style.top=`${Math.max(8,Math.min(maxTop,event.clientY-rect.top-tooltip.offsetHeight/2))}px`;
  };
  overlay.addEventListener("pointerdown",inspect);
  overlay.addEventListener("pointermove",inspect);
  overlay.addEventListener("pointerleave",()=>{
    const tooltip=document.querySelector("#historyTooltip");if(tooltip)tooltip.hidden=true;
    drawHistoryHover(canvas,overlay,null);
  });
}

function drawHistory(p,metricKey){
  const metric=metrics[metricKey],history=[...p.periods].sort((a,b)=>(a.as_of_date||"").localeCompare(b.as_of_date||""));
  const values=history.map(item=>item[metricKey]);const available=values.filter(v=>v!=null);
  const canvas=document.querySelector("#historyChart");if(!canvas)return;
  const stage=canvas.parentElement,overlay=stage.querySelector(".history-chart-overlay");if(!overlay)return;
  const {width,height}=PIPChart.stageSize(stage,230,window.innerWidth-24);
  const ctx=PIPChart.prepareCanvas(canvas,width,height,window.devicePixelRatio);
  PIPChart.prepareCanvas(overlay,width,height,window.devicePixelRatio);
  const pad={left:52,right:16,top:20,bottom:40},plotW=width-pad.left-pad.right,plotH=height-pad.top-pad.bottom;
  if(!available.length){ctx.fillStyle="#64748b";ctx.font="13px sans-serif";ctx.fillText("この指標の履歴はありません",pad.left,90);return}
  let min=Math.min(...available),max=Math.max(...available);if(min===max){min-=Math.abs(min||1)*.05;max+=Math.abs(max||1)*.05}else{const margin=(max-min)*.12;min-=margin;max+=margin}
  ctx.font="10px sans-serif";ctx.textAlign="right";ctx.textBaseline="middle";
  for(let i=0;i<4;i++){const y=pad.top+plotH*i/3,value=max-(max-min)*i/3;ctx.strokeStyle="#e2e8f0";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(pad.left,y);ctx.lineTo(width-pad.right,y);ctx.stroke();ctx.fillStyle="#64748b";ctx.fillText(metricKey==="noi"||metricKey==="appraisal"?Math.round(value).toLocaleString():value.toFixed(1),pad.left-7,y)}
  const xAt=i=>pad.left+(history.length===1?plotW/2:plotW*i/(history.length-1)),yAt=value=>pad.top+(max-value)/(max-min)*plotH;
  PIPChart.drawSegmentedSeries(ctx,values,xAt,yAt,{color:metric.color,gapColor:metric.color,width:2.8,points:true,pointRadius:3.4});
  const labelStep=Math.max(1,Math.ceil(history.length/6));
  ctx.textAlign="right";ctx.textBaseline="top";ctx.fillStyle="#64748b";
  history.forEach((item,i)=>{
    if(i%labelStep!==0&&i!==history.length-1)return;
    const label=item.as_of_date?String(item.as_of_date).slice(0,7):(item.period_no?`${item.period_no}期`:item.period);
    ctx.save();ctx.translate(xAt(i),height-pad.bottom+9);ctx.rotate(-Math.PI/5);ctx.fillText(label,0,0);ctx.restore();
  });
  canvas._pipHistoryModel={property:p,metric,metricKey,history,values,pad,plotW,plotH,width,height,xAt,yAt};
  bindHistoryInteraction(canvas,overlay);
  bindStableChartResize(stage,()=>drawHistory(p,metricKey));
  const latest=[...history].reverse().find(item=>item[metricKey]!=null),previous=[...history].reverse().filter(item=>item[metricKey]!=null)[1];
  const delta=latest&&previous?latest[metricKey]-previous[metricKey]:null;
  document.querySelector("#historySummary").innerHTML=`<div class="history-summary"><div><span>最新値</span><b>${latest?metric.format(latest[metricKey]):"—"}</b></div><div><span>前期差</span><b class="${delta>0?"up":delta<0?"down":""}">${delta==null?"—":`${delta>0?"+":""}${metricKey==="noi"||metricKey==="appraisal"?`${delta.toLocaleString("ja-JP",{maximumFractionDigits:1})}百万円`:`${delta.toFixed(1)}pt`}`}</b></div><div><span>データ期間</span><b>${available.length}期</b></div></div>`;
}

function currentFilters(){
  return{
    query:document.querySelector("#search").value,reit:reitFilter.value,type:typeFilter.value,region:region.value,
    capMin:document.querySelector("#capMin").value,capMax:document.querySelector("#capMax").value,
    occupancyMin:document.querySelector("#occupancyMin").value,occupancyMax:document.querySelector("#occupancyMax").value,
    priceMin:document.querySelector("#priceMin").value,priceMax:document.querySelector("#priceMax").value,
    areaMin:document.querySelector("#areaMin").value,areaMax:document.querySelector("#areaMax").value,
    sort:document.querySelector("#sort").value
  };
}

function renderPropertyTable(){
  const content=document.querySelector("#propertyTable");
  if(!visible.length){content.innerHTML='<div class="analysis-empty"><div><b>条件に一致する物件がありません</b><span>検索条件を変更してください。</span></div></div>';return}
  const rows=visible.map(property=>`<tr class="${comparisonIds.has(property.id)?"selected-row":""}"><td><input class="property-checkbox" type="checkbox" data-table-compare="${esc(property.id)}" aria-label="${esc(property.name)}を比較対象にする"${comparisonIds.has(property.id)?" checked":""}></td><td><button class="property-name-button" type="button" data-table-property="${esc(property.id)}"><b>${esc(property.name)}</b><small>${esc(property.address)}</small></button></td><td>${esc(property.reit)}</td><td>${esc(property.type)}</td><td>${yen(property.price)}</td><td>${yen(property.appraisal)}</td><td>${pct(property.cap)}</td><td>${pct(property.occupancy)}</td><td>${area(property.leasable_area)}</td><td>${yen(property.noi)}</td></tr>`).join("");
  content.innerHTML=`<div class="table-note"><span>${visible.length.toLocaleString("ja-JP")}物件。チェックすると比較対象へ追加します。</span><span>未開示値は「—」表示</span></div><div class="property-table-wrap"><table class="property-table"><thead><tr><th>比較</th><th>物件名／住所</th><th>投資法人</th><th>用途</th><th>取得価格</th><th>鑑定評価額</th><th>鑑定CR</th><th>稼働率</th><th>賃貸可能面積</th><th>NOI</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  content.querySelectorAll("[data-table-compare]").forEach(checkbox=>checkbox.onchange=()=>toggleComparison(checkbox.dataset.tableCompare));
  content.querySelectorAll("[data-table-property]").forEach(button=>button.onclick=()=>{setWorkspaceView("map");selectProperty(properties.find(property=>property.id===button.dataset.tableProperty))});
}

function setWorkspaceView(view,{persist=true}={}){
  workspaceView=["map","table","analysis"].includes(view)?view:"map";
  document.querySelectorAll(".view-tab").forEach(button=>{const active=button.dataset.view===workspaceView;button.classList.toggle("active",active);button.setAttribute("aria-selected",String(active))});
  document.querySelectorAll(".workspace-view").forEach(panel=>{const active=panel.id===`${workspaceView}View`;panel.hidden=!active;panel.classList.toggle("active",active)});
  if(persist)try{localStorage.setItem(workspaceViewStorageKey,workspaceView)}catch{}
  if(workspaceView==="map")requestAnimationFrame(()=>{map.invalidateSize();renderMapMarkers()});
  if(workspaceView==="table")renderPropertyTable();
  if(workspaceView==="analysis")renderWorkspaceAnalysis();
}

function downloadCsv(items,filename){
  if(!items.length)return;
  const keys=["id","reit_code","reit","name","type","region","address","lat","lng","price","book_value","appraisal","cap","discount_rate","terminal_cap_rate","occupancy","noi","leasable_area","leased_area","tenants"];
  const csv=PIPWorkspace.toCsv(items,keys),url=URL.createObjectURL(new Blob(["\ufeff"+csv],{type:"text/csv"}));
  const anchor=document.createElement("a");anchor.href=url;anchor.download=filename;anchor.click();URL.revokeObjectURL(url);
}

function clearComparison({closeDialog=false}={}){
  comparisonIds.clear();persistComparison();updateComparisonButton();render();
  if(selected)selectProperty(selected);
  if(closeDialog)document.querySelector("#comparisonDialog").close();
  if(workspaceView==="analysis")renderWorkspaceAnalysis();
}

function resetFilters(){
  document.querySelector("#search").value="";reitFilter.value="";typeFilter.value="";region.value="";
  numericFilterIds.forEach(id=>document.querySelector(`#${id}`).value="");
  document.querySelector("#sort").value="name-asc";mapBoundsFilter=null;radiusFilter=null;radiusPickMode=false;boxSelectionMode=false;boxStart=null;map.dragging.enable();
  if(selectionBox){map.removeLayer(selectionBox);selectionBox=null}
  renderRadiusOverlay();render();
}

function render(){
  const filtered=PIPWorkspace.filterAndSort(properties,currentFilters());
  const bounded=mapBoundsFilter?filtered.filter(property=>PIPMapAnalysis.boundsContain(property,mapBoundsFilter)):filtered;
  visible=radiusFilter?bounded.filter(property=>PIPSpatialAnalysis.withinRadius(property,radiusFilter)):bounded;
  document.querySelector("#count").textContent=visible.length;
  document.querySelector("#list").innerHTML=visible.map(p=>`<div class="item${selected?.id===p.id?" active":""}" data-id="${esc(p.id)}"><b>${esc(p.name)}</b><small>${esc(p.address)}</small><br><span class="pill">${esc(p.region||p.type)}・CR ${pct(p.cap)}</span><button class="compare-toggle${comparisonIds.has(p.id)?" selected":""}" data-compare-id="${esc(p.id)}" aria-pressed="${comparisonIds.has(p.id)}">${comparisonIds.has(p.id)?"✓ 比較":"＋ 比較"}</button></div>`).join("")||'<p class="range-empty-note">この条件・地図範囲に該当する物件はありません。</p>';
  renderMapMarkers();
  document.querySelectorAll(".item").forEach(el=>el.onclick=()=>selectProperty(properties.find(p=>p.id===el.dataset.id)));
  document.querySelectorAll("[data-compare-id]").forEach(button=>button.onclick=event=>{event.stopPropagation();toggleComparison(button.dataset.compareId)});
  if(workspaceView==="table")renderPropertyTable();
  if(workspaceView==="analysis")renderWorkspaceAnalysis();
  updateComparisonButton();
  updateMapAnalysisControls();
}
document.querySelector("#search").oninput=render;reitFilter.onchange=render;typeFilter.onchange=render;region.onchange=render;
numericFilterIds.forEach(id=>document.querySelector(`#${id}`).oninput=render);
document.querySelector("#sort").onchange=render;
document.querySelector("#resetFilters").onclick=resetFilters;
document.querySelectorAll(".view-tab").forEach(button=>button.onclick=()=>setWorkspaceView(button.dataset.view));
document.querySelector("#comparisonButton").onclick=openComparisonAnalysis;
document.querySelector("#clearComparison").onclick=()=>clearComparison({closeDialog:true});
document.querySelector("#clearSelection").onclick=()=>clearComparison();
document.querySelector("#openSelectedAnalysis").onclick=()=>setWorkspaceView("analysis");
document.querySelector("#filterMapBounds").onclick=applyMapBoundsFilter;
document.querySelector("#clearMapBounds").onclick=clearMapBoundsFilter;
document.querySelector("#toggleRadiusSearch").onclick=()=>toggleRadiusPanel();
document.querySelector("#closeRadiusPanel").onclick=()=>toggleRadiusPanel(false);
document.querySelector("#radiusFromCenter").onclick=()=>applyRadiusFilter(map.getCenter(),"地図中心");
document.querySelector("#radiusPick").onclick=beginRadiusPick;
document.querySelector("#clearRadius").onclick=clearRadiusFilter;
document.querySelector("#radiusKm").oninput=event=>{
  const radiusKm=PIPSpatialAnalysis.normalizeRadiusKm(event.target.value);
  document.querySelector("#radiusValue").textContent=`${radiusText(radiusKm)} km`;
  if(radiusFilter){
    radiusFilter={...radiusFilter,radiusKm};
    if(radiusCircle)radiusCircle.setRadius(radiusKm*1000);
    const handlePoint=PIPSpatialAnalysis.destinationPoint(radiusFilter,radiusKm);
    if(radiusHandle)radiusHandle.setLatLng(handlePoint);
    document.querySelector("#radiusStatus").textContent=`半径${radiusText(radiusKm)}kmに調整中`;
  }
};
document.querySelector("#radiusKm").onchange=()=>{if(radiusFilter){renderRadiusOverlay();render();updateMapAnalysisControls(`半径${radiusText(radiusFilter.radiusKm)}km・${visible.length.toLocaleString("ja-JP")}件`)}};
document.querySelector("#toggleBoxSelection").onclick=()=>setBoxSelectionMode(!boxSelectionMode);
document.querySelector("#clearBoxSelection").onclick=clearSelectionBox;
document.querySelector("#selectVisible").onclick=selectVisibleForComparison;
document.querySelector("#export").onclick=()=>downloadCsv(visible,"jreit-visible-properties.csv");
document.querySelector("#exportSelected").onclick=()=>downloadCsv(comparedProperties(),"jreit-selected-properties.csv");
map.on("zoomend",()=>{renderMapMarkers();updateMapAnalysisControls()});
map.on("click",event=>{if(radiusPickMode)applyRadiusFilter(event.latlng,"指定地点")});
map.on("mousedown",event=>{
  if(!boxSelectionMode)return;
  boxStart=event.latlng;
  if(selectionBox)map.removeLayer(selectionBox);
  selectionBox=L.rectangle(L.latLngBounds(boxStart,boxStart),{color:"#b45309",weight:2,dashArray:"6 4",fillColor:"#f59e0b",fillOpacity:.16,className:"selection-box"}).addTo(map);
  updateMapAnalysisControls("選択する範囲までドラッグしてください");
});
map.on("mousemove",event=>{if(boxSelectionMode&&boxStart&&selectionBox)selectionBox.setBounds(L.latLngBounds(boxStart,event.latlng))});
map.on("mouseup",event=>{
  if(!boxSelectionMode||!boxStart||!selectionBox)return;
  selectionBox.setBounds(L.latLngBounds(boxStart,event.latlng));boxStart=null;finishBoxSelection(selectionBox.getBounds());
});
window.addEventListener("keydown",event=>{if(event.key==="Escape"&&boxSelectionMode){setBoxSelectionMode(false);clearSelectionBox()}});
window.addEventListener("resize",()=>{if(selected){const metric=document.querySelector("#historyMetric");if(metric)drawHistory(selected,metric.value)}if(document.querySelector("#comparisonDialog").open)drawComparisonChart(comparedProperties(),comparisonMetric);if(workspaceView==="analysis")drawComparisonChart(comparedProperties(),comparisonMetric,"workspaceComparisonChart")});
renderCapLegend();
loadData().catch(err=>{document.querySelector("#dataset").textContent="読込エラー";document.querySelector("#detail").innerHTML=`<p class="error">データを読み込めませんでした。${esc(err.message)}</p>`});
loadImportStatus();
loadQualityStatus();
loadChangeStatus();
