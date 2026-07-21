import { useState } from "react";
import { ChevronDown, ChevronRight, Clipboard, RotateCcw, TriangleAlert } from "lucide-react";
import type { ChatMessage } from "../types";
import { ProductSearchResult } from "./ProductSearchResult";
import { getTaobaoArtifact } from "./productSearchViewModel";

interface Props {
  message: ChatMessage;
  onRetry?: () => void;
}

export function MessageItem({ message, onRetry }: Props) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const isProgress = message.type === "progress";
  const isError = message.type === "error";
  const taobaoArtifact = getTaobaoArtifact(message);
  const details = Object.fromEntries(
    Object.entries(message.metadata || {}).filter(([key]) => key !== "taobao_product_search")
  );
  const hasDetails = Object.keys(details).some((key) => details[key] !== "" && details[key] != null);

  return (
    <article className={`message message-${message.type} role-${message.role}`}>
      <div className="message-content">
        {isError ? <TriangleAlert size={16} aria-hidden="true" /> : null}
        <p>{message.content}</p>
        {taobaoArtifact ? <ProductSearchResult artifact={taobaoArtifact} /> : null}
      </div>
      {isProgress && hasDetails ? (
        <button className="detail-toggle" onClick={() => setDetailsOpen((value) => !value)}>
          {detailsOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          {detailsOpen ? "收起详细日志" : "查看详细日志"}
        </button>
      ) : null}
      {detailsOpen ? <pre className="message-details">{JSON.stringify(details, null, 2)}</pre> : null}
      {isError ? (
        <div className="message-actions">
          <button title="重新执行" onClick={onRetry}><RotateCcw size={15} /></button>
          <button title="复制错误" onClick={() => void navigator.clipboard.writeText(message.content)}><Clipboard size={15} /></button>
        </div>
      ) : null}
    </article>
  );
}
