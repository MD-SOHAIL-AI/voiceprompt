import { Download, RefreshCw, RotateCw } from "lucide-react";
import { Button, Toggle } from "./ui";
import { openLink } from "../lib/backend";
import { updateAction, useUpdates } from "../lib/updates";
import { notify } from "../store";

export function UpdateShortcut() {
  const status = useUpdates((state) => state.status);
  if (
    !status?.supported ||
    !status.version ||
    !["available", "downloading", "ready"].includes(status.phase)
  )
    return null;
  return (
    <Button
      className="update-shortcut"
      tone="ghost"
      disabled={status.phase === "downloading"}
      onClick={() =>
        void updateAction(
          status.phase === "ready" ? "update_install" : "update_download",
        )
      }
    >
      {status.phase === "ready" ? (
        <RotateCw size={14} />
      ) : (
        <Download size={14} />
      )}
      {status.phase === "ready"
        ? "Restart to update"
        : status.phase === "downloading"
          ? "Downloading update…"
          : "Update now"}
    </Button>
  );
}

export function Updates() {
  const status = useUpdates((state) => state.status);
  const busy =
    status?.phase === "checking" ||
    status?.phase === "downloading" ||
    status?.phase === "installing";
  const progress = status?.total
    ? Math.min(100, Math.round((status.downloaded / status.total) * 100))
    : 0;
  return (
    <section
      className="settings-section app-updates"
      aria-labelledby="updates-title"
    >
      <h2 id="updates-title">App updates</h2>
      <p className="muted">
        Installed version {status?.installedVersion ?? "…"}
        {status?.version ? ` · Version ${status.version} available` : ""}
      </p>
      <p role="status" aria-live="polite">
        {status?.message ||
          (status?.phase === "checking"
            ? "Checking for updates…"
            : status?.phase === "downloading"
              ? "Downloading update…"
              : "Check for the latest VoicePrompt release.")}
      </p>
      {status?.phase === "downloading" && (
        <div className="update-progress">
          <progress
            aria-label="Update download"
            value={status.downloaded}
            max={status.total || 1}
          />
          <span>
            {progress}% · {(status.downloaded / 1000000).toFixed(1)} /{" "}
            {(status.total / 1000000).toFixed(1)} MB
          </span>
        </div>
      )}
      <div className="button-row">
        <Button
          disabled={!status?.supported || busy}
          onClick={() => void updateAction("update_check")}
        >
          <RefreshCw size={15} />
          {status?.phase === "checking" ? "Checking…" : "Check for updates"}
        </Button>
        {status?.version && ["available", "error"].includes(status.phase) && (
          <Button
            tone="primary"
            onClick={() => void updateAction("update_download")}
          >
            <Download size={15} />
            {status.phase === "error" ? "Retry download" : "Update now"}
          </Button>
        )}
        {status?.phase === "downloading" && (
          <Button onClick={() => void updateAction("update_cancel")}>
            Cancel download
          </Button>
        )}
        {status?.phase === "ready" && (
          <>
            <Button
              tone="primary"
              onClick={() => void updateAction("update_install")}
            >
              <RotateCw size={15} />
              Restart to update
            </Button>
            <Button
              onClick={() =>
                notify(
                  "The update is saved. Choose Restart to update whenever you're ready.",
                )
              }
            >
              Later
            </Button>
          </>
        )}
      </div>
      {status?.phase === "ready" && (
        <p className="muted">
          VoicePrompt closes briefly to update. Save your changes first. Alarms
          and reminders resume when the app reopens.
        </p>
      )}
      {status?.supported && (
        <Toggle
          label="Check for updates automatically"
          hint="Check on startup and every six hours. Downloads begin only when you choose Update now."
          checked={status.automatic}
          onChange={(automatic) =>
            void updateAction("update_preferences", { automatic })
          }
        />
      )}
      {status?.lastChecked && (
        <p className="muted">
          Last checked {new Date(status.lastChecked * 1000).toLocaleString()}
        </p>
      )}
      {status?.version && status.notes && (
        <details>
          <summary>What's new in {status.version}</summary>
          <p className="update-notes">{status.notes}</p>
        </details>
      )}
      <Button
        tone="ghost"
        onClick={() =>
          void openLink(
            "https://github.com/MD-SOHAIL-AI/voiceprompt/releases",
          ).catch((error) => notify(String(error)))
        }
      >
        View all releases
      </Button>
    </section>
  );
}
