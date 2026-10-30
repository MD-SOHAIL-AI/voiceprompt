/** Explicit, in-memory design preview. Never used by the native application. */
import type { Bootstrap, HubSnapshot, Notice, Settings, Timer } from "../types";
const now = () => Date.now() / 1000;
const id = () => crypto.randomUUID();
const settings: Settings = {
  config_version: 7,
  onboarding_completed: true,
  backend: "whisper",
  nemotron_device: "vulkan",
  streaming_model: "tiny",
  cpu_threads: 4,
  microphone: "",
  capture_mode: "auto",
  noise_suppression: false,
  hotkey: "right_ctrl",
  model: "base.en",
  language: "en",
  device: "cpu",
  compute_type: "int8",
  beam_size: 3,
  preload_model: true,
  paste_injection: true,
  preserve_clipboard: true,
  startup_on_boot: false,
  vad_filter: true,
  whisper_phrase_decoding: false,
  max_history: 50,
  recording_mode: "ptt",
  sound_feedback: true,
  pill_position_x: -1,
  pill_position_y: -1,
  replacements: { "chat g p t": "ChatGPT" },
};
let planner: HubSnapshot = {
  tasks: [
    {
      id: "sample-task",
      title: "Read for twenty minutes",
      notes: "Chapter two",
      due: null,
      done: false,
    },
  ],
  timer: null,
  alarms: [
    {
      id: "sample-alarm",
      title: "Stretch break",
      due: now() + 2530,
      weekdays: [],
      hour: 19,
      minute: 30,
      timezone: "Asia/Kolkata",
      enabled: true,
    },
  ],
  contests: [
    {
      id: "sample-contest",
      platform: "codeforces",
      name: "Codeforces round",
      url: "https://codeforces.com/contests",
      start: now() + 900,
      end: now() + 8100,
      source: "codeforces",
      muted: false,
    },
  ],
  notifications: [],
  pendingCount: 0,
  now: now(),
  nextAlarm: null,
  preferences: {
    id: "preferences",
    timezone: "Asia/Kolkata",
    reminder_sound: true,
    platforms: ["codeforces", "leetcode", "codechef", "atcoder"],
    contest_minutes: 15,
    summary_hour: 9,
    daily_summary: true,
    clist_username: "",
  },
  sources: [{ id: "codeforces", updated: now(), error: "" }],
  syncing: false,
  counts: { tasks: 1, alarms: 1, contests: 1 },
};
const value: Bootstrap = {
  version: 2,
  settings,
  runtime: {
    status: "ready",
    ready: true,
    working: false,
    sessionId: 1,
    elapsedSeconds: 0,
    backlogSeconds: 0,
    latestText:
      "Let’s review the onboarding flow and send the updated notes after lunch.",
    error: "",
    detail: "Hold Right Ctrl to dictate into another application.",
    failedAudio: false,
    recording: false,
    insertionStatus: "none",
    deferReminders: false,
    download: {},
    runtimeInfo: "Whisper base.en · CPU",
    plannerError: "",
  },
  planner,
  history: [
    {
      id: "sample-transcript",
      text: "Let’s review the onboarding flow and send the updated notes after lunch.",
      created_at: new Date().toISOString(),
      duration_seconds: 14,
      source: "whisper",
    },
  ],
};
const state = new URLSearchParams(location.search).get("state");
if (state === "recording") {
  value.runtime.status = "recording";
  value.runtime.recording =
    value.runtime.working =
    value.runtime.deferReminders =
      true;
  value.runtime.elapsedSeconds = 14;
  value.runtime.insertionStatus = "copy";
}
if (new URLSearchParams(location.search).get("surface") === "island") {
  planner.timer = {
    id: "active",
    session: "preview-focus",
    title: "Read for twenty minutes",
    task_id: "sample-task",
    mode: "countdown",
    phase: "work",
    status: "running",
    remaining: 1122,
    ends_at: now() + 1122,
    work: 1500,
    short_break: 300,
    long_break: 900,
    completed: 0,
    rounds: 4,
    phase_index: 0,
  };
  planner.notifications = [
    {
      id: "preview-alarm",
      title: "Stretch break",
      detail: "Scheduled alarm",
      owner: "alarm:sample-alarm",
      url: "",
      due: now() - 1,
      created: now() - 1,
      expires: null,
      dismissed: false,
      revision: 0,
      presented_revision: 0,
      kind: "alarm",
    },
    {
      id: "preview-contest",
      title: "Codeforces round",
      detail: "Starts soon",
      owner: "contest:sample-contest",
      url: "https://codeforces.com/contests",
      due: now() - 1,
      created: now() - 1,
      expires: now() + 8100,
      dismissed: false,
      revision: 0,
      presented_revision: 0,
      kind: "contest",
      contest: planner.contests[0],
    },
    {
      id: "preview-task",
      title: "Review notes",
      detail: "Task reminder",
      owner: "task:sample-task",
      url: "",
      due: now() - 1,
      created: now() - 1,
      expires: null,
      dismissed: false,
      revision: 0,
      presented_revision: 0,
      kind: "task",
    },
  ];
}
function snapshot() {
  planner.now = now();
  if (planner.timer?.status === "running")
    planner.timer.remaining = Math.max(0, planner.timer.ends_at - now());
  planner.nextAlarm =
    planner.alarms
      .filter((a) => a.enabled && a.due > now())
      .sort((a, b) => a.due - b.due)[0] ?? null;
  planner.pendingCount = planner.notifications.filter(
    (n) => !n.dismissed && n.due <= now(),
  ).length;
  planner.counts = {
    tasks: planner.tasks.length,
    alarms: planner.alarms.length,
    contests: planner.contests.length,
  };
  value.planner = planner;
  return structuredClone(planner);
}
export async function previewRequest(
  method: string,
  p: Record<string, unknown>,
): Promise<unknown> {
  if (method === "bootstrap") {
    snapshot();
    return structuredClone(value);
  }
  if (method === "runtime") return structuredClone(value.runtime);
  if (method === "planner.snapshot") return snapshot();
  if (method === "microphone.list") return ["Sample microphone"];
  if (method === "prepare" || method === "microphone.check") {
    value.runtime.ready = true;
    value.runtime.status = "ready";
    value.runtime.detail = "Preview only: no microphone or model was accessed.";
  } else if (method === "settings.save") Object.assign(settings, p.settings);
  else if (method === "record.start") {
    value.runtime.recording = true;
    value.runtime.status = "recording";
  } else if (
    ["record.stop", "record.cancel", "record.discard"].includes(method)
  ) {
    value.runtime.recording = false;
    value.runtime.status = "ready";
  } else if (method === "history.list") {
    const items = value.history.filter((h) =>
      h.text.toLowerCase().includes(String(p.query ?? "").toLowerCase()),
    );
    return { items, total: items.length };
  } else if (method === "history.item")
    return value.history.find((item) => item.id === p.id);
  else if (method === "history.clear") value.history = [];
  else if (method === "history.delete")
    value.history = value.history.filter((h) => h.id !== p.id);
  else if (method === "planner.task.save") {
    const old = planner.tasks.find((t) => t.id === p.id);
    const item = {
      id: String(p.id ?? id()),
      title: String(p.title),
      notes: String(p.notes ?? ""),
      due: (p.due as number) ?? null,
      done: old?.done ?? false,
    };
    planner.tasks = old
      ? planner.tasks.map((t) => (t.id === old.id ? item : t))
      : [...planner.tasks, item];
  } else if (method === "planner.task.complete") {
    const item = planner.tasks.find((t) => t.id === p.id);
    if (item) item.done = !item.done;
  } else if (method === "planner.delete") {
    if (p.kind === "task")
      planner.tasks = planner.tasks.filter((t) => t.id !== p.id);
    if (p.kind === "alarm")
      planner.alarms = planner.alarms.filter((a) => a.id !== p.id);
  } else if (method === "planner.timer.start")
    planner.timer = {
      id: "active",
      session: id(),
      title: String(p.title),
      task_id: (p.taskId as string) ?? null,
      mode: (p.mode as Timer["mode"]) ?? "countdown",
      phase: "work",
      status: "running",
      remaining: Number(p.seconds),
      ends_at: now() + Number(p.seconds),
      work: Number(p.seconds),
      short_break: Number(p.shortBreak ?? 300),
      long_break: Number(p.longBreak ?? 900),
      completed: 0,
      rounds: Number(p.rounds ?? 4),
      phase_index: 0,
    };
  else if (method === "planner.timer.action" && planner.timer) {
    const timer = planner.timer;
    if (p.action === "pause") timer.status = "paused";
    if (p.action === "resume") {
      timer.status = "running";
      timer.ends_at = now() + timer.remaining;
    }
    if (p.action === "cancel") timer.status = "cancelled";
    if (p.action === "restart") {
      timer.remaining = timer.work;
      timer.ends_at = now() + timer.work;
      timer.status = "running";
    }
  } else if (method === "planner.alarm.save") {
    const date = p.localDue
      ? new Date(String(p.localDue))
      : new Date(Number(p.due) * 1000);
    const alarm = {
      id: String(p.id ?? id()),
      title: String(p.title),
      due: date.getTime() / 1000,
      weekdays: (p.weekdays as number[]) ?? [],
      hour: date.getHours(),
      minute: date.getMinutes(),
      timezone: "Asia/Kolkata",
      enabled: true,
    };
    planner.alarms = [
      ...planner.alarms.filter((a) => a.id !== alarm.id),
      alarm,
    ];
  } else if (method === "planner.alarm.toggle") {
    const item = planner.alarms.find((a) => a.id === p.id);
    if (item) item.enabled = !item.enabled;
  } else if (method === "planner.notification.act")
    planner.notifications = planner.notifications.filter((n) => n.id !== p.id);
  else if (method === "planner.notification.presented") {
    const notice = planner.notifications.find((n) => n.id === p.id);
    if (notice) notice.presented_revision = notice.revision;
  } else if (method === "planner.notifications.presented") {
    for (const item of p.items as { id: string; revision: number }[]) {
      const notice = planner.notifications.find((n) => n.id === item.id);
      if (notice) notice.presented_revision = item.revision;
    }
  } else if (method === "planner.preferences")
    Object.assign(planner.preferences, p);
  else if (method === "planner.contests.mute") {
    const contest = planner.contests.find((c) => c.id === p.id);
    if (contest) contest.muted = !contest.muted;
  } else if (method === "planner.item") {
    return planner.tasks.find((item) => item.id === p.id);
  } else if (method === "planner.page") {
    const key = `${p.kind}s` as "tasks" | "alarms" | "contests";
    return { items: planner[key], total: planner[key].length };
  } else if (method === "clipboard.copy")
    await navigator.clipboard.writeText(
      String(p.text ?? value.runtime.latestText),
    );
  snapshot();
  return { ok: true };
}
