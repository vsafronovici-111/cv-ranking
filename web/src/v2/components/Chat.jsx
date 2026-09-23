import { useCallback, useEffect, useState } from "react";
import ChatBox from "../../components/ChatBox.jsx";
import ChatHistory from "../../components/ChatHistory.jsx";
import { API_BASE_URL, WS_URL } from "../../config.js";

function toChatMessage(message) {
  return {
    id: message.id,
    sender: message.role === "user" ? "user" : "server",
    text: message.content,
    created_at: message.created_at,
  };
}

function insertSorted(messages, message) {
  return [...messages, message].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
}

function upsertMessage(messages, message) {
  return insertSorted(messages.filter((existing) => existing.id !== message.id), message);
}

function pendingReplyFor(lastMessage) {
  return {
    id: `pending-${lastMessage.id}`,
    sender: "server",
    text: "Thinking ...",
    created_at: new Date().toISOString(),
    pending: true,
  };
}

// Invariant enforced after every change: the list ends with a "Thinking
// ..." placeholder whenever the last real message is from the user, and
// never otherwise (e.g. once the assistant's real reply arrives).
function reconcilePending(messages) {
  const withoutPending = messages.filter((message) => !message.pending);
  const last = withoutPending[withoutPending.length - 1];
  return last && last.sender === "user" ? insertSorted(withoutPending, pendingReplyFor(last)) : withoutPending;
}

// Matches the backend Redis Streams consumer's own fixed retry backoff
// (`_RETRY_BACKOFF_SECONDS` in redis_streams/consumer/chat_message_consumer.py).
const RECONNECT_DELAY_MS = 1000;

// v2 counterpart to `components/Chat.jsx`: message history is still read
// from the shared v1 `GET /conversations/{id}/messages` endpoint (that
// route isn't versioned), but sending a message posts to the v2 endpoint
// (Redis Streams + LangChain agent on the backend) and the assistant's
// reply arrives over the separate `/ws/v2/conversations/{id}` socket.
function ChatV2({ conversationId }) {
  const [messages, setMessages] = useState([]);

  useEffect(() => {
    if (!conversationId) return;

    fetch(`${API_BASE_URL}/conversations/${conversationId}/messages`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load messages (${res.status})`);
        return res.json();
      })
      .then((fetched) => {
        const sorted = fetched.map(toChatMessage).sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
        setMessages(reconcilePending(sorted));
      })
      .catch(() => {});
  }, [conversationId]);

  useEffect(() => {
    if (!conversationId) return;

    let disposed = false;
    let socket;
    let reconnectTimer;

    const connect = () => {
      socket = new WebSocket(`${WS_URL}/v2/conversations/${conversationId}`);

      socket.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        const incoming = toChatMessage(payload);
        setMessages((prev) => reconcilePending(upsertMessage(prev, incoming)));
      };

      // Fires on a clean close, a network drop, and a failed handshake
      // (onerror always precedes onclose) alike, so reconnecting here
      // covers a backend restart without a separate onerror handler.
      socket.onclose = () => {
        if (disposed) return;
        reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
      };
    };

    connect();

    return () => {
      disposed = true;
      clearTimeout(reconnectTimer);
      socket.close();
    };
  }, [conversationId]);

  const sendMessage = useCallback(
    (text) => {
      if (!conversationId) return;

      fetch(`${API_BASE_URL}/v2/conversations/${conversationId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: "user", content: text }),
      })
        .then((res) => {
          if (!res.ok) throw new Error(`Failed to send message (${res.status})`);
          return res.json();
        })
        .then((message) => {
          const userMessage = toChatMessage(message);
          setMessages((prev) => reconcilePending(upsertMessage(prev, userMessage)));
        })
        .catch((err) => console.error(err));
    },
    [conversationId],
  );

  return (
    <div className="chat-layout">
      <ChatHistory messages={messages} />
      <ChatBox onSend={sendMessage} />
    </div>
  );
}

export default ChatV2;
