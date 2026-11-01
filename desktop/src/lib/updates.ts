import { useEffect, useId } from "react";
import { create } from "zustand";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { isNative, isPreview } from "./backend";
import { notify, useApp } from "../store";
import { version } from "../../package.json";

export interface UpdateStatus {
  phase:
    | "idle"
    | "unavailable"
    | "checking"
    | "current"
    | "available"
    | "downloading"
    | "ready"
    | "installing"
    | "error";
  supported: boolean;
  installedVersion: string;
  version: string | null;
  notes: string;
  downloaded: number;
  total: number;
  lastChecked: number | null;
  automatic: boolean;
  message: string;
}

interface UpdateStore {
  status: UpdateStatus | null;
  drafts: Record<string, string>;
}
export const useUpdates = create<UpdateStore>(() => ({
  status: null,
  drafts: {},
}));
let sampleDownloadId = 0;

export function useUpdateConnection() {
  useEffect(() => {
    let closed = false;
    let dispose: (() => void) | undefined;
    if (isNative()) {
      void (async () => {
        const unlisten = await listen<UpdateStatus>(
          "update-status",
          ({ payload }) => {
            if (!closed) useUpdates.setState({ status: payload });
          },
        );
        if (closed) {
          unlisten();
          return;
        }
        dispose = unlisten;
        const status = await invoke<UpdateStatus>("update_status");
        if (!closed) useUpdates.setState({ status });
      })().catch(() => {
        if (!closed)
          notify(
            "Update controls could not connect. Reopen VoicePrompt to retry.",
          );
      });
    } else if (isPreview()) {
      useUpdates.setState({
        status: {
          phase: "idle",
          supported: true,
          installedVersion: version,
          version: null,
          notes:
            "Sample release notes. No update is downloaded in browser preview.",
          downloaded: 0,
          total: 0,
          lastChecked: null,
          automatic: true,
          message: "Sample preview: update actions are simulated.",
        },
      });
    }
    return () => {
      closed = true;
      dispose?.();
    };
  }, []);
}

export function useUnsavedChanges(dirty: boolean, label: string) {
  const id = useId();
  useEffect(() => {
    if (dirty)
      useUpdates.setState((state) => ({
        drafts: { ...state.drafts, [id]: label },
      }));
    return () => {
      useUpdates.setState((state) => {
        const drafts = { ...state.drafts };
        delete drafts[id];
        return { drafts };
      });
    };
  }, [dirty, id, label]);
}

export function restartBlocker(): string {
  const drafts = Object.values(useUpdates.getState().drafts);
  if (drafts.length)
    return `Save or discard your ${[...new Set(drafts)].join(" and ")} before restarting to update.`;
  if (document.querySelector('[role="dialog"]'))
    return "Save or close the open dialog before restarting to update.";
  const runtime = useApp.getState().runtime;
  if (runtime?.failedAudio)
    return "Recover or discard your retained recording before restarting to update.";
  if (
    runtime?.working ||
    runtime?.recording ||
    runtime?.insertionStatus === "pending"
  )
    return "Finish recording, recognition and model preparation before restarting to update.";
  return "";
}

export async function updateAction(
  command:
    | "update_check"
    | "update_download"
    | "update_cancel"
    | "update_install"
    | "update_preferences",
  params: Record<string, unknown> = {},
) {
  if (command === "update_install") {
    const blocker = restartBlocker();
    if (blocker) {
      notify(blocker);
      return;
    }
  }
  try {
    if (isNative()) {
      await invoke(command, params);
      return;
    }
    if (!isPreview()) return;
    const previous = useUpdates.getState().status!;
    const set = (patch: Partial<UpdateStatus>) =>
      useUpdates.setState({
        status: { ...useUpdates.getState().status!, ...patch },
      });
    if (command === "update_check") {
      set({ phase: "checking", message: "Checking the sample update…" });
      await new Promise((resolve) => setTimeout(resolve, 350));
      set({
        phase: "available",
        version: "0.6.2",
        total: 108000000,
        lastChecked: Math.floor(Date.now() / 1000),
        message: "Sample update available.",
      });
    }
    if (command === "update_download") {
      const downloadId = ++sampleDownloadId;
      set({
        phase: "downloading",
        downloaded: 0,
        message: "Simulating a download…",
      });
      await new Promise((resolve) => setTimeout(resolve, 700));
      if (
        downloadId === sampleDownloadId &&
        useUpdates.getState().status?.phase === "downloading"
      )
        set({
          phase: "ready",
          downloaded: previous.total,
          message: "Sample ready state. No installer has been downloaded.",
        });
    }
    if (command === "update_cancel") {
      sampleDownloadId++;
      set({
        phase: "available",
        downloaded: 0,
        message: "Sample download cancelled.",
      });
    }
    if (command === "update_preferences")
      set({ automatic: Boolean(params.automatic) });
    if (command === "update_install")
      notify(
        "Sample preview: the installed app would close, update, and reopen.",
      );
  } catch (error) {
    notify(String(error).replace(/^Error: /, ""));
  }
}
