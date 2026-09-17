import { Link } from "react-router-dom";
import "./ConversationList.css";

function ConversationList({ conversations }) {
  if (conversations.length === 0) {
    return <p className="conversation-list__empty">No conversations yet.</p>;
  }

  return (
    <ul className="conversation-list">
      {conversations.map((conversation) => (
        <li key={conversation.id} className="conversation-list__item">
          <Link to={`/chat/${conversation.id}`} className="conversation-list__name">
            {conversation.name ?? `Conversation #${conversation.id}`}
          </Link>
          <span className="conversation-list__created">{new Date(conversation.created_at).toLocaleString()}</span>
        </li>
      ))}
    </ul>
  );
}

export default ConversationList;
