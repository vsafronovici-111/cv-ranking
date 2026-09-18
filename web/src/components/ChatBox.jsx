import { useState } from "react";
import "./Chat.css";

function ChatBox({ onSend }) {
  const [text, setText] = useState("");

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!text.trim()) return;
    onSend(text);
    setText("");
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit(event);
    }
  };

  return (
    <form className="chat-box" onSubmit={handleSubmit}>
      <textarea
        className="chat-box__input"
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={handleKeyDown}
        rows={8}
      />
      <button className="chat-box__send" type="submit">
        Send
      </button>
    </form>
  );
}

export default ChatBox;
