import { useEffect, useState, type FormEvent } from "react";
import {
  Check,
  Edit3,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Square,
  Timer as TimerIcon,
  Trash2,
} from "lucide-react";
import { act, navigate, request } from "../lib/backend";
import { countdown, dateTime, localInput } from "../lib/format";
import { notify, useApp } from "../store";
import type { Alarm, Task } from "../types";
import {
  Button,
  Empty,
  Field,
  Modal,
  Toggle,
  useAction,
} from "../components/ui";

export function usePaged<T>(kind: string, initial: T[], total: number) {
  const [offset, setOffset] = useState(0),
    [items, setItems] = useState<T[]>([]);
  const revision = useApp((s) => s.mutation);
  useEffect(() => {
    let alive = true;
    if (offset)
      void request<{ items: T[] }>("planner.page", { kind, offset })
        .then((result) => {
          if (alive) setItems(result.items);
        })
        .catch((error) => notify(String(error)));
    return () => {
      alive = false;
    };
  }, [kind, offset, total, revision]);
  return {
    items: offset ? items : initial,
    footer:
      total > 50 ? (
        <div className="pagination">
          <Button
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 50))}
          >
            Previous
          </Button>
          <span>
            {offset + 1}–{Math.min(offset + 50, total)} of {total}
          </span>
          <Button
            disabled={offset + 50 >= total}
            onClick={() => setOffset(offset + 50)}
          >
            Next
          </Button>
        </div>
      ) : null,
  };
}

export function TasksPage() {
  const planner = useApp((s) => s.planner);
  const action = useAction();
  const [quick, setQuick] = useState(""),
    [editing, setEditing] = useState<Task | "new" | null>(null),
    [removing, setRemoving] = useState<Task | null>(null);
  const paged = usePaged<Task>(
    "task",
    planner?.tasks ?? [],
    planner?.counts.tasks ?? 0,
  );
  if (!planner)
    return (
      <Empty title="Tasks are unavailable">
        Your planner data has been kept. Check Dictation for the storage error.
      </Empty>
    );
  return (
    <section>
      <header className="page-heading">
        <h1>Tasks</h1>
        <Button onClick={() => setEditing("new")}>
          <Plus size={16} />
          Add with details
        </Button>
      </header>
      <form
        className="quick-entry"
        onSubmit={async (e) => {
          e.preventDefault();
          if (await action.run("planner.task.save", { title: quick }))
            setQuick("");
        }}
      >
        <input
          aria-label="New task"
          value={quick}
          onChange={(e) => setQuick(e.target.value)}
          placeholder="What would you like to work on?"
          required
          maxLength={240}
        />
        <Button
          tone="primary"
          type="submit"
          disabled={action.pending || !quick.trim()}
        >
          Add task
        </Button>
      </form>
      <div className="table-frame">
        <table>
          <thead>
            <tr>
              <th className="check-column">
                <span className="sr-only">Complete</span>
              </th>
              <th>Task</th>
              <th>Reminder</th>
              <th className="actions-heading">Actions</th>
            </tr>
          </thead>
          <tbody>
            {paged.items.map((task) => (
              <tr key={task.id}>
                <td>
                  <button
                    className={`task-check ${task.done ? "done" : ""}`}
                    aria-label={`${task.done ? "Reopen" : "Complete"} ${task.title}`}
                    disabled={action.pending}
                    onClick={() =>
                      void action.run("planner.task.complete", { id: task.id })
                    }
                  >
                    {task.done && <Check size={14} />}
                  </button>
                </td>
                <td>
                  <strong className={task.done ? "completed-task" : ""}>
                    {task.title}
                  </strong>
                  {task.notes && <p className="row-detail">{task.notes}</p>}
                </td>
                <td className="muted nowrap">
                  {dateTime(task.due, planner.preferences.timezone)}
                </td>
                <td>
                  <div className="row-actions">
                    <Button
                      tone="ghost"
                      aria-label={`Start timer for ${task.title}`}
                      onClick={() => {
                        useApp.setState({ focusTask: task });
                        navigate("Focus timer");
                      }}
                    >
                      <TimerIcon size={16} />
                    </Button>
                    <Button
                      tone="ghost"
                      aria-label={`Edit ${task.title}`}
                      onClick={() => setEditing(task)}
                    >
                      <Edit3 size={16} />
                    </Button>
                    <Button
                      tone="ghost"
                      aria-label={`Delete ${task.title}`}
                      onClick={() => setRemoving(task)}
                    >
                      <Trash2 size={16} />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!paged.items.length && (
          <Empty title="Make room for your next task">
            Add a task above. You can link it to a focus session.
          </Empty>
        )}
      </div>
      {paged.footer}
      {editing && (
        <TaskEditor
          task={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
          zone={planner.preferences.timezone}
        />
      )}
      <Modal
        open={!!removing}
        onClose={() => setRemoving(null)}
        title="Delete this task?"
        description="Its pending reminders will be dismissed. Other tasks are kept."
      >
        <p>{removing?.title}</p>
        <div className="button-row">
          <Button
            tone="danger"
            disabled={action.pending}
            onClick={async () => {
              if (
                await action.run("planner.delete", {
                  kind: "task",
                  id: removing?.id,
                })
              )
                setRemoving(null);
            }}
          >
            Delete task
          </Button>
          <Button onClick={() => setRemoving(null)}>Cancel</Button>
        </div>
      </Modal>
    </section>
  );
}
function TaskEditor({
  task,
  zone,
  onClose,
}: {
  task?: Task;
  zone: string;
  onClose: () => void;
}) {
  const [title, setTitle] = useState(task?.title ?? ""),
    [notes, setNotes] = useState(task?.notes ?? ""),
    [due, setDue] = useState(task?.due ? localInput(task.due, zone) : "");
  const action = useAction();
  return (
    <Modal open onClose={onClose} title={task ? "Edit task" : "Add task"}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (
            await action.run("planner.task.save", {
              id: task?.id,
              title,
              notes,
              localDue: due || null,
              due: null,
            })
          )
            onClose();
        }}
      >
        <Field label="Task">
          <input
            autoFocus
            required
            maxLength={240}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <Field label="Notes">
          <textarea
            rows={5}
            maxLength={10000}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </Field>
        <Field label="Reminder" hint={`Optional · ${zone}`}>
          <input
            type="datetime-local"
            value={due}
            onChange={(e) => setDue(e.target.value)}
          />
        </Field>
        <div className="button-row">
          <Button tone="primary" type="submit" disabled={action.pending}>
            Save task
          </Button>
          <Button onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </Modal>
  );
}

export function TimerControls({ compact = false }: { compact?: boolean }) {
  const timer = useApp((s) => s.planner?.timer);
  const action = useAction();
  const [ending, setEnding] = useState(false);
  if (!timer || !["running", "paused"].includes(timer.status)) return null;
  const change = (name: string) =>
    action.run("planner.timer.action", {
      action: name,
      session: timer.session,
    });
  return (
    <>
      <div className={`button-row ${compact ? "timer-buttons-compact" : ""}`}>
        <Button
          tone="primary"
          disabled={action.pending}
          onClick={() =>
            void change(timer.status === "running" ? "pause" : "resume")
          }
        >
          {timer.status === "running" ? (
            <Pause size={16} />
          ) : (
            <Play size={16} />
          )}
          {timer.status === "running" ? "Pause" : "Resume"}
        </Button>
        {!compact && (
          <Button
            disabled={action.pending}
            onClick={() => void change("restart")}
          >
            <RotateCcw size={15} />
            Restart
          </Button>
        )}
        <Button disabled={action.pending} onClick={() => setEnding(true)}>
          <Square size={14} />
          End session
        </Button>
      </div>
      <Modal
        open={ending}
        onClose={() => setEnding(false)}
        title="End this focus session?"
        description="The timer stops. Your task and scheduled alarms are kept."
      >
        <div className="button-row">
          <Button
            tone="danger"
            disabled={action.pending}
            onClick={async () => {
              if (await change("cancel")) setEnding(false);
            }}
          >
            End session
          </Button>
          <Button onClick={() => setEnding(false)}>Keep going</Button>
        </div>
      </Modal>
    </>
  );
}

export function TimerComposer({ compact = false }: { compact?: boolean }) {
  const focusTask = useApp((s) => s.focusTask),
    timer = useApp((s) => s.planner?.timer);
  const action = useAction();
  const [title, setTitle] = useState(focusTask?.title ?? "Focus session"),
    [minutes, setMinutes] = useState(25),
    [mode, setMode] = useState("countdown"),
    [shortBreak, setShortBreak] = useState(5),
    [longBreak, setLongBreak] = useState(15),
    [rounds, setRounds] = useState(4),
    [custom, setCustom] = useState(!compact),
    [replacement, setReplacement] = useState<Record<string, unknown> | null>(
      null,
    );
  useEffect(() => {
    if (focusTask) setTitle(focusTask.title);
  }, [focusTask]);
  async function begin(duration = minutes, replace = false) {
    const params = {
      title,
      seconds: duration * 60,
      mode,
      shortBreak: shortBreak * 60,
      longBreak: longBreak * 60,
      rounds,
      taskId: focusTask?.id ?? null,
      replace,
      expectedSession: timer?.session,
    };
    if (!replace && timer && ["running", "paused"].includes(timer.status)) {
      setReplacement(params);
      return;
    }
    if (await action.run("planner.timer.start", params)) {
      notify("Focus session started.");
      useApp.setState({ focusTask: null });
    }
  }
  return (
    <>
      <div className={compact ? "quick-timer" : "timer-composer"}>
        {compact && (
          <>
            <h3>Quick timer</h3>
            <div className="preset-row">
              <Button disabled={action.pending} onClick={() => void begin(25)}>
                25 min
              </Button>
              <Button disabled={action.pending} onClick={() => void begin(50)}>
                50 min
              </Button>
              <Button onClick={() => setCustom(!custom)}>Custom</Button>
            </div>
          </>
        )}
        {custom && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void begin();
            }}
          >
            <Field label="Session name">
              <input
                required
                maxLength={240}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </Field>
            <div className="form-grid">
              <Field label="Duration (minutes)">
                <input
                  type="number"
                  required
                  min="0.01"
                  step="any"
                  value={minutes}
                  onChange={(e) => setMinutes(Number(e.target.value))}
                />
              </Field>
              {!compact && (
                <Field label="Timer mode">
                  <select
                    value={mode}
                    onChange={(e) => setMode(e.target.value)}
                  >
                    <option value="countdown">Single session</option>
                    <option value="pomodoro">Pomodoro cycles</option>
                  </select>
                </Field>
              )}
            </div>
            {!compact && mode === "pomodoro" && (
              <div className="form-grid three">
                <Field label="Short break (min)">
                  <input
                    type="number"
                    required
                    min="1"
                    value={shortBreak}
                    onChange={(e) => setShortBreak(Number(e.target.value))}
                  />
                </Field>
                <Field label="Long break (min)">
                  <input
                    type="number"
                    required
                    min="1"
                    value={longBreak}
                    onChange={(e) => setLongBreak(Number(e.target.value))}
                  />
                </Field>
                <Field label="Work rounds">
                  <input
                    type="number"
                    required
                    min="1"
                    max="100"
                    value={rounds}
                    onChange={(e) => setRounds(Number(e.target.value))}
                  />
                </Field>
              </div>
            )}
            {focusTask && <p className="muted">Linked to {focusTask.title}</p>}
            <Button tone="primary" type="submit" disabled={action.pending}>
              <Play size={15} />
              Start focus session
            </Button>
          </form>
        )}
      </div>
      <Modal
        open={!!replacement}
        onClose={() => setReplacement(null)}
        title="Replace the current timer?"
        description="Starting this session will end the current timer. Scheduled alarms are kept."
      >
        <p>{timer?.title}</p>
        <div className="button-row">
          <Button
            tone="primary"
            disabled={action.pending}
            onClick={async () => {
              if (
                replacement &&
                (await action.run("planner.timer.start", {
                  ...replacement,
                  replace: true,
                }))
              ) {
                setReplacement(null);
                useApp.setState({ focusTask: null });
              }
            }}
          >
            Replace timer
          </Button>
          <Button onClick={() => setReplacement(null)}>
            Keep current timer
          </Button>
        </div>
      </Modal>
    </>
  );
}

export function FocusPage() {
  const planner = useApp((s) => s.planner);
  const timer = planner?.timer;
  const active = timer && ["running", "paused"].includes(timer.status);
  if (!planner) return <Empty title="Focus timer is unavailable" />;
  const duration = active
    ? timer[
        timer.phase === "short_break"
          ? "short_break"
          : timer.phase === "long_break"
            ? "long_break"
            : "work"
      ]
    : 1;
  return (
    <section>
      <header className="page-heading">
        <h1>Focus timer</h1>
      </header>
      <div className="focus-session panel">
        <span className="muted">
          {active
            ? `${timer.phase.replaceAll("_", " ")} · ${timer.status}`
            : "Ready when you are"}
        </span>
        <h2>{active ? timer.title : "Give one activity your attention"}</h2>
        <div
          className="timer-digits numeric"
          aria-label={
            active
              ? `${countdown(timer.remaining)} remaining`
              : "No active timer"
          }
        >
          {active ? countdown(timer.remaining) : "25:00"}
        </div>
        <progress
          max={1}
          value={
            active
              ? Math.max(0, Math.min(1, 1 - timer.remaining / duration))
              : 0
          }
          aria-label="Focus session progress"
        />
        {active ? (
          <TimerControls />
        ) : (
          <p className="muted">Choose a duration below to begin.</p>
        )}
        {active && timer.mode === "pomodoro" && (
          <p className="muted">
            {timer.completed} of {timer.rounds} work rounds completed
          </p>
        )}
      </div>
      <div className="section-heading">
        <h2>{active ? "Start another session" : "Your next session"}</h2>
        <p className="muted">
          Your floating island keeps the countdown visible while you work.
        </p>
      </div>
      <TimerComposer />
    </section>
  );
}

export function AlarmsPage() {
  const planner = useApp((s) => s.planner),
    action = useAction();
  const [editing, setEditing] = useState<Alarm | "new" | null>(null),
    [removing, setRemoving] = useState<Alarm | null>(null);
  const paged = usePaged<Alarm>(
    "alarm",
    planner?.alarms ?? [],
    planner?.counts.alarms ?? 0,
  );
  if (!planner) return <Empty title="Alarms are unavailable" />;
  return (
    <section>
      <header className="page-heading">
        <h1>Alarms</h1>
        <Button tone="primary" onClick={() => setEditing("new")}>
          <Plus size={16} />
          Add alarm
        </Button>
      </header>
      <div className="alarm-list">
        {paged.items.map((alarm) => (
          <article className="alarm-item" key={alarm.id}>
            <div>
              <strong>{alarm.title}</strong>
              <p className="muted">
                {dateTime(alarm.due, alarm.timezone)} ·{" "}
                {alarm.weekdays.length
                  ? alarm.weekdays
                      .map(
                        (day) =>
                          ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][
                            day
                          ],
                      )
                      .join(", ")
                  : "One time"}
              </p>
            </div>
            <Toggle
              label={`Enable ${alarm.title}`}
              checked={alarm.enabled}
              onChange={() =>
                void action.run("planner.alarm.toggle", { id: alarm.id })
              }
              disabled={action.pending}
            />
            <Button
              tone="ghost"
              aria-label={`Edit ${alarm.title}`}
              onClick={() => setEditing(alarm)}
            >
              <Edit3 size={16} />
            </Button>
            <Button
              tone="ghost"
              aria-label={`Delete ${alarm.title}`}
              onClick={() => setRemoving(alarm)}
            >
              <Trash2 size={16} />
            </Button>
          </article>
        ))}
        {!paged.items.length && (
          <Empty title="No alarms scheduled">
            Add an alarm and the island will show its countdown.
          </Empty>
        )}
      </div>
      {paged.footer}
      <p className="page-footnote">
        Alarms work while VoicePrompt runs in the tray and Windows is awake.
        Missed reminders are recovered when you return.
      </p>
      {editing && (
        <AlarmEditor
          alarm={editing === "new" ? undefined : editing}
          zone={planner.preferences.timezone}
          onClose={() => setEditing(null)}
        />
      )}
      <Modal
        open={!!removing}
        onClose={() => setRemoving(null)}
        title="Delete this alarm?"
        description="Its pending reminders will also be dismissed."
      >
        <p>{removing?.title}</p>
        <div className="button-row">
          <Button
            tone="danger"
            disabled={action.pending}
            onClick={async () => {
              if (
                await action.run("planner.delete", {
                  kind: "alarm",
                  id: removing?.id,
                })
              )
                setRemoving(null);
            }}
          >
            Delete alarm
          </Button>
          <Button onClick={() => setRemoving(null)}>Cancel</Button>
        </div>
      </Modal>
    </section>
  );
}

export function AlarmEditor({
  alarm,
  zone,
  onClose,
}: {
  alarm?: Alarm;
  zone: string;
  onClose: () => void;
}) {
  const action = useAction();
  const [title, setTitle] = useState(alarm?.title ?? ""),
    [due, setDue] = useState(
      localInput(
        alarm && alarm.due > Date.now() / 1000
          ? alarm.due
          : Date.now() / 1000 + 3600,
        zone,
      ),
    ),
    [weekdays, setWeekdays] = useState<number[]>(alarm?.weekdays ?? []),
    [enabled, setEnabled] = useState(alarm?.enabled ?? true);
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (
      await action.run("planner.alarm.save", {
        id: alarm?.id,
        title: title.trim() || "Alarm",
        localDue: due,
        weekdays,
        enabled,
      })
    )
      onClose();
  }
  return (
    <Modal open onClose={onClose} title={alarm ? "Edit alarm" : "Add alarm"}>
      <form onSubmit={(e) => void submit(e)}>
        <Field label="Alarm name">
          <input
            autoFocus
            placeholder="For example, stretch break"
            maxLength={240}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <Field label="Date and time" hint={zone}>
          <input
            required
            type="datetime-local"
            value={due}
            onChange={(e) => setDue(e.target.value)}
          />
        </Field>
        <fieldset className="weekday-field">
          <legend>Repeat on</legend>
          <div>
            {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(
              (day, index) => (
                <label key={day}>
                  <input
                    type="checkbox"
                    checked={weekdays.includes(index)}
                    onChange={(e) =>
                      setWeekdays(
                        e.target.checked
                          ? [...weekdays, index]
                          : weekdays.filter((d) => d !== index),
                      )
                    }
                  />
                  <span>{day}</span>
                </label>
              ),
            )}
          </div>
          <small>Leave all days clear for a one-time alarm.</small>
        </fieldset>
        <Toggle label="Alarm enabled" checked={enabled} onChange={setEnabled} />
        <div className="button-row">
          <Button tone="primary" type="submit" disabled={action.pending}>
            Save alarm
          </Button>
          <Button onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </Modal>
  );
}
