export function Waveform({
  values,
  compact = false,
  active = true,
}: {
  values: number[];
  compact?: boolean;
  active?: boolean;
}) {
  const count = compact ? 18 : 96;
  const source = compact
    ? values.slice(-18)
    : Array.from(
        { length: count },
        (_, i) => values[Math.min(values.length - 1, Math.floor(i / 3))] ?? 0,
      );
  return (
    <svg
      className={`waveform ${compact ? "compact" : ""}`}
      viewBox={`0 0 ${count * 5} 48`}
      role="img"
      aria-label={active ? "Live microphone level" : "Microphone inactive"}
      preserveAspectRatio="none"
    >
      {source.map((value, i) => {
        const height = 2 + (active ? Math.max(0, Math.min(1, value)) : 0) * 42;
        return (
          <rect
            key={i}
            x={i * 5}
            y={(48 - height) / 2}
            width="2.5"
            height={height}
            rx="1.25"
          />
        );
      })}
    </svg>
  );
}
