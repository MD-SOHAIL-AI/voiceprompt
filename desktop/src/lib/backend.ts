import { useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type {
  Bootstrap,
  EngineEvent,
  HubSnapshot,
  Page,
  Runtime,
  Settings,
} from "../types";
import { pages } from "../types";
import { notify, useApp } from "../store";
import { EngineClock } from "./engine-clock";

export const isNative = () => "__TAURI_INTERNALS__" in window;
export const isPreview = () =>
  !isNative() && new URLSearchParams(location.search).get("preview") === "1";
export async function request<T = { ok: boolean }>(
  method: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  if (isNative()) return invoke<T>("engine_request", { method, params });
  if (isPreview())
    return (await import("./preview")).previewRequest(
      method,
      params,
    ) as Promise<T>;
  throw new Error("Open VoicePrompt on your desktop to use this feature.");
}
export async function refresh() {
  const value = await request<Bootstrap>("bootstrap");
  useApp.getState().hydrate(value);
}
export async function act<T = { ok: boolean }>(
  method: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  try {
    const value = await request<T>(method, params);
    if (method.startsWith("planner."))
      useApp.setState({
        planner: await request<HubSnapshot>("planner.snapshot"),
        mutation: useApp.getState().mutation + 1,
      });
    return value;
  } catch (error) {
    notify(String(error).replace(/^Error: /, ""));
    throw error;
  }
}
export async function native(
  command: string,
  params: Record<string, unknown> = {},
) {
  if (isNative()) return invoke(command, params);
}
export async function openLink(url: string) {
  if (isNative()) await invoke("open_link", { url });
  else if (isPreview())
    notify("Preview: the desktop app opens this link in your browser.");
}
export function navigate(page: Page) {
  useApp.getState().setPage(page);
}

export function useBackend() {
  useEffect(() => {
    let closed = false;
    const clock = new EngineClock();
    const disposals: (() => void)[] = [];
    const add = async (event: string, callback: (payload: unknown) => void) => {
      const dispose = await listen(event, ({ payload }) => {
        if (!closed) callback(payload);
      });
      if (closed) dispose();
      else disposals.push(dispose);
    };
    let hydration = 0;
    const hydrate = async () => {
      const generation = ++hydration;
      for (let attempt = 0; !closed && generation === hydration; attempt++) {
        try {
          const value = await request<Bootstrap>("bootstrap");
          if (
            !closed &&
            generation === hydration &&
            clock.accept(value.engineGeneration ?? 0)
          ) {
            const current = useApp.getState();
            const sequence = value.snapshotSequence ?? 0;
            current.hydrate({
              ...value,
              runtime: clock.newerThan("runtime", sequence)
                ? (current.runtime ?? value.runtime)
                : value.runtime,
              planner: clock.newerThan("planner", sequence)
                ? current.planner
                : value.planner,
              settings: clock.newerThan("settings", sequence)
                ? (current.settings ?? value.settings)
                : value.settings,
            });
          }
          return;
        } catch (error) {
          if (
            String(error) === "The voice engine is starting. Please wait." &&
            attempt < 24
          ) {
            await new Promise((resolve) => setTimeout(resolve, 250));
            continue;
          }
          if (!closed && generation === hydration)
            useApp.setState({
              error: String(error),
              connected: false,
              settingsRecovery: String(error).includes(
                "Settings need recovery",
              ),
            });
          return;
        }
      }
    };
    void (async () => {
      if (isNative()) {
        await add("engine-event", (payload) => {
          const event = payload as EngineEvent;
          if (
            !clock.accept(event.engineGeneration, event.sequence, event.event)
          )
            return;
          if (event.event === "runtime")
            useApp.setState((state) => ({
              runtime: { ...state.runtime, ...(event.payload as Runtime) },
            }));
          if (event.event === "planner")
            useApp.setState({ planner: event.payload as HubSnapshot });
          if (event.event === "settings")
            useApp.setState({ settings: event.payload as Settings });
          if (event.event === "meter") {
            const meter = event.payload as {
              sessionId: number;
              values: number[];
            };
            if (meter.sessionId === useApp.getState().runtime?.sessionId)
              useApp.setState({ meter: meter.values });
          }
          if (event.event === "navigate") {
            const page = (event.payload as { page: Page }).page;
            if (pages.includes(page)) navigate(page);
          }
          if (event.event === "protocol-error")
            notify((event.payload as { message: string }).message);
          if (event.event === "fatal")
            useApp.setState({
              error: (event.payload as { message: string }).message,
              connected: false,
              settingsRecovery:
                (event.payload as { code?: string }).code ===
                "settings_recovery",
            });
        });
        await add("engine-disconnected", (payload) => {
          const value = payload as { generation: number; message: string };
          if (!clock.accept(value.generation)) return;
          useApp.setState({
            error: value.message,
            connected: false,
            meter: Array(32).fill(0),
          });
        });
        await add("engine-restarted", (generation) => {
          if (!clock.accept(Number(generation))) return;
          void hydrate();
        });
        await add("navigate", (value) => {
          const page = (value as { page: Page }).page;
          if (String(page) === "Notifications")
            useApp.setState({ inboxOpen: true });
          if (pages.includes(page)) navigate(page);
        });
      }
      if (!closed) await hydrate();
      if (isPreview() && !closed) {
        const timer = setInterval(() => {
          void Promise.all([
            request<HubSnapshot>("planner.snapshot"),
            request<Runtime>("runtime"),
            request<Bootstrap>("bootstrap"),
          ]).then(([planner, runtime, data]) => {
            if (!closed)
              useApp.setState({
                planner,
                runtime,
                settings: data.settings,
              });
          });
        }, 500);
        disposals.push(() => clearInterval(timer));
      }
    })().catch((error) => {
      if (!closed) useApp.setState({ error: String(error) });
    });
    return () => {
      closed = true;
      disposals.forEach((dispose) => dispose());
    };
  }, []);
}
