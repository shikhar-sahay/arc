import { clamp } from "../lib/utils";

interface MiniSparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  max?: number;
  className?: string;
}

/**
 * A tiny SVG sparkline for rolling CPU/memory history.
 * No external dependencies needed for two simple lines.
 */
export function MiniSparkline({
  data,
  width = 120,
  height = 28,
  color = "#22d3ee",
  max = 100,
  className = "",
}: MiniSparklineProps) {
  if (data.length < 2) {
    return (
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className={className}
      >
        <line
          x1="0"
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="#334155"
          strokeWidth="1"
        />
      </svg>
    );
  }

  const pad = 2;
  const w = width - pad * 2;
  const h = height - pad * 2;

  const points = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * w;
    const y = pad + h - (clamp(v, 0, max) / max) * h;
    return `${x},${y}`;
  });

  const polyline = points.join(" ");
  const lastX = pad + w;
  const lastY = pad + h - (clamp(data[data.length - 1], 0, max) / max) * h;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={className}
      role="img"
      aria-label="Metric history sparkline"
    >
      <polyline
        points={polyline}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity="0.7"
      />
      <circle cx={lastX} cy={lastY} r="2" fill={color} opacity="0.9" />
    </svg>
  );
}
