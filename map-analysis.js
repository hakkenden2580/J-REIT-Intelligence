(function(root,factory){
  const api=factory();
  if(typeof module==="object"&&module.exports)module.exports=api;
  else root.PIPMapAnalysis=api;
})(typeof globalThis!=="undefined"?globalThis:this,function(){
  const bands=[
    {key:"under-3-5",label:"〜3.5",min:null,max:3.5,color:"#52cf9a"},
    {key:"3-5-to-4",label:"3.5〜4.0",min:3.5,max:4,color:"#0ca66a"},
    {key:"4-to-4-5",label:"4.0〜4.5",min:4,max:4.5,color:"#2878e8"},
    {key:"4-5-to-5",label:"4.5〜5.0",min:4.5,max:5,color:"#1942d1"},
    {key:"5-to-5-5",label:"5.0〜5.5",min:5,max:5.5,color:"#6d28d9"},
    {key:"over-5-5",label:"5.5〜",min:5.5,max:null,color:"#14233b"},
    {key:"unknown",label:"不明",min:null,max:null,color:"#94a3b8",unknown:true}
  ];

  function bandFor(value){
    const numeric=Number(value);
    if(value==null||value===""||!Number.isFinite(numeric))return bands.at(-1);
    return bands.find(band=>!band.unknown&&(band.min==null||numeric>=band.min)&&(band.max==null||numeric<band.max))||bands.at(-1);
  }

  function boundsContain(property,bounds){
    if(!bounds||property.lat==null||property.lng==null)return false;
    const lat=Number(property.lat),lng=Number(property.lng);
    return Number.isFinite(lat)&&Number.isFinite(lng)&&lat>=bounds.south&&lat<=bounds.north&&lng>=bounds.west&&lng<=bounds.east;
  }

  function selectIds(properties,existingIds,limit=8){
    const selected=[...existingIds].slice(0,limit),selectedSet=new Set(selected);
    for(const property of properties){
      if(selected.length>=limit)break;
      if(property?.id&&!selectedSet.has(property.id)){selected.push(property.id);selectedSet.add(property.id)}
    }
    return selected;
  }

  return{bands,bandFor,boundsContain,selectIds};
});
