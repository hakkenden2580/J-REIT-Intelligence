(function(root,factory){
  const api=factory();
  if(typeof module==="object"&&module.exports)module.exports=api;
  else root.PIPWorkspace=api;
})(typeof globalThis!=="undefined"?globalThis:this,function(){
  const numberOrNull=value=>{
    if(value==null||value==="")return null;
    const parsed=Number(value);
    return Number.isFinite(parsed)?parsed:null;
  };

  const inRange=(value,min,max)=>{
    const lower=numberOrNull(min),upper=numberOrNull(max);
    if(lower==null&&upper==null)return true;
    const numeric=numberOrNull(value);
    if(numeric==null)return false;
    return(lower==null||numeric>=lower)&&(upper==null||numeric<=upper);
  };

  const compareNullable=(left,right,direction=1)=>{
    const a=numberOrNull(left),b=numberOrNull(right);
    if(a==null&&b==null)return 0;
    if(a==null)return 1;
    if(b==null)return-1;
    return(a-b)*direction;
  };

  function filterProperties(properties,filters={}){
    const query=String(filters.query||"").trim().toLocaleLowerCase("ja");
    return properties.filter(property=>
      (!filters.reit||property.reit===filters.reit)&&
      (!filters.type||property.type===filters.type)&&
      (!filters.region||property.region===filters.region)&&
      (!query||`${property.name||""} ${property.address||""} ${property.reit||""}`.toLocaleLowerCase("ja").includes(query))&&
      inRange(property.cap,filters.capMin,filters.capMax)&&
      inRange(property.terminal_cap_rate,filters.terminalCapMin,filters.terminalCapMax)&&
      inRange(property.occupancy,filters.occupancyMin,filters.occupancyMax)&&
      inRange(property.price,filters.priceMin,filters.priceMax)&&
      inRange(property.leasable_area,filters.areaMin,filters.areaMax)
    );
  }

  function sortProperties(properties,sort="name-asc"){
    const result=[...properties];
    const [field,direction]=String(sort).split("-");
    if(field==="name")return result.sort((a,b)=>String(a.name||"").localeCompare(String(b.name||""),"ja"));
    const propertyField=field==="area"?"leasable_area":field;
    return result.sort((a,b)=>compareNullable(a[propertyField],b[propertyField],direction==="desc"?-1:1)||String(a.name||"").localeCompare(String(b.name||""),"ja"));
  }

  function filterAndSort(properties,filters={}){
    return sortProperties(filterProperties(properties,filters),filters.sort||"name-asc");
  }

  const csvEscape=value=>`"${String(value??"").replaceAll('"','""')}"`;
  function toCsv(properties,keys){
    return[keys.join(","),...properties.map(property=>keys.map(key=>csvEscape(property[key])).join(","))].join("\n");
  }

  return{numberOrNull,inRange,filterProperties,sortProperties,filterAndSort,toCsv};
});
