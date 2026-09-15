import { useEffect, useState } from "react";
import Chat from "../components/Chat.jsx";
import { API_BASE_URL } from "../config.js";

function ChatPage() {
  const [header, setHeader] = useState("");

  useEffect(() => {
    fetch(`${API_BASE_URL}/`)
      .then((res) => res.json())
      .then((data) => setHeader(data.message))
      .catch(() => setHeader("Failed to load"));
  }, []);

  return (
    <div>
      <h1>{header}</h1>
      <Chat />
    </div>
  );
}

export default ChatPage;
