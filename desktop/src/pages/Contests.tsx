import { useState } from "react";
import { ExternalLink, RefreshCw, Settings2 } from "lucide-react";
import { openLink } from "../lib/backend";
import { dateTime } from "../lib/format";
import { notify, useApp } from "../store";
import { platformNames, type Contest, type Platform } from "../types";
import {
  Button,
  Empty,
  Field,
  Modal,
  Toggle,
  useAction,
} from "../components/ui";
import { usePaged } from "./Planner";

export function ContestsPage() {
  const planner = useApp((s) => s.planner),
    action = useAction();
  const [connection, setConnection] = useState(false),
    [preferences, setPreferences] = useState(false),
    [filter, setFilter] = useState("all");
  const paged = usePaged<Contest>(
    "contest",
    planner?.contests ?? [],
    planner?.counts.contests ?? 0,
  );
  if (!planner) return <Empty title="Contest schedules are unavailable" />;
  const items = paged.items
    .filter((c) => filter === "all" || c.platform === filter)
    .filter((c) => c.end > planner.now);
  return (
    <section>
      <header className="page-heading">
        <h1>Contests</h1>
        <div className="button-row">
          <Button onClick={() => setPreferences(true)}>
            <Settings2 size={16} />
            Reminders
          </Button>
          <Button
            disabled={planner.syncing || action.pending}
            onClick={async () => {
              const result = await action.run<{ started: boolean }>(
                "planner.contests.refresh",
              );
              if (result && !result.started)
                notify(
                  "A refresh is already running, or the service needs a short wait.",
                );
            }}
          >
            <RefreshCw size={16} className={planner.syncing ? "spin" : ""} />
            {planner.syncing ? "Refreshing…" : "Refresh"}
          </Button>
        </div>
      </header>
      <div className="contest-toolbar">
        <Field label="Platform">
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All platforms</option>
            {Object.entries(platformNames).map(([key, name]) => (
              <option key={key} value={key}>
                {name}
              </option>
            ))}
          </select>
        </Field>
        <Button onClick={() => setConnection(true)}>
          {planner.preferences.clist_username
            ? "Manage CLIST connection"
            : "Connect CLIST"}
        </Button>
      </div>
      <p className="muted">
        The island reminds you {planner.preferences.contest_minutes} minutes
        before a contest and when it starts.
      </p>
      <div className="contest-list">
        {items.map((contest) => (
          <article className="contest-item" key={contest.id}>
            <span className={`platform-tag platform-${contest.platform}`}>
              {platformNames[contest.platform]}
            </span>
            <div className="contest-body">
              <h2>{contest.name}</h2>
              <p>
                {dateTime(contest.start, planner.preferences.timezone)} ·{" "}
                {Math.round((contest.end - contest.start) / 60)} min
              </p>
              <small>
                {contest.start <= planner.now ? "Running now" : "Upcoming"}
                {contest.muted ? " · Reminders muted" : ""}
              </small>
            </div>
            <div className="contest-actions">
              <Button
                disabled={action.pending}
                onClick={() =>
                  void action.run("planner.contests.mute", { id: contest.id })
                }
              >
                {contest.muted ? "Enable reminders" : "Mute reminders"}
              </Button>
              <Button
                onClick={() =>
                  void openLink(contest.url).catch((error) =>
                    notify(String(error)),
                  )
                }
              >
                <ExternalLink size={15} />
                Open contest
              </Button>
            </div>
          </article>
        ))}
        {!items.length && (
          <Empty title="No contests to show">
            Codeforces needs no key. Connect your CLIST account for LeetCode,
            CodeChef, and AtCoder.
          </Empty>
        )}
      </div>
      {paged.footer}
      <div className="source-status">
        {planner.sources.map((source) => (
          <p key={source.id}>
            <strong>{source.id === "clist" ? "CLIST" : "Codeforces"}</strong> ·{" "}
            {source.error ||
              `Updated ${dateTime(source.updated, planner.preferences.timezone)}`}
            {source.error && source.updated
              ? ` · Cached schedule from ${dateTime(source.updated, planner.preferences.timezone)}`
              : ""}
          </p>
        ))}
      </div>
      <Modal
        open={connection}
        onClose={() => setConnection(false)}
        title="Connect CLIST"
        description="Use your CLIST username and API key. The key is saved in Windows Credential Manager."
      >
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const fields = new FormData(form);
            if (
              await action.run("planner.contests.connect", {
                username: fields.get("username"),
                key: fields.get("key"),
              })
            ) {
              form.reset();
              setConnection(false);
              notify("Connection saved. Refreshing contest schedules.");
            }
          }}
        >
          <Field label="CLIST username">
            <input
              name="username"
              required
              defaultValue={planner.preferences.clist_username}
              autoComplete="off"
            />
          </Field>
          <Field label="API key">
            <input
              name="key"
              type="password"
              required
              autoComplete="off"
              spellCheck={false}
            />
          </Field>
          <div className="button-row">
            <Button tone="primary" type="submit" disabled={action.pending}>
              Save and refresh
            </Button>
            <Button onClick={() => setConnection(false)}>Cancel</Button>
          </div>
        </form>
      </Modal>
      {preferences && (
        <ContestPreferences onClose={() => setPreferences(false)} />
      )}
    </section>
  );
}
function ContestPreferences({ onClose }: { onClose: () => void }) {
  const prefs = useApp((s) => s.planner!.preferences),
    action = useAction();
  const [lead, setLead] = useState(prefs.contest_minutes),
    [platforms, setPlatforms] = useState<Platform[]>(prefs.platforms),
    [summary, setSummary] = useState(prefs.daily_summary),
    [hour, setHour] = useState(prefs.summary_hour);
  return (
    <Modal open onClose={onClose} title="Contest reminders">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (
            await action.run("planner.preferences", {
              contest_minutes: lead,
              platforms,
              daily_summary: summary,
              summary_hour: hour,
            })
          )
            onClose();
        }}
      >
        <Field label="Remind me before start (minutes)">
          <input
            required
            type="number"
            min="0"
            max="10080"
            value={lead}
            onChange={(e) => setLead(Number(e.target.value))}
          />
        </Field>
        <fieldset>
          <legend>Platforms</legend>
          {Object.entries(platformNames).map(([key, name]) => (
            <Toggle
              key={key}
              label={name}
              checked={platforms.includes(key as Platform)}
              onChange={(checked) =>
                setPlatforms(
                  checked
                    ? [...platforms, key as Platform]
                    : platforms.filter((p) => p !== key),
                )
              }
            />
          ))}
        </fieldset>
        <Toggle
          label="Daily contest summary"
          checked={summary}
          onChange={setSummary}
        />
        {summary && (
          <Field label="Summary hour (0–23)">
            <input
              type="number"
              required
              min="0"
              max="23"
              value={hour}
              onChange={(e) => setHour(Number(e.target.value))}
            />
          </Field>
        )}
        <div className="button-row">
          <Button tone="primary" type="submit" disabled={action.pending}>
            Save reminders
          </Button>
          <Button onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </Modal>
  );
}
