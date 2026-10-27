import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Check,
  Copy,
  Cpu,
  History,
  Mic,
  Square,
  X,
} from "lucide-react";
import { isNative, native, navigate, request } from "../lib/backend";
import { countdown, hotkeyName } from "../lib/format";
import { notify, useApp } from "../store";
import { statusLabels } from "../types";
import { Button, Field, Modal, useAction } from "../components/ui";
import { Waveform } from "../components/Waveform";

export function DictationPage() {
  const runtime = useApp((s) => s.runtime)!,
    settings = useApp((s) => s.settings)!,
    meter = useApp((s) => s.meter);
  const action = useAction();
  const [microphones, setMicrophones] = useState<string[]>([]);
  useEffect(() => {
    request<string[]>("microphone.list")
      .then(setMicrophones)
      .catch(() => undefined);
  }, []);
  const engine =
    settings.backend === "whisper"
      ? `Whisper ${settings.model}`
      : {
          moonshine: `Moonshine ${settings.streaming_model}`,
          parakeet: "Parakeet English",
          nemotron: "Nemotron streaming",
        }[settings.backend];
  const previewValues = [
    0.2, 0.45, 0.6, 0.25, 0.8, 0.52, 0.3, 0.9, 0.65, 0.28, 0.75, 0.45, 0.2, 0.4,
    0.6, 0.38, 0.17, 0.3, 0.2, 0.1, 0.15, 0.08, 0.12, 0.06, 0.03, 0.04, 0.02, 0,
    0, 0, 0, 0,
  ];
  return (
    <section aria-labelledby="page-title">
      <header className="page-heading">
        <h1 id="page-title">Dictation</h1>
        <span className="engine-name">
          <Cpu size={19} />
          {engine} · On this device
        </span>
      </header>
      <div className="recording-panel panel">
        <div className="status-row">
          <strong
            className={`session-label state-${runtime.status.replaceAll(" ", "-")}`}
            role="status"
          >
            <span className="status-dot" />
            {statusLabels[runtime.status]}
          </strong>
          <span className="numeric muted">
            {countdown(runtime.elapsedSeconds)} / 5:00
          </span>
        </div>
        <Waveform
          values={!isNative() && runtime.recording ? previewValues : meter}
          active={runtime.recording}
        />
        <p className="shortcut-copy">
          {settings.recording_mode === "ptt" ? (
            <>
              Hold <kbd>{hotkeyName(settings.hotkey)}</kbd> to speak. Release to
              paste.
            </>
          ) : (
            <>
              Press <kbd>{hotkeyName(settings.hotkey)}</kbd> to start or finish
              recording.
            </>
          )}
        </p>
        <div className="recording-controls">
          <label className="microphone-select">
            <Mic size={18} />
            <span className="sr-only">Microphone</span>
            <select
              aria-label="Microphone"
              value={settings.microphone}
              disabled={runtime.working || action.pending}
              onChange={(e) =>
                void action.run("settings.save", {
                  settings: { microphone: e.target.value },
                })
              }
            >
              <option value="">Windows default</option>
              {Array.from(new Set([settings.microphone, ...microphones]))
                .filter(Boolean)
                .map((name) => (
                  <option key={name}>{name}</option>
                ))}
            </select>
          </label>
          <div className="button-row">
            {runtime.recording ? (
              <Button
                tone="primary"
                disabled={action.pending}
                onClick={() => void action.run("record.stop")}
              >
                <Square size={15} />
                Finish recording
              </Button>
            ) : !runtime.ready ? (
              <Button
                tone="primary"
                disabled={runtime.working || action.pending}
                onClick={() => void action.run("prepare")}
              >
                Prepare model and microphone
              </Button>
            ) : (
              <Button
                tone="primary"
                disabled={runtime.working || action.pending}
                onClick={() => void action.run("record.start")}
              >
                <Mic size={16} />
                Start recording
              </Button>
            )}
            <Button
              disabled={!runtime.working || action.pending}
              onClick={() => void action.run("record.cancel")}
            >
              <X size={16} />
              Cancel
            </Button>
          </div>
        </div>
        {runtime.working && !runtime.recording && (
          <div className="preparation">
            <progress aria-label="Preparation or recognition progress" />
            <span>{runtime.detail}</span>
          </div>
        )}
      </div>
      {runtime.error && (
        <div className="notice danger" role="alert">
          <AlertTriangle size={18} />
          <div>
            <strong>Something needs attention</strong>
            <p>{runtime.error}</p>
          </div>
          {runtime.failedAudio && (
            <>
              <Button
                disabled={runtime.working || action.pending}
                onClick={() => void action.run("record.retry")}
              >
                Retry recording
              </Button>
              <Button
                disabled={runtime.working || action.pending}
                onClick={() => void action.run("record.discard")}
              >
                Discard
              </Button>
            </>
          )}
        </div>
      )}
      <div className="transcript-panel panel">
        <h2>Latest transcript</h2>
        <div
          className="transcript-text"
          tabIndex={0}
          aria-label="Latest transcript"
        >
          {runtime.latestText || (
            <span className="muted">
              Your completed words will appear here.
            </span>
          )}
        </div>
        {runtime.insertionStatus === "copy" && runtime.latestText && (
          <div className="notice warning">
            <AlertTriangle size={18} />
            <span>
              {runtime.detail.includes("active window changed")
                ? "Destination changed. Text will be ready to copy."
                : "Your text is ready. Use Copy to insert it where you want."}
            </span>
          </div>
        )}
        <div className="button-row">
          <Button
            tone="primary"
            disabled={!runtime.latestText || action.pending}
            onClick={async () => {
              if (
                await action.run("clipboard.copy", { text: runtime.latestText })
              )
                notify("Text copied.");
            }}
          >
            <Copy size={17} />
            Copy
          </Button>
          <Button onClick={() => navigate("History")}>
            <History size={17} />
            Open history
          </Button>
          {runtime.insertionStatus === "pasted" && (
            <span className="success-copy">
              <Check size={16} />
              Text pasted
            </span>
          )}
        </div>
      </div>
      <p className="page-footnote">
        {!runtime.working && !runtime.error
          ? runtime.detail
          : "Audio stays on this device. Cloud cleanup runs only when you enable it."}
      </p>
    </section>
  );
}

export function Onboarding() {
  const settings = useApp((s) => s.settings),
    runtime = useApp((s) => s.runtime);
  const action = useAction();
  const [open, setOpen] = useState(true);
  if (!settings || !runtime || settings.onboarding_completed) return null;
  return (
    <Modal
      open={open}
      onClose={() => setOpen(false)}
      title="Welcome to VoicePrompt"
      description="A quick check gets voice typing ready on this computer."
    >
      <ol className="onboarding-steps">
        <li>
          <strong>Check your microphone</strong>
          <p>
            Use your Windows default input, or select another microphone on
            Dictation.
          </p>
          <Button
            disabled={runtime.working || action.pending}
            onClick={() => void action.run("microphone.check")}
          >
            Check microphone
          </Button>
        </li>
        <li>
          <strong>Prepare your local speech model</strong>
          <p>
            The first preparation downloads the selected model. Cached models
            work offline.
          </p>
          <Button
            disabled={runtime.working || action.pending}
            onClick={() => void action.run("prepare")}
          >
            Prepare model
          </Button>
        </li>
        <li>
          <strong>Try your shortcut</strong>
          <p>
            Put the cursor in a text editor. Hold{" "}
            <kbd>{hotkeyName(settings.hotkey)}</kbd>, speak, and release.
          </p>
        </li>
      </ol>
      <p role="status">{runtime.error || runtime.detail}</p>
      <div className="button-row">
        <Button
          tone="primary"
          disabled={!runtime.ready || action.pending}
          onClick={async () => {
            if (
              await action.run("settings.save", {
                settings: { onboarding_completed: true },
              })
            )
              setOpen(false);
          }}
        >
          Finish setup
        </Button>
        <Button
          onClick={() => {
            setOpen(false);
            void native("open_main");
          }}
        >
          Continue setup later
        </Button>
      </div>
    </Modal>
  );
}
