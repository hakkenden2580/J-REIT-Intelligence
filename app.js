// 画面・操作確認用の架空データです。実データはData Engine完成後に差し替えます。
const properties=[
 {id:"DEMO-001",name:"丸の内サンプルビル",reit:"デモ投資法人",type:"オフィス",address:"東京都千代田区丸の内",lat:35.6812,lng:139.7671,price:42000,cap:3.4,occupancy:99.2,noi:1530,appraisal:46800},
 {id:"DEMO-002",name:"新宿サンプルタワー",reit:"デモ投資法人",type:"オフィス",address:"東京都新宿区西新宿",lat:35.6896,lng:139.6917,price:31500,cap:3.7,occupancy:98.5,noi:1240,appraisal:34200},
 {id:"DEMO-003",name:"品川サンプルレジデンス",reit:"デモ住宅投資法人",type:"住宅",address:"東京都港区港南",lat:35.6285,lng:139.7387,price:12800,cap:3.8,occupancy:97.8,noi:520,appraisal:13900},
 {id:"DEMO-004",name:"流山サンプル物流センター",reit:"デモ物流投資法人",type:"物流",address:"千葉県流山市",lat:35.8563,lng:139.9029,price:24600,cap:4.1,occupancy:100,noi:1090,appraisal:26700},
 {id:"DEMO-005",name:"横浜サンプルモール",reit:"デモ商業投資法人",type:"商業",address:"神奈川県横浜市西区",lat:35.4658,lng:139.6223,price:19800,cap:4.3,occupancy:98.1,noi:920,appraisal:20700},
 {id:"DEMO-006",name:"大阪サンプルホテル",reit:"デモホテル投資法人",type:"ホテル",address:"大阪府大阪市北区",lat:34.7055,lng:135.4983,price:22100,cap:4.5,occupancy:92.4,noi:1040,appraisal:23500}
];
const map=L.map("map").setView([35.55,139.55],8);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"&copy; OpenStreetMap contributors"}).addTo(map);
const markers=L.layerGroup().addTo(map);let visible=[...properties];
const yen=n=>n==null?"—":`${n.toLocaleString()}百万円`;const pct=n=>n==null?"—":`${n.toFixed(1)}%`;
const type=document.querySelector("#type");[...new Set(properties.map(x=>x.type))].forEach(x=>type.add(new Option(x,x)));
function select(p){document.querySelector("#detail").innerHTML=`<h2>${p.name}</h2><div class="address">${p.address}</div><span class="pill">${p.type}</span><div class="metrics"><div class="metric"><span>取得価格</span><b>${yen(p.price)}</b></div><div class="metric"><span>鑑定評価額</span><b>${yen(p.appraisal)}</b></div><div class="metric"><span>CAP</span><b>${pct(p.cap)}</b></div><div class="metric"><span>稼働率</span><b>${pct(p.occupancy)}</b></div><div class="metric"><span>NOI</span><b>${yen(p.noi)}</b></div><div class="metric"><span>投資法人</span><b style="font-size:13px">${p.reit}</b></div></div><div class="source">デモデータ（架空）。実データとして利用しないでください。</div>`;map.flyTo([p.lat,p.lng],13)}
function render(){const q=document.querySelector("#search").value.toLowerCase(),t=type.value;visible=properties.filter(p=>(!t||p.type===t)&&(`${p.name} ${p.address} ${p.reit}`.toLowerCase().includes(q)));document.querySelector("#count").textContent=visible.length;document.querySelector("#list").innerHTML=visible.map(p=>`<div class="item" data-id="${p.id}"><b>${p.name}</b><small>${p.address}</small><br><span class="pill">${p.type}・CAP ${pct(p.cap)}</span></div>`).join("");markers.clearLayers();visible.forEach(p=>L.marker([p.lat,p.lng]).addTo(markers).bindTooltip(p.name).on("click",()=>select(p)));document.querySelectorAll(".item").forEach(el=>el.onclick=()=>select(properties.find(p=>p.id===el.dataset.id)))}
document.querySelector("#search").oninput=render;type.onchange=render;
document.querySelector("#export").onclick=()=>{const keys=Object.keys(properties[0]);const csv=[keys.join(","),...visible.map(p=>keys.map(k=>`"${String(p[k]??"").replaceAll('"','""')}"`).join(","))].join("\n");const a=document.createElement("a");a.href=URL.createObjectURL(new Blob(["\ufeff"+csv],{type:"text/csv"}));a.download="jreit-demo.csv";a.click()};render();
