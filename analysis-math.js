(function attachAnalysisMath(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.PIPAnalysis = api;
}(typeof window !== "undefined" ? window : globalThis, function createAnalysisMath() {
  const periodKey = (period, index = 0) => {
    if (period?.as_of_date) return String(period.as_of_date);
    if (period?.period_no != null) return `period-${String(period.period_no).padStart(6, "0")}`;
    return `index-${String(index).padStart(6, "0")}`;
  };

  const periodLabel = (period, key) => {
    if (period?.as_of_date) return String(period.as_of_date).slice(0, 7);
    return period?.period || (period?.period_no != null ? `第${period.period_no}期` : key);
  };

  function buildTimeline(properties) {
    const byKey = new Map();
    properties.forEach(property => {
      (property.periods || []).forEach((period, index) => {
        const key = periodKey(period, index);
        if (!byKey.has(key)) byKey.set(key, {key, label: periodLabel(period, key)});
      });
    });
    return [...byKey.values()].sort((a, b) => a.key.localeCompare(b.key));
  }

  function buildSeries(property, metricKey, timeline) {
    const values = new Map();
    (property.periods || []).forEach((period, index) => {
      const value = period?.[metricKey];
      values.set(periodKey(period, index), value == null || Number.isNaN(Number(value)) ? null : Number(value));
    });
    return timeline.map(point => values.has(point.key) ? values.get(point.key) : null);
  }

  function averageSeries(seriesList) {
    if (!seriesList.length) return [];
    return seriesList[0].map((_, index) => {
      const values = seriesList.map(series => series[index]).filter(value => value != null);
      return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
    });
  }

  function summary(property, metricKey) {
    const values = (property.periods || [])
      .map((period, index) => ({key: periodKey(period, index), value: period?.[metricKey]}))
      .filter(item => item.value != null && !Number.isNaN(Number(item.value)))
      .sort((a, b) => a.key.localeCompare(b.key))
      .map(item => Number(item.value));
    if (!values.length) return {first: null, latest: null, change: null, count: 0};
    return {
      first: values[0],
      latest: values[values.length - 1],
      change: values[values.length - 1] - values[0],
      count: values.length,
    };
  }

  return {periodKey, buildTimeline, buildSeries, averageSeries, summary};
}));
