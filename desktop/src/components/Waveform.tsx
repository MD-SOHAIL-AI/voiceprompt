import { motion } from 'framer-motion';

interface WaveformProps {
  values: number[];
  active?: boolean;
  compact?: boolean;
  tone?: 'recording' | 'processing' | 'cleaning' | 'neutral';
}

export function Waveform({ values, active = true, compact = false, tone = 'recording' }: WaveformProps) {
  const count = compact ? 18 : Math.min(32, values.length);
  const source = values.slice(-count);
  return (
    <div className={`waveform waveform-${tone} ${compact ? 'waveform-compact' : ''}`} aria-label="Live microphone level">
      {source.map((value, index) => {
        const normalized = active ? Math.max(0.08, Math.min(1, value)) : 0.08;
        const height = compact ? 4 + normalized * 22 : 5 + normalized * 42;
        return (
          <motion.span
            key={index}
            className="waveform-bar"
            animate={{ height }}
            transition={{ duration: 0.09, ease: 'easeOut' }}
          />
        );
      })}
    </div>
  );
}
