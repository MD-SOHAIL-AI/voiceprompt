import { useEffect, useState } from "react";
import { Copy, Search, Trash2 } from "lucide-react";
import { dateTime } from "../lib/format";
import { request } from "../lib/backend";
import { useApp, notify } from "../store";
import type { HistoryItem } from "../types";
import { Button, Empty, Modal, useAction } from "../components/ui";

export function HistoryPage() {
  const [query, setQuery] = useState(""),
    [items, setItems] = useState<HistoryItem[]>([]),
    [total, setTotal] = useState(0),
    [offset, setOffset] = useState(0),
    [previous, setPrevious] = useState<number[]>([]),
    [clear, setClear] = useState(false),
    [detail, setDetail] = useState<HistoryItem | null>(null),
    [revision, setRevision] = useState(0);
  const action = useAction();
  const limit = useApp((s) => s.settings?.max_history ?? 0);
  useEffect(() => {
    if (offset && offset >= total) {
      setOffset(0);
      setPrevious([]);
    }
  }, [offset, total]);
  useEffect(() => {
    let alive = true;
    const timeout = setTimeout(() => {
      void request<{ items: HistoryItem[]; total: number }>("history.list", {
        query,
        offset,
      })
        .then((result) => {
          if (alive) {
            setItems(result.items);
            setTotal(result.total);
          }
        })
        .catch((error) => {
          if (alive) notify(String(error));
        });
    }, 180);
    return () => {
      alive = false;
      clearTimeout(timeout);
    };
  }, [query, offset, revision]);
  return (
    <section>
      <header className="page-heading">
        <h1>History</h1>
        <Button disabled={action.pending} onClick={() => setClear(true)}>
          <Trash2 size={16} />
          Clear history
        </Button>
      </header>
      <div className="search-field">
        <Search size={17} />
        <input
          aria-label="Search history"
          placeholder="Search your transcripts"
          value={query}
          onChange={(e) => {
            setOffset(0);
            setPrevious([]);
            setQuery(e.target.value);
          }}
        />
      </div>
      {!limit && (
        <p className="notice">
          New transcripts are not being saved. Existing history stays until you
          clear it.
        </p>
      )}
      <div className="history-list">
        {items.length ? (
          items.map((item) => (
            <article className="history-item" key={item.id}>
              <div className="history-meta">
                <time>{dateTime(Date.parse(item.created_at) / 1000)}</time>
                <span>
                  {item.source} · {Math.round(item.duration_seconds)}s
                </span>
              </div>
              <p>{item.text}</p>
              {item.truncated && (
                <Button
                  disabled={action.pending}
                  onClick={async () => {
                    const full = await action.run<HistoryItem>("history.item", {
                      id: item.id,
                    });
                    if (full) setDetail(full);
                  }}
                >
                  Show full transcript
                </Button>
              )}
              <div className="button-row">
                <Button
                  disabled={action.pending}
                  onClick={async () => {
                    const full = item.truncated
                      ? await action.run<HistoryItem>("history.item", {
                          id: item.id,
                        })
                      : item;
                    if (
                      full &&
                      (await action.run("clipboard.copy", { text: full.text }))
                    )
                      notify("Text copied.");
                  }}
                >
                  <Copy size={15} />
                  Copy
                </Button>
                <Button
                  tone="ghost"
                  disabled={action.pending}
                  onClick={async () => {
                    if (await action.run("history.delete", { id: item.id }))
                      setRevision((r) => r + 1);
                  }}
                >
                  <Trash2 size={15} />
                  Delete
                </Button>
              </div>
            </article>
          ))
        ) : (
          <Empty
            title={query ? "No matching transcripts" : "No saved transcripts"}
          >
            Completed recordings appear here when history is enabled.
          </Empty>
        )}
      </div>
      <div className="pagination">
        <Button
          disabled={!offset}
          onClick={() => {
            setOffset(previous.at(-1) ?? 0);
            setPrevious(previous.slice(0, -1));
          }}
        >
          Previous
        </Button>
        <span>
          {total
            ? `${offset + 1}–${Math.min(offset + items.length, total)} of ${total}`
            : "0 transcripts"}
        </span>
        <Button
          disabled={!items.length || offset + items.length >= total}
          onClick={() => {
            setPrevious([...previous, offset]);
            setOffset(offset + items.length);
          }}
        >
          Next
        </Button>
      </div>
      <Modal
        open={!!detail}
        onClose={() => setDetail(null)}
        title="Saved transcript"
        description="The complete transcript stored on this device."
      >
        <p className="transcript-text">{detail?.text}</p>
      </Modal>
      <Modal
        open={clear}
        onClose={() => setClear(false)}
        title="Clear saved transcripts?"
        description="This removes transcript history from this computer. Your tasks, settings, and models are kept."
      >
        <div className="button-row">
          <Button
            tone="danger"
            disabled={action.pending}
            onClick={async () => {
              if (await action.run("history.clear")) {
                setClear(false);
                setOffset(0);
                setRevision((r) => r + 1);
              }
            }}
          >
            Clear history
          </Button>
          <Button onClick={() => setClear(false)}>Cancel</Button>
        </div>
      </Modal>
    </section>
  );
}
