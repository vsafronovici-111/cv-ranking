import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL, WS_URL } from "../config.js";
import ChatBox from "./ChatBox.jsx";
import ChatHistory from "./ChatHistory.jsx";

function Chat({ conversationId }) {
  const [messages, setMessages] = useState([]);
  const nextIdRef = useRef(0);

  useEffect(() => {
    if (!conversationId) return;

    fetch(`${API_BASE_URL}/conversations/${conversationId}/messages`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load messages (${res.status})`);
        return res.json();
      })
      .then((fetched) => {
        setMessages(
          fetched.map((message) => ({
            id: message.id,
            sender: message.role === "user" ? "user" : "server",
            text: message.content,
          })),
        );
        nextIdRef.current = fetched.reduce((max, message) => Math.max(max, message.id), 0) + 1;
      })
      .catch(() => {});
  }, [conversationId]);

  useEffect(() => {
    const socket = new WebSocket(WS_URL);
    socket.onmessage = (event) => {
      setMessages((prev) => [...prev, { id: nextIdRef.current++, sender: "server", text: event.data }]);
    };

    return () => socket.close();
  }, []);

  const sendMessage = useCallback(
    (text) => {
      if (!conversationId) return;

      fetch(`${API_BASE_URL}/conversations/${conversationId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: "user", content: text }),
      })
        .then((res) => {
          if (!res.ok) throw new Error(`Failed to send message (${res.status})`);
          return res.json();
        })
        .then((message) => {
          setMessages((prev) => [...prev, { id: message.id, sender: "user", text: message.content }]);
        })
        .catch((err) => console.error(err));
    },
    [conversationId],
  );

  return (
    <div>
      <ChatHistory messages={messages} />
      <ChatBox onSend={sendMessage} />
    </div>
  );
}

export default Chat;
