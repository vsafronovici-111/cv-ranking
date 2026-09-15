import { useCallback, useEffect, useRef, useState } from "react";
import { WS_URL } from "../config.js";
import ChatBox from "./ChatBox.jsx";
import ChatHistory from "./ChatHistory.jsx";

function Chat() {
  const [messages, setMessages] = useState([]);
  const socketRef = useRef(null);
  const nextIdRef = useRef(0);

  useEffect(() => {
    const socket = new WebSocket(WS_URL);
    socket.onmessage = (event) => {
      setMessages((prev) => [...prev, { id: nextIdRef.current++, sender: "server", text: event.data }]);
    };
    socketRef.current = socket;

    return () => socket.close();
  }, []);

  const sendMessage = useCallback((text) => {
    setMessages((prev) => [...prev, { id: nextIdRef.current++, sender: "user", text }]);
    socketRef.current?.send(text);
  }, []);

  return (
    <div>
      <ChatHistory messages={messages} />
      <ChatBox onSend={sendMessage} />
    </div>
  );
}

export default Chat;
