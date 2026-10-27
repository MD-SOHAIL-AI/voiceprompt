import { describe, expect, it } from "vitest";
import { islandKind, unseenNotices } from "./island-state";
import type { HubSnapshot, Runtime } from "../types";
const runtime = {
  status: "ready",
  ready: true,
  recording: false,
  error: "",
} as Runtime;
const hub = {
  timer: { status: "running" },
  pendingCount: 2,
  nextAlarm: { due: 500 },
  notifications: [{ id: "a", revision: 0, presented_revision: -1 }],
} as HubSnapshot;
describe("island interaction priority", () => {
  it("keeps waveform ahead of timer and reminders", () =>
    expect(islandKind({ ...runtime, recording: true }, hub)).toBe("recording"));
  it("returns to focus before next alarm", () =>
    expect(islandKind(runtime, hub)).toBe("focus"));
  it("hides when nothing is active or pending", () =>
    expect(
      islandKind(runtime, {
        ...hub,
        timer: null,
        nextAlarm: null,
        pendingCount: 0,
      }),
    ).toBe("hidden"));
  it("defers previews during dictation", () => {
    expect(unseenNotices(hub, true)).toEqual([]);
    expect(unseenNotices(hub, false)).toHaveLength(1);
  });
  it("does not present the same delivery twice", () =>
    expect(
      unseenNotices(
        {
          ...hub,
          notifications: [{ ...hub.notifications[0], presented_revision: 0 }],
        },
        false,
      ),
    ).toEqual([]));
  it("does not pretend a disconnected timer is running", () =>
    expect(islandKind(runtime, hub, false)).toBe("error"));
});
