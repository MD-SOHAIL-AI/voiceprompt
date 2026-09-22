import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Activity, AudioLines, BarChart3, Check, ChevronDown, CircleDollarSign, Cloud, Copy,
  Cpu, Gauge, History, Home, KeyRound, Layers3, Mic2, PlugZap, Search, Settings,
  ShieldCheck, Sparkles, Trash2, WandSparkles, X,
} from 'lucide-react';
import { Waveform } from './components/Waveform';
import {
  applyEngineProfile, bootstrap, clearHistory, deleteHistory, getAccuracyScores, getHistory,
  listModels, listProviders, listenEngine, removeProviderCredential, saveProviderCredential,
  saveSettings, scoreHistory, setOverlayVisible, testProvider,
} from './lib/backend';
import { useAppStore } from './store';
import type {
  AccuracyScore, AppSettings, BillingTier, EngineProfile, ModelDescriptor, NavItem,
  ProviderDescriptor, TranscriptRecord,
} from './types';

const navItems: Array<{ id: NavItem; label: string; icon: typeof Home }> = [
  { id: 'home', label: 'Home', icon: Home },
  { id: 'history', label: 'History', icon: History },
  { id: 'models', label: 'Models', icon: Layers3 },
  { id: 'providers', label: 'Providers', icon: PlugZap },
  { id: 'performance', label: 'Performance', icon: BarChart3 },
  { id: 'dictionary', label: 'Dictionary', icon: WandSparkles },
  { id: 'settings', label: 'Settings', icon: Settings },
];

const fmtMs = (ms: number) => ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`;
const fmtTime = (iso: string) => new Intl.DateTimeFormat([], { hour: '2-digit', minute: '2-digit' }).format(new Date(iso));
const providerName = (items: ProviderDescriptor[], id: string) => items.find((item) => item.id === id)?.name ?? id;

export default function App() {
  const [nav, setNav] = useState<NavItem>('home');
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<string | null>(null);
  const hydrate = useAppStore((s) => s.hydrate);
  const ready = useAppStore((s) => s.ready);
  const handleEngineEvent = useAppStore((s) => s.handleEngineEvent);

  useEffect(() => {
    bootstrap().then(async (payload) => {
      hydrate(payload);
      await applyEngineProfile(toEngineProfile(payload.settings)).catch(() => undefined);
      await setOverlayVisible(payload.settings.overlayEnabled).catch(() => undefined);
    }).finally(() => setLoading(false));
    let unlisten: (() => void) | undefined;
    listenEngine(handleEngineEvent).then((dispose) => { unlisten = dispose; });
    return () => unlisten?.();
  }, [hydrate, handleEngineEvent]);

  const notify = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(null), 2300);
  };

  if (loading || !ready) return <div className="app-loader"><AudioLines size={26}/><span>Starting Voice Prompt…</span></div>;

  return <div className="app-shell">
    <Sidebar active={nav} onChange={setNav}/>
    <main className="app-content">
      <Topbar active={nav}/>
      <div className="page-wrap">
        <AnimatePresence mode="wait">
          <motion.div key={nav} initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: .14 }}>
            {nav === 'home' && <HomePage onNavigate={setNav}/>} 
            {nav === 'history' && <HistoryPage notify={notify}/>} 
            {nav === 'models' && <ModelsPage notify={notify}/>} 
            {nav === 'providers' && <ProvidersPage notify={notify}/>} 
            {nav === 'performance' && <PerformancePage/>} 
            {nav === 'dictionary' && <DictionaryPage notify={notify}/>} 
            {nav === 'settings' && <SettingsPage notify={notify}/>} 
          </motion.div>
        </AnimatePresence>
      </div>
    </main>
    <AnimatePresence>{toast && <motion.div className="toast" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}><Check size={14}/>{toast}</motion.div>}</AnimatePresence>
  </div>;
}

function Sidebar({ active, onChange }: { active: NavItem; onChange: (item: NavItem) => void }) {
  return <aside className="sidebar">
    <div className="brand"><div className="brand-wave"><i/><i/><i/><i/><i/></div><div><strong>Voice Prompt</strong><span>Desktop</span></div></div>
    <nav>{navItems.map(({ id, label, icon: Icon }) => <button key={id} className={active === id ? 'active' : ''} onClick={() => onChange(id)}><Icon size={17}/><span>{label}</span></button>)}</nav>
    <div className="sidebar-foot"><span><ShieldCheck size={14}/>Local-first</span><small>v2.0 alpha</small></div>
  </aside>;
}

function Topbar({ active }: { active: NavItem }) {
  const status = useAppStore((s) => s.status) ?? 'idle';
  const title = navItems.find((item) => item.id === active)?.label ?? 'Voice Prompt';
  return <header className="topbar" data-tauri-drag-region>
    <div data-tauri-drag-region><h1>{title}</h1><p>{active === 'home' ? 'Local-first dictation with cloud when you choose it.' : 'Voice Prompt'}</p></div>
    <span className={`status-chip ${status}`}><i/>{status === 'idle' ? 'Ready' : status === 'recording' ? 'Listening' : status}</span>
  </header>;
}

function HomePage({ onNavigate }: { onNavigate: (item: NavItem) => void }) {
  const settings = useAppStore((s) => s.settings)!;
  const providers = useAppStore((s) => s.providers);
  const metrics = useAppStore((s) => s.metrics)!;
  const recent = useAppStore((s) => s.recent);
  const waveform = useAppStore((s) => s.waveform);
  const status = useAppStore((s) => s.status) ?? 'idle';
  const [models, setModels] = useState<ModelDescriptor[]>([]);

  useEffect(() => { listModels(settings.transcriptionProvider).then(setModels).catch(() => setModels([])); }, [settings.transcriptionProvider]);
  const save = usePersistSettings();

  return <div className="page-stack">
    <section className="panel hero-card">
      <div className="section-head"><div><span className="eyebrow"><Mic2 size={13}/>LIVE DICTATION</span><h2>{status === 'recording' ? 'Listening…' : status === 'transcribing' ? 'Transcribing…' : status === 'cleaning' ? 'Cleaning…' : 'Ready when you are'}</h2></div><span className="hotkey-badge">{settings.hotkey}</span></div>
      <div className="hero-wave"><Waveform values={waveform} active={status === 'recording'} tone={status === 'cleaning' ? 'cleaning' : status === 'transcribing' ? 'processing' : 'recording'}/></div>
      <p>Hold the hotkey, speak, release, and Voice Prompt safely returns the transcript to the window where you started.</p>
      <div className="selector-grid">
        <SelectField label="Mode" value={settings.engineMode} options={[['auto','Auto'],['local','Local'],['cloud','Cloud']]} onChange={(engineMode) => save({ engineMode: engineMode as AppSettings['engineMode'] })}/>
        <SelectField label="Provider" value={settings.transcriptionProvider} options={providers.filter((p) => p.supportsTranscription).map((p) => [p.id,p.name])} onChange={(transcriptionProvider) => save({ transcriptionProvider })}/>
        <SelectField label="Model" value={settings.transcriptionModel} options={Array.from(new Map([{ id: settings.transcriptionModel, name: settings.transcriptionModel } as ModelDescriptor, ...models].map((m) => [m.id,m])).values()).map((m) => [m.id,m.name])} onChange={(transcriptionModel) => save({ transcriptionModel })}/>
      </div>
    </section>

    <section className="metric-grid">
      <Metric icon={AudioLines} label="Prompts today" value={String(metrics.promptsToday)} detail={`${Math.round(metrics.audioTodayMs / 1000)} sec audio`}/>
      <Metric icon={Gauge} label="Average latency" value={fmtMs(metrics.avgLatencyMs)} detail={`P95 ${fmtMs(metrics.p95LatencyMs)}`}/>
      <Metric icon={Cpu} label="Local share" value={`${metrics.localShare}%`} detail="On-device sessions"/>
      <Metric icon={Activity} label="Fastest route" value={metrics.fastestProvider ?? '—'} detail="Measured on this PC"/>
    </section>

    <div className="two-column">
      <section className="panel"><SectionHead eyebrow="RECENT" title="Latest prompts" action={<button className="text-button" onClick={() => onNavigate('history')}>View all</button>}/><div className="history-list">{recent.slice(0,4).map((record) => <HistoryRow key={record.id} record={record}/>)}{!recent.length && <Empty title="No history saved" body="History is private and off by default. Enable it in Settings if you want it."/>}</div></section>
      <section className="panel pipeline-card"><SectionHead eyebrow="PIPELINE" title="Current route"/><Pipeline label="Capture" detail="Push-to-talk" icon={Mic2}/><Pipeline label={providerName(providers, settings.transcriptionProvider)} detail={settings.transcriptionModel} icon={settings.transcriptionProvider === 'local' ? Cpu : Cloud}/><Pipeline label="Cleanup" detail={settings.cleanupEnabled ? `${settings.cleanupProvider} · ${settings.cleanupModel}` : 'Disabled'} icon={Sparkles}/></section>
    </div>
  </div>;
}

function HistoryPage({ notify }: { notify: (message: string) => void }) {
  const recent = useAppStore((s) => s.recent);
  const setRecent = useAppStore((s) => s.setRecent);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<TranscriptRecord | null>(recent[0] ?? null);

  useEffect(() => { getHistory(query, 250).then((items) => { setRecent(items); setSelected((current) => items.find((x) => x.id === current?.id) ?? items[0] ?? null); }); }, [query, setRecent]);
  const remove = async (id: string) => { await deleteHistory(id); const next = recent.filter((x) => x.id !== id); setRecent(next); setSelected(next[0] ?? null); notify('History item deleted'); };
  const clear = async () => { await clearHistory(); setRecent([]); setSelected(null); notify('Local history cleared'); };

  return <div className="history-layout">
    <section className="panel history-browser"><SectionHead eyebrow="LOCAL SQLITE" title="Prompt history" action={<button className="icon-button danger" onClick={clear}><Trash2 size={15}/></button>}/><div className="search-box"><Search size={15}/><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search transcript, provider or model"/></div><div className="history-list scroll-list">{recent.map((record) => <button className={`history-select ${selected?.id === record.id ? 'selected' : ''}`} key={record.id} onClick={() => setSelected(record)}><HistoryRow record={record}/></button>)}{!recent.length && <Empty title="Nothing here" body="Enable local history in Settings to retain prompt records."/>}</div></section>
    <section className="panel history-detail">{selected ? <HistoryDetail record={selected} onDelete={() => remove(selected.id)} notify={notify}/> : <Empty title="Select a prompt" body="Timing, provider, model and cost details appear here."/>}</section>
  </div>;
}

function ModelsPage({ notify }: { notify: (message: string) => void }) {
  const settings = useAppStore((s) => s.settings)!;
  const providers = useAppStore((s) => s.providers);
  const [purpose, setPurpose] = useState<'transcription'|'cleanup'>('transcription');
  const [provider, setProvider] = useState(settings.transcriptionProvider);
  const [models, setModels] = useState<ModelDescriptor[]>([]);
  const [filter, setFilter] = useState<BillingTier|'all'>('all');
  const save = usePersistSettings();

  useEffect(() => { listModels(provider, purpose).then(setModels).catch(() => setModels([])); }, [provider, purpose]);
  useEffect(() => {
    const allowed = providers.filter((p) => purpose === 'transcription' ? p.supportsTranscription : p.supportsCleanup);
    if (!allowed.some((p) => p.id === provider)) setProvider(allowed[0]?.id ?? 'local');
  }, [providers, provider, purpose]);

  const visible = models.filter((m) => filter === 'all' || m.billing === filter);
  const select = async (model: ModelDescriptor) => {
    if (purpose === 'transcription') await save({ transcriptionProvider: model.provider, transcriptionModel: model.id });
    else await save({ cleanupEnabled: true, cleanupProvider: model.provider, cleanupModel: model.id });
    notify(`${model.name} selected`);
  };
  const selected = purpose === 'transcription' ? settings.transcriptionModel : settings.cleanupModel;
  const allowedProviders = providers.filter((p) => purpose === 'transcription' ? p.supportsTranscription : p.supportsCleanup);

  return <div className="page-stack">
    <section className="page-intro"><div><span className="eyebrow">MODEL ROUTER</span><h2>Choose exactly how Voice Prompt runs</h2><p>Catalogs are fetched from the selected provider. Billing is labeled only when the provider exposes enough information to do it safely.</p></div></section>
    <section className="panel toolbar"><Segment value={purpose} options={[['transcription','Transcription'],['cleanup','AI cleanup']]} onChange={(v) => setPurpose(v as typeof purpose)}/><SelectInline value={provider} options={allowedProviders.map((p) => p.id)} onChange={setProvider}/><div className="filter-row">{(['all','free','paid','quota','local'] as const).map((value) => <button key={value} className={filter === value ? 'active' : ''} onClick={() => setFilter(value)}>{value === 'quota' ? 'Provider quota' : value}</button>)}</div></section>
    <section className="model-grid">{visible.map((model) => <ModelCard key={model.id} model={model} selected={selected === model.id} onSelect={() => select(model)}/>)}{!visible.length && <div className="panel"><Empty title="No matching models" body="Connect the provider or change the billing filter."/></div>}</section>
  </div>;
}

function ProvidersPage({ notify }: { notify: (message: string) => void }) {
  const providers = useAppStore((s) => s.providers);
  const setProviders = useAppStore((s) => s.setProviders);
  const [active, setActive] = useState<ProviderDescriptor | null>(null);
  const refresh = () => listProviders().then(setProviders);
  const disconnect = async (provider: ProviderDescriptor) => { await removeProviderCredential(provider.id); await refresh(); notify(`${provider.name} disconnected`); };

  return <div className="page-stack">
    <section className="page-intro"><div><span className="eyebrow">CONNECTIONS</span><h2>Providers</h2><p>Cloud keys are kept in the operating-system credential vault. Saved secrets are never returned to the React UI.</p></div></section>
    <section className="provider-grid">{providers.map((provider) => <article className="panel provider-card" key={provider.id}><div className="provider-icon">{provider.kind === 'local' ? <Cpu size={20}/> : <Cloud size={20}/>}</div><div className="provider-body"><div className="provider-title"><h3>{provider.name}</h3><span className={`connection-dot ${provider.connected ? 'connected' : ''}`}>{provider.connected ? 'Connected' : 'Not connected'}</span></div><p>{provider.description}</p><div className="capability-row">{provider.supportsTranscription && <span>Transcription</span>}{provider.supportsCleanup && <span>Cleanup</span>}</div></div><div className="provider-actions">{provider.configurable && <button className="secondary-button" onClick={() => setActive(provider)}>{provider.connected ? 'Manage' : 'Connect'}</button>}{provider.connected && provider.kind !== 'local' && <button className="icon-button danger" onClick={() => disconnect(provider)}><Trash2 size={15}/></button>}</div></article>)}</section>
    <ProviderModal provider={active} onClose={() => setActive(null)} onSaved={async (message) => { await refresh(); setActive(null); notify(message); }}/>
  </div>;
}

function PerformancePage() {
  const metrics = useAppStore((s) => s.metrics)!;
  const history = useAppStore((s) => s.recent);
  const [scores, setScores] = useState<AccuracyScore[]>([]);
  const [recordId, setRecordId] = useState(history[0]?.id ?? '');
  const [reference, setReference] = useState('');
  useEffect(() => { getAccuracyScores().then(setScores).catch(() => undefined); }, []);
  const runScore = async () => { if (!recordId || !reference.trim()) return; const score = await scoreHistory(recordId, reference.trim()); setScores((items) => [score, ...items.filter((x) => x.recordId !== score.recordId)]); };
  const recentLatencies = history.slice(0, 18).reverse().map((x) => x.totalMs);

  return <div className="page-stack">
    <section className="metric-grid"><Metric icon={Gauge} label="Average" value={fmtMs(metrics.avgLatencyMs)} detail="End-to-end"/><Metric icon={Activity} label="P95" value={fmtMs(metrics.p95LatencyMs)} detail="Tail latency"/><Metric icon={Cpu} label="Local share" value={`${metrics.localShare}%`} detail="Private sessions"/><Metric icon={Cloud} label="Fastest" value={metrics.fastestProvider ?? '—'} detail="Measured route"/></section>
    <section className="panel"><SectionHead eyebrow="LATENCY" title="Recent sessions"/><LatencyChart values={recentLatencies}/></section>
    <div className="two-column"><section className="panel"><SectionHead eyebrow="ACCURACY" title="WER / CER benchmark"/><p className="muted-block">Accuracy is measured only when you provide the known reference transcript. Voice Prompt does not invent confidence percentages.</p><SelectInline value={recordId} options={history.map((x) => x.id)} onChange={setRecordId}/><textarea className="reference-input" value={reference} onChange={(e) => setReference(e.target.value)} placeholder="Paste the exact reference transcript…"/><button className="primary-button" onClick={runScore}>Score transcript</button></section><section className="panel"><SectionHead eyebrow="MEASURED" title="Accuracy results"/><div className="score-list">{scores.slice(0,8).map((score) => <div key={score.recordId}><div><strong>{score.provider}</strong><span>{score.model}</span></div><b>WER {(score.wer*100).toFixed(1)}%</b><b>CER {(score.cer*100).toFixed(1)}%</b></div>)}{!scores.length && <Empty title="No measured scores" body="Score a saved prompt against a reference transcript."/>}</div></section></div>
  </div>;
}

function DictionaryPage({ notify }: { notify: (message: string) => void }) {
  const settings = useAppStore((s) => s.settings)!;
  const save = usePersistSettings();
  const [source, setSource] = useState('');
  const [target, setTarget] = useState('');
  const entries = Object.entries(settings.customReplacements);
  const add = async () => { if (!source.trim() || !target.trim()) return; await save({ customReplacements: { ...settings.customReplacements, [source.trim()]: target.trim() } }); setSource(''); setTarget(''); notify('Dictionary entry added'); };
  const remove = async (key: string) => { const next = { ...settings.customReplacements }; delete next[key]; await save({ customReplacements: next }); notify('Dictionary entry removed'); };

  return <div className="page-stack"><section className="page-intro"><div><span className="eyebrow">PERSONAL VOCABULARY</span><h2>Dictionary</h2><p>Correct product names, acronyms and technical terms after transcription.</p></div></section><section className="panel dictionary-add"><Field label="What ASR may hear"><input value={source} onChange={(e) => setSource(e.target.value)} placeholder="forge x"/></Field><span>→</span><Field label="Replace with"><input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="ForgeX"/></Field><button className="primary-button" onClick={add}>Add</button></section><section className="panel"><SectionHead eyebrow="ACTIVE" title={`${entries.length} replacements`}/><div className="dictionary-table">{entries.map(([from,to]) => <div key={from}><code>{from}</code><span>→</span><strong>{to}</strong><button className="icon-button" onClick={() => remove(from)}><Trash2 size={14}/></button></div>)}</div></section></div>;
}

function SettingsPage({ notify }: { notify: (message: string) => void }) {
  const settings = useAppStore((s) => s.settings)!;
  const providers = useAppStore((s) => s.providers);
  const [cleanupModels, setCleanupModels] = useState<ModelDescriptor[]>([]);
  const save = usePersistSettings();
  useEffect(() => { if (settings.cleanupEnabled) listModels(settings.cleanupProvider, 'cleanup').then(setCleanupModels).catch(() => setCleanupModels([])); else setCleanupModels([]); }, [settings.cleanupEnabled, settings.cleanupProvider]);
  const update = async (patch: Partial<AppSettings>) => { await save(patch); notify('Settings saved'); };

  return <div className="settings-layout">
    <SettingsSection eyebrow="INTERACTION" title="Dictation"><SettingRow title="Hotkey" detail="Push-to-talk shortcut"><SelectInline value={settings.hotkey} options={['Right Ctrl','Left Ctrl','F8','F9']} onChange={(hotkey) => update({hotkey})}/></SettingRow><SettingRow title="Recording mode" detail="Hold or toggle recording"><Segment value={settings.recordingMode} options={[['ptt','Push to talk'],['toggle','Toggle']]} onChange={(v) => update({ recordingMode: v as AppSettings['recordingMode'] })}/></SettingRow><SettingRow title="Sound feedback" detail="Audible start and stop cues"><Toggle checked={settings.soundFeedback} onChange={(soundFeedback) => update({soundFeedback})}/></SettingRow><SettingRow title="Auto paste" detail="Paste into the original target app"><Toggle checked={settings.autoPaste} onChange={(autoPaste) => update({autoPaste})}/></SettingRow><SettingRow title="Restore target focus" detail="Return focus safely before paste"><Toggle checked={settings.restoreTargetFocus} onChange={(restoreTargetFocus) => update({restoreTargetFocus})}/></SettingRow></SettingsSection>
    <SettingsSection eyebrow="FLOATING UI" title="Overlay"><SettingRow title="Floating overlay" detail="Always-on-top voice feedback"><Toggle checked={settings.overlayEnabled} onChange={(overlayEnabled) => update({overlayEnabled})}/></SettingRow><SettingRow title="Visibility" detail="When the capsule appears"><SelectInline value={settings.overlayVisibility} options={['always','recording','hidden-idle']} onChange={(v) => update({ overlayVisibility: v as AppSettings['overlayVisibility'] })}/></SettingRow><SettingRow title="Position" detail="Anchor it or remember dragged position"><SelectInline value={settings.overlayPosition} options={['remember','bottom-center','bottom-right','top-center']} onChange={(v) => update({ overlayPosition: v as AppSettings['overlayPosition'] })}/></SettingRow><SettingRow title="Size" detail="Compact is recommended"><Segment value={settings.overlaySize} options={[['compact','Compact'],['comfortable','Comfortable']]} onChange={(v) => update({ overlaySize: v as AppSettings['overlaySize'] })}/></SettingRow></SettingsSection>
    <SettingsSection eyebrow="PRIVACY" title="History & cloud"><SettingRow title="Save prompt history" detail="Off by default; stored locally in SQLite"><Toggle checked={settings.historyEnabled} onChange={(historyEnabled) => update({historyEnabled})}/></SettingRow><SettingRow title="Retention" detail="Automatically prune old records"><SelectInline value={String(settings.historyRetentionDays)} options={['7','30','90','365']} onChange={(v) => update({ historyRetentionDays: Number(v) })}/></SettingRow><SettingRow title="AI cleanup" detail="Optional text-only cleanup stage"><Toggle checked={settings.cleanupEnabled} onChange={(cleanupEnabled) => update({cleanupEnabled})}/></SettingRow>{settings.cleanupEnabled && <><SettingRow title="Cleanup provider" detail="Transcript text is sent only here"><SelectInline value={settings.cleanupProvider} options={providers.filter((p) => p.supportsCleanup).map((p) => p.id)} onChange={(cleanupProvider) => update({cleanupProvider})}/></SettingRow><SettingRow title="Cleanup model" detail="Fetched from the selected provider"><SelectInline value={settings.cleanupModel} options={Array.from(new Set([settings.cleanupModel,...cleanupModels.map((m) => m.id)]))} onChange={(cleanupModel) => update({cleanupModel})}/></SettingRow></>}</SettingsSection>
    <SettingsSection eyebrow="SYSTEM" title="Routing"><SettingRow title="Engine mode" detail="Auto falls back to local if cloud fails"><Segment value={settings.engineMode} options={[['auto','Auto'],['local','Local'],['cloud','Cloud']]} onChange={(v) => update({ engineMode: v as AppSettings['engineMode'] })}/></SettingRow><SettingRow title="Launch at startup" detail="Start when you sign in to Windows"><Toggle checked={settings.launchAtStartup} onChange={(launchAtStartup) => update({launchAtStartup})}/></SettingRow><SettingRow title="Language" detail="Automatic detection is recommended"><SelectInline value={settings.language} options={['auto','en','ta','hi','te','ml','kn']} onChange={(language) => update({language})}/></SettingRow></SettingsSection>
  </div>;
}

function ProviderModal({ provider, onClose, onSaved }: { provider: ProviderDescriptor | null; onClose: () => void; onSaved: (message: string) => void }) {
  const [apiKey, setApiKey] = useState(''); const [baseUrl, setBaseUrl] = useState(''); const [busy, setBusy] = useState(false); const [result, setResult] = useState('');
  useEffect(() => { setApiKey(''); setBaseUrl(provider?.baseUrl ?? ''); setResult(''); }, [provider]);
  if (!provider) return null;
  const persist = async (testOnly = false) => { setBusy(true); try { if (apiKey.trim()) await saveProviderCredential(provider.id, apiKey.trim(), baseUrl.trim() || undefined); const message = await testProvider(provider.id); setResult(message); if (!testOnly) onSaved(`${provider.name}: ${message}`); } catch (error) { setResult(String(error)); } finally { setBusy(false); } };
  return <div className="modal-backdrop" onMouseDown={onClose}><motion.div className="modal" initial={{ opacity: 0, scale: .98, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }} onMouseDown={(e) => e.stopPropagation()}><div className="modal-head"><div><span className="eyebrow">PROVIDER</span><h3>{provider.name}</h3></div><button className="icon-button" onClick={onClose}><X size={16}/></button></div><p className="security-note"><ShieldCheck size={15}/>API keys are stored in the OS credential vault and are never returned to this UI.</p><Field label={`API key${provider.connected ? ' · leave blank to keep existing' : ''}`}><input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={provider.connected ? '••••••••••••••' : 'Paste provider key'}/></Field>{provider.id === 'custom' && <Field label="Base URL"><input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.example.com/v1"/></Field>}{result && <div className="test-result">{result}</div>}<div className="modal-actions"><button className="secondary-button" disabled={busy} onClick={() => persist(true)}>Test</button><button className="primary-button" disabled={busy || (!apiKey.trim() && !provider.connected)} onClick={() => persist(false)}>{busy ? 'Working…' : 'Save provider'}</button></div></motion.div></div>;
}

function usePersistSettings() {
  const settings = useAppStore((s) => s.settings)!;
  const setSettings = useAppStore((s) => s.setSettings);
  return async (patch: Partial<AppSettings>) => {
    const next = { ...settings, ...patch };
    setSettings(next);
    await saveSettings(next);
    await applyEngineProfile(toEngineProfile(next)).catch(() => undefined);
    if ('overlayEnabled' in patch) await setOverlayVisible(next.overlayEnabled).catch(() => undefined);
  };
}

function ModelCard({ model, selected, onSelect }: { model: ModelDescriptor; selected: boolean; onSelect: () => void }) {
  return <article className={`panel model-card ${selected ? 'selected' : ''}`}><div className="model-top"><div className="provider-icon">{model.provider === 'local' ? <Cpu size={18}/> : <Cloud size={18}/>}</div><div><BillingBadge tier={model.billing}/>{model.recommended && <span className="tag recommended">Recommended</span>}</div></div><h3>{model.name}</h3><code>{model.id}</code><p>{model.description ?? 'Available from the live provider catalog.'}</p><div className="capability-row">{model.capabilities.slice(0,4).map((cap) => <span key={cap}>{cap}</span>)}</div><div className="model-foot"><span><CircleDollarSign size={14}/>{model.priceLabel ?? billingCopy(model.billing)}</span><button className={selected ? 'selected-button' : 'secondary-button'} onClick={onSelect}>{selected ? <><Check size={14}/>Selected</> : 'Use model'}</button></div></article>;
}

function HistoryRow({ record }: { record: TranscriptRecord }) { return <div className="history-row"><time>{fmtTime(record.createdAt)}</time><div><strong>{record.text}</strong><span>{record.provider} · {record.model} · {fmtMs(record.totalMs)}</span></div><em className={record.source}>{record.source}</em></div>; }
function HistoryDetail({ record, onDelete, notify }: { record: TranscriptRecord; onDelete: () => void; notify: (m:string) => void }) { const copy = () => navigator.clipboard.writeText(record.text).then(() => notify('Transcript copied')); return <><SectionHead eyebrow="TRANSCRIPT" title={new Date(record.createdAt).toLocaleString()} action={<div className="inline-actions"><button className="secondary-button" onClick={copy}><Copy size={14}/>Copy</button><button className="icon-button danger" onClick={onDelete}><Trash2 size={15}/></button></div>}/><div className="transcript-box">{record.text}</div><div className="detail-metrics"><Detail label="Audio" value={fmtMs(record.audioDurationMs)}/><Detail label="ASR" value={fmtMs(record.transcriptionMs)}/><Detail label="Cleanup" value={fmtMs(record.cleanupMs)}/><Detail label="Paste" value={fmtMs(record.pasteMs)}/><Detail label="Total" value={fmtMs(record.totalMs)}/><Detail label="Cost" value={record.costUsd ? `$${record.costUsd.toFixed(5)}` : '—'}/></div><div className="detail-table"><Detail label="Provider" value={record.provider}/><Detail label="Model" value={record.model}/><Detail label="Language" value={record.language || 'Auto'}/><Detail label="Target" value={record.targetApp || 'Unknown'}/></div></>; }
function LatencyChart({ values }: { values: number[] }) { if (!values.length) return <Empty title="No latency data" body="Measurements appear after saved sessions."/>; const max = Math.max(...values,1), width=760, height=210, pad=18, step=values.length>1?(width-pad*2)/(values.length-1):0; const points=values.map((v,i)=>`${pad+i*step},${height-pad-(v/max)*(height-pad*2)}`).join(' '); return <div className="chart"><svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none"><line x1={pad} x2={width-pad} y1={height-pad} y2={height-pad}/><polyline points={points} fill="none"/></svg></div>; }
function Metric({ icon: Icon, label, value, detail }: { icon: typeof Activity; label:string; value:string; detail:string }) { return <article className="panel metric-card"><span className="metric-icon"><Icon size={17}/></span><div><small>{label}</small><strong>{value}</strong><span>{detail}</span></div></article>; }
function Pipeline({ label, detail, icon: Icon }: { label:string; detail:string; icon: typeof Mic2 }) { return <div className="pipeline-row"><span><Icon size={16}/></span><div><strong>{label}</strong><small>{detail}</small></div></div>; }
function Detail({ label, value }: { label:string; value:string }) { return <div><span>{label}</span><strong>{value}</strong></div>; }
function Empty({ title, body }: { title:string; body:string }) { return <div className="empty"><AudioLines size={22}/><strong>{title}</strong><span>{body}</span></div>; }
function SectionHead({ eyebrow, title, action }: { eyebrow:string; title:string; action?:ReactNode }) { return <div className="section-head"><div><span className="eyebrow">{eyebrow}</span><h3>{title}</h3></div>{action}</div>; }
function SettingsSection({ eyebrow, title, children }: { eyebrow:string; title:string; children:ReactNode }) { return <section className="panel settings-section"><SectionHead eyebrow={eyebrow} title={title}/>{children}</section>; }
function SettingRow({ title, detail, children }: { title:string; detail:string; children:ReactNode }) { return <div className="setting-row"><div><strong>{title}</strong><span>{detail}</span></div>{children}</div>; }
function Field({ label, children }: { label:string; children:ReactNode }) { return <label className="field"><span>{label}</span>{children}</label>; }
function BillingBadge({ tier }: { tier: BillingTier }) { return <span className={`tag billing-${tier}`}>{tier === 'quota' ? 'Provider quota' : tier}</span>; }
function billingCopy(tier: BillingTier) { return tier === 'local' ? 'Free · on device' : tier === 'free' ? 'Free' : tier === 'paid' ? 'Paid' : 'Check provider'; }
function SelectField({ label, value, options, onChange }: { label:string; value:string; options:Array<[string,string]>; onChange:(v:string)=>void }) { return <label className="select-field"><span>{label}</span><div><select value={value} onChange={(e)=>onChange(e.target.value)}>{options.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select><ChevronDown size={14}/></div></label>; }
function SelectInline({ value, options, onChange }: { value:string; options:string[]; onChange:(v:string)=>void }) { return <div className="select-inline"><select value={value} onChange={(e)=>onChange(e.target.value)}>{options.map((v)=><option key={v} value={v}>{v}</option>)}</select><ChevronDown size={14}/></div>; }
function Segment({ value, options, onChange }: { value:string; options:Array<[string,string]>; onChange:(v:string)=>void }) { return <div className="segmented">{options.map(([v,l])=><button key={v} className={value===v?'active':''} onClick={()=>onChange(v)}>{l}</button>)}</div>; }
function Toggle({ checked, onChange }: { checked:boolean; onChange:(v:boolean)=>void }) { return <button className={`toggle ${checked?'on':''}`} onClick={()=>onChange(!checked)} aria-pressed={checked}><i/></button>; }

function toEngineProfile(settings: AppSettings): EngineProfile {
  return {
    engineMode: settings.engineMode, transcriptionProvider: settings.transcriptionProvider,
    transcriptionModel: settings.transcriptionModel, cleanupEnabled: settings.cleanupEnabled,
    cleanupProvider: settings.cleanupProvider, cleanupModel: settings.cleanupModel,
    language: settings.language, hotkey: settings.hotkey, recordingMode: settings.recordingMode,
    soundFeedback: settings.soundFeedback, autoPaste: settings.autoPaste,
    restoreTargetFocus: settings.restoreTargetFocus, customReplacements: settings.customReplacements,
  };
}
