interface Series {
  label: string;
  values: number[];
  color: string;
}

export function TelemetryChart({
  series,
  height = 150,
}: {
  series: Series[];
  height?: number;
}) {
  const count = Math.max(2, ...series.map((item) => item.values.length));
  const points = (values: number[]) =>
    values
      .map((value, index) => {
        const x = (index / (count - 1)) * 100;
        const y = 100 - Math.max(0, Math.min(100, value));
        return `${x},${y}`;
      })
      .join(" ");

  return (
    <div className="telemetry-chart" style={{ height }}>
      <div className="chart-grid" aria-hidden="true" />
      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        role="img"
        aria-label={series
          .map((item) => `${item.label} utilization`)
          .join(" and ")}
      >
        {series.map(
          (item) =>
            item.values.length > 1 && (
              <polyline
                key={item.label}
                points={points(item.values)}
                fill="none"
                stroke={item.color}
                strokeWidth="1.8"
                vectorEffect="non-scaling-stroke"
              />
            ),
        )}
      </svg>
      <span className="axis-label axis-top">100%</span>
      <span className="axis-label axis-bottom">0</span>
      <div className="chart-legend">
        {series.map((item) => (
          <span key={item.label}>
            <i style={{ background: item.color }} />
            {item.label}
          </span>
        ))}
      </div>
    </div>
  );
}
