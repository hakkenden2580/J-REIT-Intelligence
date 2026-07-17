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

  const comparisonPeriodKey = (period, index = 0) => {
    const match = String(period?.as_of_date || "").match(/^(\d{4})-(\d{2})/);
    if (!match) return periodKey(period, index);
    const half = Number(match[2]) <= 6 ? 1 : 2;
    return `${match[1]}-H${half}`;
  };

  const comparisonPeriodLabel = (period, key) => {
    const match = String(key).match(/^(\d{4})-H([12])$/);
    if (!match) return periodLabel(period, key);
    return `${match[1]}-${match[2] === "1" ? "06" : "12"}`;
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

  function buildComparisonTimeline(properties) {
    const byKey = new Map();
    properties.forEach(property => {
      (property.periods || []).forEach((period, index) => {
        const key = comparisonPeriodKey(period, index);
        if (!byKey.has(key)) {
          byKey.set(key, {key, label: comparisonPeriodLabel(period, key)});
        }
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

  function buildComparisonSeries(property, metricKey, timeline) {
    const values = new Map();
    (property.periods || []).forEach((period, index) => {
      const numeric = Number(period?.[metricKey]);
      if (period?.[metricKey] == null || Number.isNaN(numeric)) return;
      const key = comparisonPeriodKey(period, index);
      const observedAt = period?.as_of_date
        ? String(period.as_of_date)
        : `index-${String(index).padStart(6, "0")}`;
      const previous = values.get(key);
      if (!previous || observedAt >= previous.observedAt) {
        values.set(key, {value: numeric, observedAt});
      }
    });
    return timeline.map(point => values.get(point.key)?.value ?? null);
  }

  function averageSeries(seriesList) {
    if (!seriesList.length) return [];
    return seriesList[0].map((_, index) => {
      const values = seriesList.map(series => series[index]).filter(value => value != null);
      return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
    });
  }

  function sampleCounts(seriesList) {
    if (!seriesList.length) return [];
    return seriesList[0].map((_, index) =>
      seriesList.reduce((count, series) => count + (series[index] == null ? 0 : 1), 0)
    );
  }

  function minimumAverageSampleSize(propertyCount) {
    if (propertyCount <= 8) return 1;
    return Math.max(3, Math.ceil(propertyCount * 0.1));
  }

  function quantile(values, probability) {
    const sorted = (values || [])
      .filter(value => value != null && !Number.isNaN(Number(value)))
      .map(Number)
      .sort((a, b) => a - b);
    if (!sorted.length) return null;
    if (sorted.length === 1) return sorted[0];
    const position = Math.max(0, Math.min(1, Number(probability) || 0)) * (sorted.length - 1);
    const lower = Math.floor(position);
    const upper = Math.ceil(position);
    if (lower === upper) return sorted[lower];
    const weight = position - lower;
    return sorted[lower] * (1 - weight) + sorted[upper] * weight;
  }

  function distributionSeries(seriesList, minimumCount = minimumAverageSampleSize(seriesList.length)) {
    if (!seriesList.length) {
      return {average: [], median: [], q1: [], q3: [], counts: [], minimumCount};
    }
    const points = seriesList[0].map((_, index) =>
      seriesList
        .map(series => series[index])
        .filter(value => value != null && !Number.isNaN(Number(value)))
        .map(Number)
    );
    const visible = values => values.length >= minimumCount;
    return {
      average: points.map(values =>
        visible(values) ? values.reduce((sum, value) => sum + value, 0) / values.length : null
      ),
      median: points.map(values => visible(values) ? quantile(values, 0.5) : null),
      q1: points.map(values => visible(values) ? quantile(values, 0.25) : null),
      q3: points.map(values => visible(values) ? quantile(values, 0.75) : null),
      counts: points.map(values => values.length),
      minimumCount,
    };
  }

  function coverageAwareAverage(seriesList, minimumCount = minimumAverageSampleSize(seriesList.length)) {
    const distribution = distributionSeries(seriesList, minimumCount);
    return {
      average: distribution.average,
      counts: distribution.counts,
      minimumCount: distribution.minimumCount,
    };
  }

  function resolveSeriesMode(requestedMode, propertyCount, individualLimit = 8) {
    if (requestedMode === "average" || requestedMode === "individual") return requestedMode;
    return propertyCount > individualLimit ? "average" : "individual";
  }

  function nearestTimelineIndex(pointerX, plotLeft, plotWidth, timelineLength) {
    if (!timelineLength) return null;
    if (timelineLength === 1 || plotWidth <= 0) return 0;
    const ratio = Math.max(0, Math.min(1, (pointerX - plotLeft) / plotWidth));
    return Math.max(0, Math.min(timelineLength - 1, Math.round(ratio * (timelineLength - 1))));
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

  return {
    periodKey,
    comparisonPeriodKey,
    buildTimeline,
    buildComparisonTimeline,
    buildSeries,
    buildComparisonSeries,
    averageSeries,
    sampleCounts,
    minimumAverageSampleSize,
    quantile,
    distributionSeries,
    coverageAwareAverage,
    resolveSeriesMode,
    nearestTimelineIndex,
    summary,
  };
}));
