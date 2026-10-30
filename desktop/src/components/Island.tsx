import { useEffect, useRef, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import {
  AlarmClock,
  AlertTriangle,
  Bell,
  Check,
  ChevronDown,
  ExternalLink,
  LoaderCircle,
  Pause,
  Pin,
  PinOff,
  Plus,
  Timer,
  Trophy,
  X,
} from "lucide-react";
import { act, isNative, native, useBackend } from "../lib/backend";
import { countdown, dateTime } from "../lib/format";
import { islandKind, unseenNotices } from "../lib/island-state";
import { notify, useApp } from "../store";
import { platformNames, type Notice } from "../types";
import { AlarmEditor, TimerComposer, TimerControls } from "../pages/Planner";
import { NotificationList, noticeDescription } from "./Notifications";
import { Button, Empty, Toggle, WaveMark, useAction } from "./ui";
import { Waveform } from "./Waveform";
import { updatePreferences, usePreferences } from "../lib/preferences";

type Tab = "Focus" | "Alarms" | "Notifications";
type View = "compact" | "expanded" | "peek";
export function Island() {
  useBackend();
  const enabled = usePreferences((p) => p.islandEnabled);
  const pinned = usePreferences((p) => p.islandPinned);
  const runtime = useApp((s) => s.runtime),
    hub = useApp((s) => s.planner),
    meter = useApp((s) => s.meter),
    connected = useApp((s) => s.connected),
    error = useApp((s) => s.error),
    settings = useApp((s) => s.settings),
    toast = useApp((s) => s.toast);
  const [view, setView] = useState<View>(
    new URLSearchParams(location.search).has("panel") ? "expanded" : "compact",
  );
  const [tab, setTab] = useState<Tab>(
    new URLSearchParams(location.search).get("panel") === "notifications"
      ? "Notifications"
      : "Focus",
  );
  const [peek, setPeek] = useState<Notice | null>(null),
    [addingAlarm, setAddingAlarm] = useState(false),
    [success, setSuccess] = useState(false);
  const action = useAction();
  const kind = islandKind(runtime, hub, connected);
  const pending = hub?.pendingCount ?? 0;
  const deferred = !!runtime?.deferReminders;
  const presented = useRef(new Set<string>()),
    showing = useRef<Notice[]>([]),
    previousBusy = useRef(false),
    lastResult = useRef("");
  const restored = useRef(false);
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const open = (selected?: Tab) => {
    setTab(
      selected ??
        (hub?.timer && ["running", "paused"].includes(hub.timer.status)
          ? "Focus"
          : pending
            ? "Notifications"
            : hub?.nextAlarm
              ? "Alarms"
              : "Focus"),
    );
    setView("expanded");
  };
  const markPresented = () => {
    const items = showing.current.map((item) => ({
      id: item.id,
      revision: item.revision,
    }));
    showing.current = [];
    if (items.length)
      void act("planner.notifications.presented", { items }).catch(
        () => undefined,
      );
  };

  useEffect(() => {
    if (deferred && !previousBusy.current) {
      showing.current.forEach((n) =>
        presented.current.delete(`${n.id}:${n.revision}`),
      );
      showing.current = [];
      setView("compact");
      setPeek(null);
    }
    previousBusy.current = deferred;
  }, [deferred]);

  useEffect(() => {
    if (view !== "compact" || !connected || !enabled) return;
    const candidates = unseenNotices(hub, deferred).filter(
      (n) => !presented.current.has(`${n.id}:${n.revision}`),
    );
    if (!candidates.length) return;
    candidates.forEach((n) => presented.current.add(`${n.id}:${n.revision}`));
    showing.current = candidates;
    setPeek(candidates[0]);
    setView("peek");
  }, [hub, deferred, view, connected, enabled]);
  useEffect(() => {
    if (enabled) return;
    showing.current.forEach((n) =>
      presented.current.delete(`${n.id}:${n.revision}`),
    );
    showing.current = [];
    setView("compact");
    setPeek(null);
  }, [enabled]);
  useEffect(() => {
    if (view !== "peek" || !enabled) return;
    const timer = setTimeout(() => {
      markPresented();
      setPeek(null);
      setView("compact");
    }, 8000);
    return () => clearTimeout(timer);
  }, [view, enabled]);
  useEffect(() => {
    if (
      !runtime ||
      runtime.deferReminders ||
      runtime.error ||
      !runtime.latestText ||
      !["pasted", "copy"].includes(runtime.insertionStatus)
    )
      return;
    const key = `${runtime.sessionId}:${runtime.latestText}`;
    if (lastResult.current === key) return;
    lastResult.current = key;
    setSuccess(true);
  }, [
    runtime?.sessionId,
    runtime?.insertionStatus,
    runtime?.deferReminders,
    runtime?.error,
    runtime?.latestText,
  ]);
  useEffect(() => {
    if (!success) return;
    const timer = setTimeout(() => setSuccess(false), 900);
    return () => clearTimeout(timer);
  }, [success]);
  const visible =
    enabled &&
    (pinned ||
      kind !== "hidden" ||
      view === "expanded" ||
      view === "peek" ||
      success);
  useEffect(() => {
    if (!settings) return;
    let cancelled = false;
    void (async () => {
      if (!restored.current) {
        restored.current = true;
        await native("restore_island", {
          x: settings.pill_position_x,
          y: settings.pill_position_y,
        });
      }
      if (!cancelled)
        await native("island_view", {
          mode: visible ? view : "hidden",
          focus: view === "expanded",
        });
    })().catch((error) => notify(String(error)));
    return () => {
      cancelled = true;
    };
  }, [view, visible, !!settings]);
  useEffect(() => {
    if (!isNative()) return;
    let closed = false,
      off: (() => void) | undefined,
      timer: ReturnType<typeof setTimeout>;
    const window = getCurrentWindow();
    void window
      .onMoved(({ payload }) => {
        if (view !== "compact" || !drag.current?.moved) return;
        clearTimeout(timer);
        timer = setTimeout(() => {
          drag.current = null;
          void window.scaleFactor().then((scale) =>
            native("remember_island", {
              x: payload.x / scale,
              y: payload.y / scale,
            }),
          );
        }, 350);
      })
      .then((dispose) => {
        if (closed) dispose();
        else off = dispose;
      });
    return () => {
      closed = true;
      clearTimeout(timer);
      off?.();
    };
  }, [view]);
  useEffect(() => {
    if (view !== "expanded" || !isNative()) return;
    let closed = false,
      off: (() => void) | undefined;
    void getCurrentWindow()
      .onFocusChanged(({ payload }) => {
        if (!payload && !addingAlarm) setView("compact");
      })
      .then((dispose) => {
        if (closed) dispose();
        else off = dispose;
      });
    return () => {
      closed = true;
      off?.();
    };
  }, [view, addingAlarm]);
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (addingAlarm) setAddingAlarm(false);
        else {
          markPresented();
          setView("compact");
        }
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [addingAlarm]);

  if (!runtime || !visible) return null;
  const timer = hub?.timer,
    active = timer && ["running", "paused"].includes(timer.status);
  const fullLabel =
    kind === "focus" && timer
      ? `${timer.title}, ${countdown(timer.remaining)} remaining, ${timer.status}`
      : kind === "alarm" && hub?.nextAlarm
        ? `${hub.nextAlarm.title}, ${countdown(hub.nextAlarm.due - hub.now)} until alarm`
        : kind === "recording"
          ? `Listening. ${pending} pending reminders.`
          : kind === "error"
            ? "VoicePrompt needs attention"
            : pending
              ? `${pending} pending reminders`
              : "VoicePrompt ready. Open floating controls";
  return (
    <div
      className={`island-frame view-${view} ${kind === "recording" ? "is-listening" : ""}`}
    >
      {view === "compact" && (
        <button
          className={`island-capsule kind-${kind}`}
          aria-label={fullLabel}
          title={`${fullLabel}. Click to open VoicePrompt controls.`}
          onClick={() => {
            if (!drag.current?.moved) open();
          }}
          onPointerDown={(event) => {
            drag.current = { x: event.clientX, y: event.clientY, moved: false };
          }}
          onPointerMove={(event) => {
            if (
              drag.current &&
              event.buttons === 1 &&
              !drag.current.moved &&
              Math.hypot(
                event.clientX - drag.current.x,
                event.clientY - drag.current.y,
              ) > 5
            ) {
              drag.current.moved = true;
              if (isNative()) void getCurrentWindow().startDragging();
            }
          }}
        >
          {success && !deferred ? (
            <>
              <Check size={15} />
              <span>
                {runtime.insertionStatus === "pasted" ? "Done" : "Copy ready"}
              </span>
            </>
          ) : kind === "recording" ? (
            <Waveform values={meter} compact />
          ) : kind === "processing" || kind === "preparing" ? (
            <>
              <LoaderCircle size={14} className="spin" />
              <span>{kind === "preparing" ? "Preparing" : "Finishing"}</span>
            </>
          ) : kind === "error" ? (
            <>
              <AlertTriangle size={15} />
              <span>Attention</span>
            </>
          ) : kind === "focus" && timer ? (
            <>
              <span
                className={`mini-progress ${timer.status}`}
                style={
                  {
                    "--progress":
                      Math.max(
                        0,
                        Math.min(
                          1,
                          1 -
                            timer.remaining /
                              Math.max(
                                1,
                                timer[
                                  timer.phase === "short_break"
                                    ? "short_break"
                                    : timer.phase === "long_break"
                                      ? "long_break"
                                      : "work"
                                ],
                              ),
                        ),
                      ) *
                        100 +
                      "%",
                  } as React.CSSProperties
                }
              >
                {timer.status === "paused" && <Pause size={8} />}
              </span>
              <span className="numeric">{countdown(timer.remaining)}</span>
            </>
          ) : kind === "alarm" && hub?.nextAlarm ? (
            <>
              <AlarmClock size={15} />
              <span className="numeric">
                {countdown(hub.nextAlarm.due - hub.now)}
              </span>
            </>
          ) : pending ? (
            <>
              <Bell size={15} />
              <span>{pending} pending</span>
            </>
          ) : (
            <>
              <WaveMark size={16} />
              <span>Ready</span>
            </>
          )}
          {pending > 0 && kind !== "notifications" && (
            <span
              className={kind === "recording" ? "pending-dot" : "island-badge"}
            >
              {kind !== "recording" ? (pending > 9 ? "9+" : pending) : null}
            </span>
          )}
        </button>
      )}
      {view === "peek" && peek && (
        <div className={`island-peek kind-${peek.kind}`} role="status">
          <div className="peek-copy">
            <strong>{peek.title}</strong>
            <p>{noticeDescription(peek, hub?.now ?? Date.now() / 1000)}</p>
          </div>
          <div className="peek-actions">
            <Button
              tone="ghost"
              aria-label="Open notifications"
              onClick={() => {
                markPresented();
                open("Notifications");
              }}
            >
              <Bell size={15} />
              {pending > 1 ? `+${pending - 1}` : "View"}
            </Button>
            <Button
              tone="ghost"
              aria-label="Collapse reminder preview"
              onClick={() => {
                markPresented();
                setView("compact");
              }}
            >
              <X size={15} />
            </Button>
          </div>
        </div>
      )}
      {view === "expanded" && (
        <div className="island-panel">
          <header className="island-header">
            <WaveMark size={20} />
            <strong>VoicePrompt</strong>
            <Button
              tone="ghost"
              className="island-pin"
              aria-label="Keep island visible"
              aria-pressed={pinned}
              title={
                pinned
                  ? "Unpin: hide automatically when idle"
                  : "Pin: keep visible when idle"
              }
              onClick={() => updatePreferences({ islandPinned: !pinned })}
            >
              {pinned ? <PinOff size={15} /> : <Pin size={15} />}
            </Button>
            <Button
              tone="ghost"
              aria-label="Collapse island"
              onClick={() => {
                markPresented();
                setView("compact");
              }}
            >
              <ChevronDown size={17} />
            </Button>
          </header>
          <div
            className="island-tabs"
            role="tablist"
            aria-label="Floating controls"
          >
            {(["Focus", "Alarms", "Notifications"] as Tab[]).map((name) => (
              <button
                id={`tab-${name}`}
                key={name}
                role="tab"
                aria-selected={tab === name}
                aria-controls={`panel-${name}`}
                tabIndex={tab === name ? 0 : -1}
                onClick={() => {
                  setTab(name);
                  if (name === "Notifications") markPresented();
                }}
                onKeyDown={(event) => {
                  if (
                    ["ArrowLeft", "ArrowRight", "Home", "End"].includes(
                      event.key,
                    )
                  ) {
                    event.preventDefault();
                    const names: Tab[] = ["Focus", "Alarms", "Notifications"];
                    const index =
                      event.key === "Home"
                        ? 0
                        : event.key === "End"
                          ? 2
                          : (names.indexOf(tab) +
                              (event.key === "ArrowRight" ? 1 : 2)) %
                            3;
                    setTab(names[index]);
                    document.getElementById(`tab-${names[index]}`)?.focus();
                  }
                }}
              >
                {name}
                {name === "Notifications" && pending > 0 && (
                  <span className="count">{pending > 9 ? "9+" : pending}</span>
                )}
              </button>
            ))}
          </div>
          <div
            key={tab}
            className="island-panel-body"
            role="tabpanel"
            id={`panel-${tab}`}
            aria-labelledby={`tab-${tab}`}
          >
            {(runtime.error || error || runtime.failedAudio) && (
              <div className="island-error" role="alert">
                <AlertTriangle size={17} />
                <p>{error || runtime.error || runtime.detail}</p>
                {runtime.failedAudio && (
                  <>
                    <Button
                      disabled={runtime.working || action.pending}
                      onClick={() => void action.run("record.retry")}
                    >
                      Retry recording
                    </Button>
                    <Button
                      disabled={runtime.working || action.pending}
                      onClick={() => void action.run("record.discard")}
                    >
                      Discard
                    </Button>
                  </>
                )}
                <Button
                  onClick={() =>
                    connected
                      ? void native("open_main", { page: "Dictation" })
                      : void native("restart_engine")
                  }
                >
                  {connected ? "Open dictation" : "Restart engine"}
                </Button>
              </div>
            )}
            {tab === "Focus" && (
              <>
                <div className="island-timer">
                  {active && timer ? (
                    <>
                      <p>{timer.title}</p>
                      <div className="island-digits numeric">
                        {countdown(timer.remaining)}
                      </div>
                      <progress
                        max={1}
                        value={Math.max(
                          0,
                          Math.min(
                            1,
                            1 -
                              timer.remaining /
                                Math.max(
                                  1,
                                  timer[
                                    timer.phase === "short_break"
                                      ? "short_break"
                                      : timer.phase === "long_break"
                                        ? "long_break"
                                        : "work"
                                  ],
                                ),
                          ),
                        )}
                        aria-label="Focus session progress"
                      />
                      <span className="sr-only">{timer.status}</span>
                      <TimerControls compact />
                    </>
                  ) : (
                    <Empty title="Ready for some focus?">
                      Start a quick timer below.
                    </Empty>
                  )}
                </div>
                <TimerComposer compact />
                {hub?.nextAlarm && (
                  <div className="next-alarm">
                    <h3>Next alarm</h3>
                    <Toggle
                      label={`${hub.nextAlarm.title} · ${new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", timeZone: hub.preferences.timezone }).format(new Date(hub.nextAlarm.due * 1000))}`}
                      checked={hub.nextAlarm.enabled}
                      disabled={action.pending}
                      onChange={() =>
                        void action.run("planner.alarm.toggle", {
                          id: hub.nextAlarm!.id,
                        })
                      }
                    />
                  </div>
                )}
              </>
            )}
            {tab === "Alarms" && (
              <>
                <div className="island-section-heading">
                  <h2>Upcoming alarms</h2>
                  <Button
                    tone="ghost"
                    aria-label="Add alarm"
                    onClick={() => setAddingAlarm(true)}
                  >
                    <Plus size={17} />
                  </Button>
                </div>
                {hub?.alarms.length ? (
                  hub.alarms.map((alarm) => (
                    <div className="island-alarm" key={alarm.id}>
                      <Toggle
                        label={alarm.title}
                        checked={alarm.enabled}
                        disabled={action.pending}
                        onChange={() =>
                          void action.run("planner.alarm.toggle", {
                            id: alarm.id,
                          })
                        }
                      />
                      <p>{dateTime(alarm.due, alarm.timezone)}</p>
                    </div>
                  ))
                ) : (
                  <Empty title="No alarms yet">
                    Add one without leaving your work.
                  </Empty>
                )}
                <Button onClick={() => setAddingAlarm(true)}>
                  <Plus size={15} />
                  Add alarm
                </Button>
              </>
            )}
            {tab === "Notifications" && <NotificationList compact />}
          </div>
          <footer>
            <Button
              onClick={() => {
                setView("compact");
                void native("open_main", {
                  page:
                    tab === "Focus"
                      ? "Focus timer"
                      : tab === "Alarms"
                        ? "Alarms"
                        : "Notifications",
                });
              }}
            >
              <ExternalLink size={15} />
              Open VoicePrompt
            </Button>
          </footer>
          {toast && (
            <div className="island-toast" role="status">
              {toast}
            </div>
          )}
        </div>
      )}
      {addingAlarm && (
        <AlarmEditor
          zone={hub?.preferences.timezone ?? "Asia/Kolkata"}
          onClose={() => setAddingAlarm(false)}
        />
      )}
    </div>
  );
}
