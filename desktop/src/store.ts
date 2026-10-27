import { create } from "zustand";
import type {
  Bootstrap,
  HubSnapshot,
  Page,
  Runtime,
  Settings,
  Task,
} from "./types";

interface Store {
  data: Bootstrap | null;
  runtime: Runtime | null;
  planner: HubSnapshot | null;
  settings: Settings | null;
  meter: number[];
  page: Page;
  connected: boolean;
  error: string;
  toast: string;
  mutation: number;
  focusTask: Task | null;
  inboxOpen: boolean;
  hydrate: (value: Bootstrap) => void;
  setPage: (page: Page) => void;
}
export const useApp = create<Store>((set) => ({
  data: null,
  runtime: null,
  planner: null,
  settings: null,
  meter: Array(32).fill(0),
  page: "Dictation",
  connected: false,
  error: "",
  toast: "",
  mutation: 0,
  focusTask: null,
  inboxOpen: false,
  hydrate: (value) =>
    set({
      data: value,
      runtime: value.runtime,
      planner: value.planner,
      settings: value.settings,
      connected: true,
      error: "",
    }),
  setPage: (page) => set({ page }),
}));
let toastTimer: ReturnType<typeof setTimeout>;
export function notify(message: string) {
  clearTimeout(toastTimer);
  useApp.setState({ toast: message });
  toastTimer = setTimeout(() => useApp.setState({ toast: "" }), 5500);
}
