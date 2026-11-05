import { useEffect, useState } from "react";
import { Download, RefreshCw, Trash2 } from "lucide-react";
import { request } from "../lib/backend";
import { useApp } from "../store";
import { Button, Modal, Toggle } from "./ui";

interface Model {
  id: string; name: string; engine: string; languages: string[];
  installed: boolean; selected: boolean; compatible: boolean;
  hasFiles?: boolean;
  ownership: "owned" | "shared" | null; downloadBytes: number; diskBytes: number;
  license: string; ram_mb?: number; performance?: string;
  measurement?: { peakRamMb?: number; lastFinishSeconds?: number };
}
interface Library {
  models: Model[];
  operation: { state: string; id?: string; completed?: number; total?: number; error?: string; freedBytes?: number };
  catalogVersion: number;
  storageWarning?: string;
}
interface CatalogStatus { enabled: boolean; last_checked: number; message: string }
export const diskSize = (bytes: number) =>
  bytes < 1024 ** 3 ? `${(bytes / 1024 ** 2).toFixed(0)} MB` : `${(bytes / 1024 ** 3).toFixed(2)} GB`;

export function ModelLibrary() {
  const working = useApp((s) => s.runtime?.working ?? false);
  const preparing = useApp((s) => s.runtime?.status === "loading model");
  const selected = useApp((s) => s.settings?.selected_model_id);
  const [library, setLibrary] = useState<Library | null>(null);
  const [catalog, setCatalog] = useState<CatalogStatus | null>(null);
  const [filter, setFilter] = useState("available");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [removing, setRemoving] = useState<Model | null>(null);
  const [sharedConfirmed, setSharedConfirmed] = useState(false);
  useEffect(() => {
    let closed = false;
    const load = async () => {
      try {
        const [state, status] = await Promise.all([
          request<Library>("models.list"), request<CatalogStatus>("models.catalog.status"),
        ]);
        if (!closed) { setLibrary(state); setCatalog(status); }
      } catch (cause) { if (!closed) setError(String(cause).replace(/^Error: /, "")); }
    };
    void load();
    const timer = setInterval(() => void load(), 1000);
    return () => { closed = true; clearInterval(timer); };
  }, []);
  async function run(method: string, params: Record<string, unknown> = {}) {
    setPending(true); setError("");
    try {
      const result = await request<CatalogStatus>(method, params);
      if (method === "models.refresh" || method === "models.preferences") setCatalog(result);
      setLibrary(await request<Library>("models.list"));
      return true;
    } catch (cause) { setError(String(cause).replace(/^Error: /, "")); return false; }
    finally { setPending(false); }
  }
  const operation = library?.operation;
  const downloading = ["downloading", "paused", "cancelling"].includes(operation?.state ?? "");
  return (
    <section className="settings-section model-library" aria-labelledby="model-library-title">
      <div className="section-actions">
        <div><h2 id="model-library-title">Models</h2><p className="muted">Download the speech models you want. Delete unused models to recover disk space.</p></div>
        <Button disabled={pending || downloading} onClick={() => void run("models.refresh", { manual: true })}><RefreshCw size={16} />Refresh list</Button>
      </div>
      <div className="button-row" role="group" aria-label="Show models">
        <Button aria-pressed={filter === "available"} onClick={() => setFilter("available")}>Available</Button>
        <Button aria-pressed={filter === "installed"} onClick={() => setFilter("installed")}>Installed</Button>
      </div>
      {selected === "none" && <p role="status">No model selected. Download a model, then choose Use model to enable dictation.</p>}
      {preparing && <p role="status">Preparing the selected model and microphone…</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {library?.storageWarning && <p role="status">{library.storageWarning}</p>}
      {catalog?.message && <p className="muted" role="status">{catalog.message}</p>}
      {operation && downloading && <div className="model-progress" role="status">
        <span>{operation.state === "cancelling" ? "Stopping download…" : operation.state === "paused" ? "Download paused while dictating" : "Downloading model"} · {diskSize(operation.completed ?? 0)} of {diskSize(operation.total ?? 0)}</span>
        <progress value={operation.completed ?? 0} max={operation.total || 1} aria-label="Model download progress" />
        <Button onClick={() => void run("models.cancel")} disabled={pending || operation.state === "cancelling"}>Cancel download</Button>
      </div>}
      {operation?.state === "error" && <p className="form-error" role="alert">{operation.error} Select Download to retry, or Delete partial download to reclaim its space.</p>}
      {operation?.state === "cancelled" && <p role="status">Download cancelled. Select Download to resume, or delete the partial download.</p>}
      {operation?.state === "deleted" && <p role="status">Deleted model files. Recovered {diskSize(operation.freedBytes ?? 0)}.</p>}
      {!library && !error && <p role="status">Loading model library…</p>}
      <ul className="model-list">
        {library?.models.filter((model) => filter === "available" || model.installed).map((model) => <li key={model.id}>
          <div className="model-description">
            <strong>{model.name}{model.selected ? " · Selected" : ""}</strong>
            <p className="muted">{model.installed ? `${diskSize(model.diskBytes)} on disk` : model.hasFiles ? `${diskSize(model.diskBytes)} incomplete files · ${diskSize(model.downloadBytes)} full download` : `${diskSize(model.downloadBytes)} download`} · {model.languages.join(", ")} · {model.license}</p>
            <small className="muted">{model.measurement?.peakRamMb ? `Peak worker RAM on this device: ${model.measurement.peakRamMb} MB` : model.ram_mb ? `Estimated RAM: ${model.ram_mb} MB` : "RAM not measured"} · {model.measurement?.lastFinishSeconds !== undefined ? `Last transcript finished in ${model.measurement.lastFinishSeconds}s` : model.performance ?? "Performance not measured"}{model.ownership === "shared" ? " · Shared cache" : ""}</small>
          </div>
          <div className="button-row">
            {!model.compatible ? <span className="muted">App update required</span> : model.installed ?
              <Button disabled={working || pending} onClick={() => void run("models.select", { id: model.id })}>{model.selected ? "Prepare model" : "Use model"}</Button> :
              <Button disabled={pending || downloading} onClick={() => void run("models.download", { id: model.id })}><Download size={15} />Download</Button>}
            {(model.installed || model.hasFiles || (operation?.id === model.id && ["error", "cancelled"].includes(operation.state))) && <Button tone="ghost" disabled={pending || working || downloading} onClick={() => { setRemoving(model); setSharedConfirmed(false); }}><Trash2 size={15} />{model.installed ? "Delete" : "Delete partial download"}</Button>}
          </div>
        </li>)}
      </ul>
      {library && filter === "installed" && !library.models.some((model) => model.installed) && <p>No models installed. Open Available to download one.</p>}
      {catalog && <Toggle label="Check for new supported models automatically" hint="Checks the list at most once a day. Models download only when you choose Download." checked={catalog.enabled} disabled={pending} onChange={(enabled) => void run("models.preferences", { enabled })} />}
      <Modal open={!!removing} onClose={() => setRemoving(null)} title={`Delete ${removing?.name ?? "model"}?`} description={`This removes downloaded files${removing?.installed ? ` and recovers up to ${diskSize(removing.diskBytes)}` : ""}. The model stays available to download again.`}>
        {removing?.selected && <p>This is your selected model. Dictation will pause until you prepare another model.</p>}
        {removing?.ownership === "shared" && <Toggle label="Remove these shared cached files" hint="Other apps using this exact cached model may need to download it again." checked={sharedConfirmed} onChange={setSharedConfirmed} />}
        <div className="button-row"><Button onClick={() => setRemoving(null)} disabled={pending}>Keep model</Button><Button tone="danger" disabled={pending || (removing?.ownership === "shared" && !sharedConfirmed)} onClick={async () => {
          if (removing && await run("models.delete", { id: removing.id, allowShared: sharedConfirmed })) setRemoving(null);
        }}>Delete model files</Button></div>
      </Modal>
    </section>
  );
}
