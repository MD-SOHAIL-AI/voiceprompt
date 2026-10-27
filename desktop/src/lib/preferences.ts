import { create } from "zustand";
import { emit, listen } from "@tauri-apps/api/event";
import { notify } from "../store";
import {
  parsePreferences,
  resolveAppearance,
  type Preferences,
} from "./preferences-model";

const storageKey = "voiceprompt.preferences.v1";
function readPreferences() {
  try {
    return parsePreferences(
      JSON.parse(localStorage.getItem(storageKey) ?? "null"),
    );
  } catch {
    return parsePreferences(null);
  }
}
export const usePreferences = create<Preferences>(() => readPreferences());
const system = window.matchMedia("(prefers-color-scheme: dark)");
function apply(preferences: Preferences) {
  usePreferences.setState(preferences);
  const resolved = resolveAppearance(preferences.appearance, system.matches);
  document.documentElement.dataset.appearance = resolved;
  document.documentElement.dataset.palette = preferences.palette;
  document.documentElement.dataset.islandTranslucent = String(
    preferences.islandTransparency > 0,
  );
  document.documentElement.style.setProperty(
    "--island-opacity",
    `${100 - preferences.islandTransparency}%`,
  );
  document.documentElement.style.colorScheme = resolved;
}
export function updatePreferences(
  patch: Partial<Omit<Preferences, "version">>,
) {
  const preferences = parsePreferences({
    ...usePreferences.getState(),
    ...patch,
  });
  apply(preferences);
  try {
    localStorage.setItem(storageKey, JSON.stringify(preferences));
  } catch {
    notify(
      "Your appearance changed for this session, but could not be saved on this device.",
    );
  }
  if ("__TAURI_INTERNALS__" in window)
    void emit("preferences-changed", preferences).catch(() =>
      notify(
        "The other window could not update. Reopen it to apply your appearance.",
      ),
    );
}
export function initializePreferences() {
  apply(readPreferences());
  system.addEventListener("change", () => apply(usePreferences.getState()));
  window.addEventListener("storage", (event) => {
    if (event.key === storageKey || event.key === null)
      apply(readPreferences());
  });
  if ("__TAURI_INTERNALS__" in window) {
    void listen<Preferences>("preferences-changed", ({ payload }) =>
      apply(parsePreferences(payload)),
    )
      .then(() => apply(readPreferences()))
      .catch(() =>
        notify(
          "Live appearance updates are unavailable. Reopen the other window to apply changes.",
        ),
      );
  }
}
