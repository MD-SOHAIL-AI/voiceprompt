import {
  AlarmClock,
  Bell,
  Check,
  ExternalLink,
  ListTodo,
  Timer,
  Trophy,
} from "lucide-react";
import { openLink } from "../lib/backend";
import { dateTime } from "../lib/format";
import { useApp } from "../store";
import { platformNames, type Notice } from "../types";
import { Button, Empty, useAction } from "./ui";

export function noticeDescription(item: Notice, now: number) {
  if (item.contest) {
    const seconds = item.contest.start - now;
    return `${platformNames[item.contest.platform]} · ${seconds > 0 ? `Starts in ${Math.max(1, Math.ceil(seconds / 60))} min` : "Contest has started"}`;
  }
  return item.detail;
}
export function NotificationList({ compact = false }: { compact?: boolean }) {
  const planner = useApp((s) => s.planner),
    action = useAction();
  const notices = planner?.notifications ?? [];
  const icons = {
    alarm: AlarmClock,
    timer: Timer,
    task: ListTodo,
    contest: Trophy,
    summary: Bell,
  };
  return (
    <div className={`notification-list ${compact ? "compact" : ""}`}>
      <h2 className="notification-count">
        {planner?.pendingCount ?? 0} pending
      </h2>
      {notices.length ? (
        notices.map((item) => {
          const Icon = icons[item.kind] ?? Bell;
          return (
            <article
              className={`notification-item kind-${item.kind}`}
              key={`${item.id}:${item.revision}`}
            >
              <Icon size={21} />
              <div className="notification-content">
                <strong>{item.title}</strong>
                <p>
                  {noticeDescription(item, planner?.now ?? Date.now() / 1000)}
                </p>
                {item.contest && (
                  <small>
                    {dateTime(
                      item.contest.start,
                      planner?.preferences.timezone,
                    )}
                  </small>
                )}
                <div className="button-row">
                  {item.url && (
                    <Button
                      tone="primary"
                      disabled={action.pending}
                      onClick={() =>
                        void openLink(item.url).catch(() => undefined)
                      }
                    >
                      <ExternalLink size={14} />
                      {item.contest ? "Open contest" : "Open"}
                    </Button>
                  )}
                  <Button
                    disabled={action.pending}
                    onClick={() =>
                      void action.run("planner.notification.act", {
                        id: item.id,
                        revision: item.revision,
                        snooze: true,
                      })
                    }
                  >
                    Snooze 5 min
                  </Button>
                  <Button
                    disabled={action.pending}
                    onClick={() =>
                      void action.run("planner.notification.act", {
                        id: item.id,
                        revision: item.revision,
                        snooze: false,
                      })
                    }
                  >
                    <Check size={14} />
                    Dismiss
                  </Button>
                </div>
              </div>
            </article>
          );
        })
      ) : (
        <Empty title="You’re all caught up">
          Timers, alarms, tasks, and contest reminders will appear here.
        </Empty>
      )}
      {(planner?.pendingCount ?? 0) > notices.length && (
        <p className="muted">
          More reminders will appear as you acknowledge these.
        </p>
      )}
    </div>
  );
}
