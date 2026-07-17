(function attachChartRenderer(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.PIPChart = api;
}(typeof window !== "undefined" ? window : globalThis, function createChartRenderer() {
  function numericPoint(value, index) {
    if (value == null || Number.isNaN(Number(value))) return null;
    return {index, value: Number(value)};
  }

  function segmentSeries(values) {
    const solid = [];
    const gaps = [];
    const points = [];
    let current = [];
    let previous = null;
    let missingSincePrevious = false;

    (values || []).forEach((value, index) => {
      const point = numericPoint(value, index);
      if (!point) {
        if (current.length) solid.push(current);
        current = [];
        if (previous) missingSincePrevious = true;
        return;
      }

      points.push(point);
      if (missingSincePrevious && previous) gaps.push([previous, point]);
      current.push(point);
      previous = point;
      missingSincePrevious = false;
    });

    if (current.length) solid.push(current);
    return {solid, gaps, points};
  }

  function stableChartWidth(measuredWidth, viewportWidth, minimum = 240, maximum = 2000) {
    const viewport = Number.isFinite(Number(viewportWidth)) && Number(viewportWidth) > 0
      ? Number(viewportWidth)
      : maximum;
    const measured = Number.isFinite(Number(measuredWidth)) && Number(measuredWidth) > 0
      ? Number(measuredWidth)
      : viewport;
    const safeMinimum = Math.min(minimum, viewport);
    return Math.round(Math.max(safeMinimum, Math.min(measured, viewport, maximum)));
  }

  function stageSize(stage, height, viewportWidth) {
    const rectWidth = stage?.getBoundingClientRect?.().width;
    const measured = rectWidth || stage?.clientWidth || viewportWidth;
    return {
      width: stableChartWidth(measured, viewportWidth),
      height: Math.max(160, Math.round(Number(height) || 390)),
    };
  }

  function prepareCanvas(canvas, width, height, devicePixelRatio = 1) {
    const dpr = Math.max(1, Math.min(2, Number(devicePixelRatio) || 1));
    const pixelWidth = Math.round(width * dpr);
    const pixelHeight = Math.round(height * dpr);
    canvas.style.width = "100%";
    canvas.style.height = `${height}px`;
    if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
    if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
    const context = canvas.getContext("2d");
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, width, height);
    return context;
  }

  function drawSegmentedSeries(context, values, xAt, yAt, options = {}) {
    const {
      color = "#2457e6",
      width = 2.3,
      points = true,
      pointRadius = 3,
      gapColor = color,
      gapDash = [5, 5],
      opacity = 1,
    } = options;
    const segments = segmentSeries(values);

    context.save();
    context.globalAlpha = opacity;
    context.strokeStyle = color;
    context.lineWidth = width;
    context.lineJoin = "round";
    context.lineCap = "round";
    context.setLineDash([]);
    segments.solid.forEach(segment => {
      if (segment.length < 2) return;
      context.beginPath();
      segment.forEach((point, index) => {
        const x = xAt(point.index);
        const y = yAt(point.value);
        if (index === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      });
      context.stroke();
    });

    context.strokeStyle = gapColor;
    context.setLineDash(gapDash);
    context.globalAlpha = Math.min(opacity, 0.58);
    segments.gaps.forEach(([from, to]) => {
      context.beginPath();
      context.moveTo(xAt(from.index), yAt(from.value));
      context.lineTo(xAt(to.index), yAt(to.value));
      context.stroke();
    });

    if (points) {
      context.setLineDash([]);
      context.globalAlpha = opacity;
      segments.points.forEach(point => {
        context.fillStyle = "#fff";
        context.strokeStyle = color;
        context.lineWidth = Math.max(1.5, width * 0.72);
        context.beginPath();
        context.arc(xAt(point.index), yAt(point.value), pointRadius, 0, Math.PI * 2);
        context.fill();
        context.stroke();
      });
    }
    context.restore();
    return segments;
  }

  return {
    segmentSeries,
    stableChartWidth,
    stageSize,
    prepareCanvas,
    drawSegmentedSeries,
  };
}));
