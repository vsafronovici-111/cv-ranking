import "./Chat.css";

function ChatHistory({ messages }) {
  return (
    <ul className="chat-history">
      {messages.map((message) => (
        <li key={message.id} className={`chat-message chat-message--${message.sender}`}>
          {message.text}
        </li>
      ))}
    </ul>
  );
}

export default ChatHistory;
