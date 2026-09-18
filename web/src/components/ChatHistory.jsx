import "./Chat.css";

function formatTimestamp(isoString) {
  const date = new Date(isoString);
  const day = String(date.getDate()).padStart(2, "0");
  const month = date.toLocaleString("en-US", { month: "short" });
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${day}/${month} ${hours}:${minutes}`;
}

function ChatHistory({ messages }) {
  return (
    <ul className="chat-history">
      {messages.map((message) => (
        <li key={message.id} className={`chat-message chat-message--${message.sender}`}>
          <div className="chat-message__text">{message.text}</div>
          {message.created_at && !message.pending && (
            <time className="chat-message__time" dateTime={message.created_at}>
              {formatTimestamp(message.created_at)}
            </time>
          )}
        </li>
      ))}
    </ul>
  );
}

export default ChatHistory;
