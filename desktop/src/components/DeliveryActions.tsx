import { ClipboardPaste, RotateCcw } from "lucide-react";
import { useApp } from "../store";
import { Button, useAction } from "./ui";

export function DeliveryActions() {
  const runtime = useApp((s) => s.runtime);
  const action = useAction();
  if (!runtime) return null;
  return <>
    {runtime.deliveryPending && <div className="delivery-notice" role="status"><strong>Text needs insertion</strong><p>{runtime.detail}</p></div>}
    <div className="button-row delivery-actions">
      {runtime.deliverySessionId && runtime.canPastePrevious && <Button disabled={runtime.working || action.pending} onClick={() => void action.run("dictation.paste", { sessionId: runtime.deliverySessionId })}><ClipboardPaste size={16} />Paste to previous app</Button>}
      {runtime.insertionReason === "clipboard_preservation" && <Button disabled={runtime.working || action.pending} onClick={() => void action.run("dictation.paste", { sessionId: runtime.deliverySessionId, replaceClipboard: true })}>Paste and replace clipboard</Button>}
      {runtime.canRetryRecent && <Button disabled={runtime.working || action.pending} onClick={() => void action.run("record.retry_recent")}><RotateCcw size={16} />Retry recognition</Button>}
      {runtime.canRestoreClipboard && <Button disabled={runtime.working || action.pending} onClick={() => void action.run("clipboard.restore")}>Restore previous clipboard</Button>}
      {runtime.deliveryPending && <Button tone="ghost" disabled={action.pending} onClick={() => void action.run("dictation.dismiss")}>Dismiss notice</Button>}
    </div>
  </>;
}
