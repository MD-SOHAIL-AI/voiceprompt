export const pages = [
  "Dictation",
  "History",
  "Tasks",
  "Focus timer",
  "Alarms",
  "Contests",
  "Settings",
] as const;
export type Page = (typeof pages)[number];
export type SessionStatus =
  | "idle"
  | "ready"
  | "loading model"
  | "starting"
  | "recording"
  | "catching up"
  | "transcribing"
  | "cleaning"
  | "error";
export interface Settings {
  config_version: number;
  onboarding_completed: boolean;
  backend: "whisper" | "moonshine" | "parakeet" | "nemotron";
  nemotron_device: "cpu" | "vulkan";
  streaming_model: "tiny" | "small";
  cpu_threads: number;
  microphone: string;
  capture_mode: "auto" | "wasapi" | "mme";
  noise_suppression: boolean;
  hotkey: string;
  model: string;
  language: string;
  device: string;
  compute_type: string;
  beam_size: number;
  preload_model: boolean;
  paste_injection: boolean;
  preserve_clipboard: boolean;
  cleanup_provider: "none" | "gemini" | "openrouter";
  cleanup_timeout_seconds: number;
  openrouter_model: string;
  gemini_cleanup: boolean;
  gemini_model: string;
  startup_on_boot: boolean;
  vad_filter: boolean;
  max_history: number;
  recording_mode: "ptt" | "toggle";
  sound_feedback: boolean;
  pill_position_x: number;
  pill_position_y: number;
  replacements: Record<string, string>;
}
export interface Runtime {
  status: SessionStatus;
  ready: boolean;
  working: boolean;
  sessionId: number;
  elapsedSeconds: number;
  backlogSeconds: number;
  latestText: string;
  error: string;
  detail: string;
  failedAudio: boolean;
  recording: boolean;
  insertionStatus: "none" | "pending" | "pasted" | "copy";
  deferReminders: boolean;
  download: Record<string, unknown>;
  runtimeInfo: string;
  plannerError: string;
}
export interface Task {
  id: string;
  title: string;
  notes: string;
  due: number | null;
  done: boolean;
}
export interface Timer {
  id: string;
  session: string;
  title: string;
  task_id: string | null;
  mode: "countdown" | "pomodoro";
  phase: "work" | "short_break" | "long_break" | "finished";
  status: "running" | "paused" | "completed" | "cancelled";
  remaining: number;
  ends_at: number;
  work: number;
  short_break: number;
  long_break: number;
  completed: number;
  rounds: number;
  phase_index: number;
}
export interface Alarm {
  id: string;
  title: string;
  due: number;
  weekdays: number[];
  hour: number;
  minute: number;
  timezone: string;
  enabled: boolean;
}
export type Platform = "codeforces" | "leetcode" | "codechef" | "atcoder";
export interface Contest {
  id: string;
  platform: Platform;
  name: string;
  url: string;
  start: number;
  end: number;
  source: string;
  muted: boolean;
}
export interface Notice {
  id: string;
  title: string;
  detail: string;
  owner: string;
  url: string;
  due: number;
  created: number;
  expires: number | null;
  dismissed: boolean;
  revision: number;
  presented_revision?: number;
  kind: "alarm" | "timer" | "task" | "contest" | "summary";
  contest?: Contest | null;
}
export interface Preferences {
  id: string;
  timezone: string;
  reminder_sound: boolean;
  platforms: Platform[];
  contest_minutes: number;
  summary_hour: number;
  daily_summary: boolean;
  clist_username: string;
}
export interface HubSnapshot {
  tasks: Task[];
  timer: Timer | null;
  alarms: Alarm[];
  contests: Contest[];
  notifications: Notice[];
  pendingCount: number;
  now: number;
  nextAlarm: Alarm | null;
  preferences: Preferences;
  sources: { id: string; updated: number | null; error: string }[];
  syncing: boolean;
  counts: Record<"tasks" | "alarms" | "contests", number>;
}
export interface HistoryItem {
  id: string;
  text: string;
  created_at: string;
  duration_seconds: number;
  source: string;
}
export interface Bootstrap {
  version: 1;
  settings: Settings;
  runtime: Runtime;
  planner: HubSnapshot | null;
  history: HistoryItem[];
  credentials: Record<"gemini" | "openrouter", boolean>;
}
export interface EngineEvent {
  version: 1;
  event:
    | "runtime"
    | "planner"
    | "settings"
    | "meter"
    | "navigate"
    | "ready"
    | "fatal"
    | "protocol-error";
  sequence: number;
  payload: unknown;
}
export const platformNames: Record<Platform, string> = {
  codeforces: "Codeforces",
  leetcode: "LeetCode",
  codechef: "CodeChef",
  atcoder: "AtCoder",
};
export const statusLabels: Record<SessionStatus, string> = {
  idle: "Not prepared",
  ready: "Ready to dictate",
  "loading model": "Preparing",
  starting: "Starting microphone",
  recording: "Listening",
  "catching up": "Listening · catching up",
  transcribing: "Finishing recording",
  cleaning: "Cleaning text",
  error: "Needs attention",
};
