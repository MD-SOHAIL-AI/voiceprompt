import type { HubSnapshot, Runtime } from "../types";
export type IslandKind =
  | "hidden"
  | "error"
  | "recording"
  | "processing"
  | "preparing"
  | "focus"
  | "alarm"
  | "notifications";
export function islandKind(
  runtime: Runtime | null,
  hub: HubSnapshot | null,
  connected = true,
): IslandKind {
  if (!runtime) return "hidden";
  if (!connected) return "error";
  if (
    runtime.recording ||
    runtime.status === "recording" ||
    runtime.status === "catching up"
  )
    return "recording";
  if (
    runtime.status === "transcribing" ||
    runtime.status === "cleaning" ||
    runtime.status === "starting"
  )
    return "processing";
  if (runtime.error) return "error";
  if (runtime.status === "loading model") return "preparing";
  if (hub?.timer && ["running", "paused"].includes(hub.timer.status))
    return "focus";
  if (hub?.nextAlarm) return "alarm";
  if (hub?.pendingCount) return "notifications";
  return "hidden";
}
export function unseenNotices(hub: HubSnapshot | null, defer: boolean) {
  return defer
    ? []
    : (hub?.notifications ?? []).filter(
        (item) => item.presented_revision !== item.revision,
      );
}
