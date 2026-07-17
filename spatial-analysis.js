(function(root,factory){
  const api=factory();
  if(typeof module==="object"&&module.exports)module.exports=api;
  else root.PIPSpatialAnalysis=api;
})(typeof globalThis!=="undefined"?globalThis:this,function(){
  function coordinates(value){
    const lat=Number(value?.lat),lng=Number(value?.lng);
    return Number.isFinite(lat)&&Number.isFinite(lng)?{lat,lng}:null;
  }

  function normalizeRadiusKm(value,fallback=3){
    const numeric=Number(value);
    return Number.isFinite(numeric)&&numeric>=0?Math.min(50,Math.max(.5,numeric)):fallback;
  }

  function haversineKm(a,b){
    const first=coordinates(a),second=coordinates(b);
    if(!first||!second)return null;
    const radians=value=>value*Math.PI/180;
    const dLat=radians(second.lat-first.lat),dLng=radians(second.lng-first.lng);
    const h=Math.sin(dLat/2)**2+Math.cos(radians(first.lat))*Math.cos(radians(second.lat))*Math.sin(dLng/2)**2;
    return 6371*2*Math.atan2(Math.sqrt(h),Math.sqrt(1-h));
  }

  function withinRadius(property,filter){
    if(!filter)return true;
    const distance=haversineKm(property,filter);
    return distance!=null&&distance<=normalizeRadiusKm(filter.radiusKm);
  }

  function destinationPoint(origin,distanceKm,bearingDegrees=90){
    const start=coordinates(origin);
    if(!start)return null;
    const distance=normalizeRadiusKm(distanceKm)/6371,bearing=Number(bearingDegrees)*Math.PI/180;
    const lat1=start.lat*Math.PI/180,lng1=start.lng*Math.PI/180;
    const lat2=Math.asin(Math.sin(lat1)*Math.cos(distance)+Math.cos(lat1)*Math.sin(distance)*Math.cos(bearing));
    const lng2=lng1+Math.atan2(Math.sin(bearing)*Math.sin(distance)*Math.cos(lat1),Math.cos(distance)-Math.sin(lat1)*Math.sin(lat2));
    return{lat:lat2*180/Math.PI,lng:lng2*180/Math.PI};
  }

  return{coordinates,normalizeRadiusKm,haversineKm,withinRadius,destinationPoint};
});
