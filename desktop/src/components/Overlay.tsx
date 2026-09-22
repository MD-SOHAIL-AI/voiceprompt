import { useEffect, useMemo, useState } from 'react';
import { Check, LoaderCircle, Mic2, TriangleAlert } from 'lucide-react';
import { bootstrap, listenEngine } from '../lib/backend';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { useAppStore } from '../store';
import { Waveform } from './Waveform';

export function Overlay() {
  const status = useAppStore((s) => s.status);
  const waveform = useAppStore((s) => s.waveform);
  const handleEngineEvent = useAppStore((s) => s.handleEngineEvent);
  const [visibility, setVisibility] = useState<'always' | 'recording' | 'hidden-idle'>('always');

  useEffect(() => {
    bootstrap().then((payload) => setVisibility(payload.settings.overlayVisibility)).catch(() => undefined);
    let unlisten: (() => void) | undefined;
    listenEngine(handleEngineEvent).then((fn) => { unlisten = fn; });
    return () => unlisten?.();
  }, [handleEngineEvent]);

  useEffect(() => {
    if (!('__TAURI_INTERNALS__' in window)) return;
    const overlay = getCurrentWindow();
    const shouldShow = visibility === 'always' || status === 'recording' || status === 'transcribing' || status === 'cleaning' || status === 'success' || status === 'error';
    if (shouldShow) overlay.show().catch(() => undefined);
    else overlay.hide().catch(() => undefined);
  }, [status, visibility]);

  const label = useMemo(() => {
    if (status === 'recording') return 'Listening';
    if (status === 'transcribing') return 'Transcribing';
    if (status === 'cleaning') return 'Cleaning';
    if (status === 'success') return 'Done';
    if (status === 'error') return 'Error';
    return 'Ready';
  }, [status]);

  return (
    <main className={`overlay-root overlay-${status ?? 'idle'}`} data-tauri-drag-region>
      <div className="overlay-inner" data-tauri-drag-region>
        <span className="overlay-state-icon" data-tauri-drag-region>
          {status === 'success' ? <Check size={14} /> :
            status === 'error' ? <TriangleAlert size={14} /> :
            status === 'transcribing' || status === 'cleaning' ? <LoaderCircle size={14} className="spin" /> :
            <Mic2 size={14} />}
        </span>
        {status === 'recording' ? (
          <Waveform values={waveform} compact tone="recording" />
        ) : status === 'transcribing' ? (
          <div className="processing-line"><i /><i /><i /><i /><i /></div>
        ) : status === 'cleaning' ? (
          <div className="processing-line cleaning"><i /><i /><i /><i /><i /></div>
        ) : (
          <span className="overlay-label">{label}</span>
        )}
      </div>
    </main>
  );
}
