import { useEffect, useState } from "react";
import {
  AlarmClock,
  Bell,
  History,
  ListTodo,
  Mic,
  Minus,
  Maximize2,
  Settings as SettingsIcon,
  Timer,
  Trophy,
  X,
} from "lucide-react";
import { useBackend, isNative, isPreview, native } from "./lib/backend";
import { useApp } from "./store";
import { pages, type Page } from "./types";
import { Button, Modal, WaveMark, useAction } from "./components/ui";
import { DictationPage, Onboarding } from "./pages/Dictation";
import { HistoryPage } from "./pages/History";
import { TasksPage, FocusPage, AlarmsPage } from "./pages/Planner";
import { ContestsPage } from "./pages/Contests";
import { SettingsPage } from "./pages/Settings";
import { NotificationList } from "./components/Notifications";
import { UpdateShortcut } from "./components/Updates";
import { useUpdateConnection } from "./lib/updates";

const icons = [Mic, History, ListTodo, Timer, AlarmClock, Trophy, SettingsIcon];
export default function App() {
  useBackend();
  useUpdateConnection();
  const page = useApp((s) => s.page),
    setPage = useApp((s) => s.setPage),
    data = useApp((s) => s.data);
  const error = useApp((s) => s.error),
    settingsRecovery = useApp((s) => s.settingsRecovery),
    connected = useApp((s) => s.connected),
    toast = useApp((s) => s.toast);
  const count = useApp((s) => s.planner?.pendingCount ?? 0);
  const inbox = useApp((s) => s.inboxOpen);
  const setInbox = (inboxOpen: boolean) => useApp.setState({ inboxOpen });
  useEffect(() => {
    document.getElementById("main-content")?.scrollTo({ top: 0 });
  }, [page]);
  if (!isNative() && !isPreview())
    return (
      <main className="launch-screen">
        <WaveMark size={42} />
        <h1>VoicePrompt</h1>
        <p>Open VoicePrompt on your Windows desktop.</p>
        <a className="button" href="?preview=1">
          Explore a sample preview
        </a>
      </main>
    );
  const views: Record<Page, React.ReactNode> = {
    Dictation: <DictationPage />,
    History: <HistoryPage />,
    Tasks: <TasksPage />,
    "Focus timer": <FocusPage />,
    Alarms: <AlarmsPage />,
    Contests: <ContestsPage />,
    Settings: <SettingsPage />,
  };
  return (
    <div className="app-shell">
      <aside className="rail">
        <div className="brand" data-tauri-drag-region>
          <WaveMark size={25} />
          <strong>VoicePrompt</strong>
        </div>
        <nav aria-label="Main navigation">
          {pages.map((item, index) => {
            const Icon = icons[index];
            return (
              <button
                key={item}
                className={`nav-item ${page === item ? "selected" : ""} ${item === "Settings" ? "settings-nav" : ""}`}
                aria-current={page === item ? "page" : undefined}
                onClick={() => setPage(item)}
              >
                <Icon size={20} />
                <span>{item}</span>
              </button>
            );
          })}
        </nav>
      </aside>
      <div className="titlebar" data-tauri-drag-region>
        <div data-tauri-drag-region />
        <UpdateShortcut />
        <Button
          tone="ghost"
          aria-label={`Pending reminders${count ? `: ${count}` : ""}`}
          onClick={() => setInbox(true)}
        >
          <Bell size={15} />
          {count > 0 && (
            <span className="count">{count > 9 ? "9+" : count}</span>
          )}
        </Button>
        <Button
          tone="ghost"
          aria-label="Minimize"
          onClick={() => void native("window_action", { action: "minimize" })}
        >
          <Minus size={15} />
        </Button>
        <Button
          tone="ghost"
          aria-label="Maximize or restore"
          onClick={() => void native("window_action", { action: "maximize" })}
        >
          <Maximize2 size={13} />
        </Button>
        <Button
          tone="ghost"
          className="close-window"
          aria-label="Close to tray"
          onClick={() => void native("window_action", { action: "close" })}
        >
          <X size={16} />
        </Button>
      </div>
      <main className="workspace" id="main-content">
        {isPreview() && (
          <div className="preview-note">
            Sample preview · microphone, native shortcuts, and provider
            connections are inactive.
          </div>
        )}
        {error && (
          <div role="alert" className="notice danger">
            <span>{error.replace(/^Error: /, "")}</span>
            {settingsRecovery && <SettingsRecovery />}
            <Button
              onClick={() =>
                void native("restart_engine").catch((e) =>
                  useApp.setState({ error: String(e) }),
                )
              }
            >
              Restart engine
            </Button>
          </div>
        )}
        {!data ? (
          <div className="loading">
            <WaveMark size={34} />
            <p>
              {error
                ? "The app is waiting for its voice engine."
                : "Opening your workspace…"}
            </p>
          </div>
        ) : (
          <>
            <div className={!connected ? "disconnected-content" : ""}>
              {views[page]}
            </div>
            <Onboarding />
          </>
        )}
      </main>
      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
      <Modal
        open={inbox}
        onClose={() => setInbox(false)}
        title="Notifications"
        description="Pending reminders stay here until you dismiss or snooze them."
      >
        <NotificationList />
      </Modal>
    </div>
  );
}

function SettingsRecovery() {
  const [confirm, setConfirm] = useState(false);
  const action = useAction();
  async function recover(mode: "backup" | "defaults") {
    if (await action.run("configuration.recover", { mode })) {
      setConfirm(false);
      await native("restart_engine").catch((error) =>
        useApp.setState({ error: String(error) }),
      );
    }
  }
  return (
    <>
      <Button disabled={action.pending} onClick={() => void recover("backup")}>
        Restore settings backup
      </Button>
      <Button disabled={action.pending} onClick={() => setConfirm(true)}>
        Start with defaults
      </Button>
      <Modal
        open={confirm}
        onClose={() => setConfirm(false)}
        title="Recover with default settings"
        description="The unreadable settings file will be kept. Your history, tasks, alarms, and downloaded models remain available. Microphone setup will open again."
      >
        <Button
          disabled={action.pending}
          onClick={() => void recover("defaults")}
        >
          Keep original file and use defaults
        </Button>
      </Modal>
    </>
  );
}
