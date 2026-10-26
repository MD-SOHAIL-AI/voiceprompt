import { useState } from "react";
import { ExternalLink, Save } from "lucide-react";
import { openLink, refresh } from "../lib/backend";
import { notify, useApp } from "../store";
import type { Settings } from "../types";
import { Button, Field, Toggle, useAction } from "../components/ui";

export function SettingsPage() {
  const saved = useApp((s) => s.settings)!,
    planner = useApp((s) => s.planner),
    credentials = useApp((s) => s.data?.credentials);
  const action = useAction();
  const [form, setForm] = useState<Settings>(() => structuredClone(saved)),
    [dictionary, setDictionary] = useState(() =>
      Object.entries(saved.replacements)
        .map(([from, to]) => `${from}=${to}`)
        .join("\n"),
    ),
    [zone, setZone] = useState(planner?.preferences.timezone ?? "Asia/Kolkata");
  const set = <K extends keyof Settings>(key: K, value: Settings[K]) =>
    setForm((previous) => ({ ...previous, [key]: value }));
  const select = <K extends keyof Settings>(
    key: K,
    label: string,
    options: [string, string][],
  ) => (
    <Field label={label}>
      <select
        value={String(form[key])}
        onChange={(e) => set(key, e.target.value as Settings[K])}
      >
        {options.map(([value, text]) => (
          <option value={value} key={value}>
            {text}
          </option>
        ))}
      </select>
    </Field>
  );
  async function save() {
    const replacements: Record<string, string> = {};
    for (const line of dictionary.split("\n").filter((line) => line.trim())) {
      const split = line.indexOf("=");
      if (split < 1 || !line.slice(split + 1).trim()) {
        notify("Use source=replacement on each dictionary line.");
        return;
      }
      replacements[line.slice(0, split).trim()] = line.slice(split + 1).trim();
    }
    if (
      planner &&
      zone !== planner.preferences.timezone &&
      !(await action.run("planner.preferences", { timezone: zone }))
    )
      return;
    if (
      await action.run("settings.save", { settings: { ...form, replacements } })
    )
      notify(
        "Settings queued. They apply after any current recording finishes.",
      );
  }
  return (
    <section>
      <header className="page-heading">
        <h1>Settings</h1>
        <Button
          tone="primary"
          disabled={action.pending}
          onClick={() => void save()}
        >
          <Save size={16} />
          Save settings
        </Button>
      </header>
      <div className="settings-sections">
        <section className="settings-section">
          <h2>Recording</h2>
          <div className="form-grid">
            {select("hotkey", "Recording key", [
              ["right_ctrl", "Right Ctrl"],
              ["left_ctrl", "Left Ctrl"],
              ["right_alt", "Right Alt"],
              ["left_alt", "Left Alt"],
              ["f8", "F8"],
              ["f9", "F9"],
            ])}
            {select("recording_mode", "Recording mode", [
              ["ptt", "Hold to talk"],
              ["toggle", "Press to start / stop"],
            ])}
          </div>
          <Field
            label="Microphone"
            hint="Leave blank to use your Windows default input."
          >
            <input
              value={form.microphone}
              onChange={(e) => set("microphone", e.target.value)}
            />
          </Field>
          <Toggle
            label="Play recording sounds"
            checked={form.sound_feedback}
            onChange={(value) => set("sound_feedback", value)}
          />
          <Toggle
            label="Prepare model when VoicePrompt opens"
            checked={form.preload_model}
            onChange={(value) => set("preload_model", value)}
          />
          <Toggle
            label="Start after Windows sign-in"
            checked={form.startup_on_boot}
            onChange={(value) => set("startup_on_boot", value)}
          />
          <Toggle
            label="Paste completed text automatically"
            checked={form.paste_injection}
            onChange={(value) => set("paste_injection", value)}
          />
          <Toggle
            label="Restore clipboard after automatic paste"
            checked={form.preserve_clipboard}
            onChange={(value) => set("preserve_clipboard", value)}
          />
        </section>
        <section className="settings-section">
          <h2>Local speech model</h2>
          {select("backend", "Recognition engine", [
            ["whisper", "Whisper"],
            ["moonshine", "Moonshine"],
            ["parakeet", "Parakeet"],
            ["nemotron", "Nemotron"],
          ])}
          <details>
            <summary>Advanced speech settings</summary>
            <div className="form-grid">
              <Field label="Whisper model">
                <input
                  value={form.model}
                  onChange={(e) => set("model", e.target.value)}
                />
              </Field>
              <Field label="Whisper language">
                <input
                  value={form.language}
                  onChange={(e) => set("language", e.target.value)}
                />
              </Field>
              {select("streaming_model", "Moonshine model", [
                ["tiny", "Tiny"],
                ["small", "Small"],
              ])}
              {select("nemotron_device", "Nemotron device", [
                ["vulkan", "Vulkan"],
                ["cpu", "CPU"],
              ])}
              {select("device", "Whisper device", [
                ["cpu", "CPU"],
                ["cuda", "CUDA"],
                ["auto", "Automatic"],
              ])}
              {select("compute_type", "Compute type", [
                ["int8", "INT8"],
                ["float16", "Float16"],
                ["float32", "Float32"],
                ["int8_float16", "INT8 / Float16"],
                ["auto", "Automatic"],
              ])}
              {select("capture_mode", "Capture host", [
                ["auto", "Automatic"],
                ["wasapi", "WASAPI"],
                ["mme", "MME"],
              ])}
              <Field label="CPU threads">
                <input
                  type="number"
                  min="1"
                  max="12"
                  value={form.cpu_threads}
                  onChange={(e) => set("cpu_threads", Number(e.target.value))}
                />
              </Field>
              <Field label="Beam size">
                <input
                  type="number"
                  min="1"
                  max="10"
                  value={form.beam_size}
                  onChange={(e) => set("beam_size", Number(e.target.value))}
                />
              </Field>
            </div>
            <Toggle
              label="Filter silence during recognition"
              checked={form.vad_filter}
              onChange={(value) => set("vad_filter", value)}
            />
            <Toggle
              label="RNNoise suppression"
              checked={form.noise_suppression}
              onChange={(value) => set("noise_suppression", value)}
            />
            <p className="muted">
              Moonshine, Parakeet, and Nemotron use English recognition.
              Existing downloaded models are preserved.
            </p>
          </details>
        </section>
        <section className="settings-section">
          <h2>History and dictionary</h2>
          <Field
            label="Saved transcripts"
            hint="0 disables future history. Existing transcripts can be cleared on History."
          >
            <input
              type="number"
              min="0"
              max="500"
              value={form.max_history}
              onChange={(e) => set("max_history", Number(e.target.value))}
            />
          </Field>
          <Field
            label="Custom dictionary"
            hint="One source=replacement pair per line. Names and terminology stay on this device."
          >
            <textarea
              className="dictionary-input"
              rows={6}
              value={dictionary}
              onChange={(e) => setDictionary(e.target.value)}
              spellCheck={false}
            />
          </Field>
        </section>
        <section className="settings-section">
          <h2>Alarms and reminders</h2>
          {planner && (
            <>
              <Field label="Time zone">
                <input
                  value={zone}
                  onChange={(e) => setZone(e.target.value)}
                  placeholder="Asia/Kolkata"
                />
              </Field>
              <Toggle
                label="Play reminder sounds"
                checked={planner.preferences.reminder_sound}
                disabled={action.pending}
                onChange={(value) =>
                  void action.run("planner.preferences", {
                    reminder_sound: value,
                  })
                }
              />
              <p className="muted">
                During dictation, the island shows a quiet badge. Reminder
                sounds wait until your recording and paste are finished.
              </p>
            </>
          )}
        </section>
        <section className="settings-section">
          <h2>Optional text cleanup</h2>
          {select("cleanup_provider", "Cleanup provider", [
            ["none", "Off · keep text on this device"],
            ["gemini", "Gemini"],
            ["openrouter", "OpenRouter"],
          ])}
          <p className="muted">
            Enabling cleanup sends completed transcript text to the selected
            provider. Audio stays on your computer.
          </p>
          <div className="form-grid">
            <Field label="Gemini model">
              <input
                value={form.gemini_model}
                onChange={(e) => set("gemini_model", e.target.value)}
              />
            </Field>
            <Field label="OpenRouter model">
              <input
                value={form.openrouter_model}
                onChange={(e) => set("openrouter_model", e.target.value)}
              />
            </Field>
            <Field label="Cleanup timeout (seconds)">
              <input
                type="number"
                min="1"
                max="15"
                step="0.5"
                value={form.cleanup_timeout_seconds}
                onChange={(e) =>
                  set("cleanup_timeout_seconds", Number(e.target.value))
                }
              />
            </Field>
          </div>
          <div className="credential-forms">
            {(["gemini", "openrouter"] as const).map((provider) => (
              <form
                key={provider}
                onSubmit={async (e) => {
                  e.preventDefault();
                  const element = e.currentTarget;
                  const fields = new FormData(element);
                  if (
                    await action.run("credential.save", {
                      provider,
                      key: fields.get("key"),
                    })
                  ) {
                    element.reset();
                    await refresh();
                    notify("Provider key saved in Windows Credential Manager.");
                  }
                }}
              >
                <Field
                  label={`${provider === "gemini" ? "Gemini" : "OpenRouter"} API key`}
                  hint={
                    credentials?.[provider]
                      ? "A key is available. Its value is never returned to this interface."
                      : "No key is available."
                  }
                >
                  <input
                    type="password"
                    name="key"
                    required
                    autoComplete="off"
                    spellCheck={false}
                  />
                </Field>
                <div className="button-row">
                  <Button type="submit" disabled={action.pending}>
                    Save key
                  </Button>
                  <Button
                    disabled={action.pending || !credentials?.[provider]}
                    onClick={async () => {
                      if (await action.run("credential.remove", { provider })) {
                        await refresh();
                        notify(
                          "Stored key removed. Environment-provided keys remain available to source launches.",
                        );
                      }
                    }}
                  >
                    Remove stored key
                  </Button>
                </div>
              </form>
            ))}
          </div>
        </section>
        <section className="settings-section">
          <h2>VoicePrompt</h2>
          <p className="muted">
            Version 0.5.0 · local Windows voice typing and daily focus tools
          </p>
          <div className="button-row">
            <Button
              onClick={() =>
                void openLink(
                  "https://github.com/MD-SOHAIL-AI/voiceprompt/releases",
                ).catch((error) => notify(String(error)))
              }
            >
              <ExternalLink size={15} />
              Check for updates
            </Button>
            <Button
              onClick={() => {
                useApp.setState({ page: "Dictation" });
                void action.run("settings.save", {
                  settings: { onboarding_completed: false },
                });
              }}
            >
              Run setup again
            </Button>
          </div>
        </section>
      </div>
      <div className="settings-save-footer">
        <Button
          tone="primary"
          disabled={action.pending}
          onClick={() => void save()}
        >
          <Save size={16} />
          Save settings
        </Button>
      </div>
    </section>
  );
}
