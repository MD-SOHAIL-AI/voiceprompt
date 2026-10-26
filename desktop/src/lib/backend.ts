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
    notify("Preview: the desktop app opens this contest in your browser.");
}
export function navigate(page: Page) {
  useApp.getState().setPage(page);
}

export function useBackend() {
  useEffect(() => {
    let closed = false,
      serial = 0;
    const disposals: (() => void)[] = [];
    const add = async (event: string, callback: (payload: unknown) => void) => {
      const dispose = await listen(event, ({ payload }) => {
        if (!closed) callback(payload);
      });
      if (closed) dispose();
      else disposals.push(dispose);
    };
    const hydrate = async () => {
      try {
        const value = await request<Bootstrap>("bootstrap");
        if (!closed) useApp.getState().hydrate(value);
      } catch (error) {
        if (!closed)
          useApp.setState({ error: String(error), connected: false });
      }
    };
    void (async () => {
      if (isNative()) {
        await add("engine-event", (payload) => {
          const event = payload as EngineEvent;
          if (event.sequence <= serial) return;
          serial = event.sequence;
          if (event.event === "runtime")
            useApp.setState({ runtime: event.payload as Runtime });
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
          if (event.event === "fatal")
            useApp.setState({
              error: (event.payload as { message: string }).message,
              connected: false,
            });
        });
        await add("engine-disconnected", (message) =>
          useApp.setState({
            error: String(message),
            connected: false,
            meter: Array(32).fill(0),
          }),
        );
        await add("engine-restarted", () => {
          serial = 0;
          void hydrate();
        });
        await add("navigate", (value) => {
          const page = (value as { page: Page }).page;
          if (pages.includes(page)) navigate(page);
        });
      }
      if (!closed) await hydrate();
      if (isPreview() && !closed) {
        const timer = setInterval(() => {
          void Promise.all([
            request<HubSnapshot>("planner.snapshot"),
            request<Runtime>("runtime"),
          ]).then(([planner, runtime]) => {
            if (!closed)
              useApp.setState({
                planner,
                runtime,
                settings: useApp.getState().data!.settings,
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
