import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import ConversationList from "../components/ConversationList.jsx";
import CreateConversationModal from "../components/CreateConversationModal.jsx";
import { API_BASE_URL } from "../config.js";
import "./ConversationsPage.css";

function ConversationsPage() {
  const { userId } = useParams();
  const [conversations, setConversations] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const loadConversations = useCallback(() => {
    setLoading(true);
    setError(null);

    return fetch(`${API_BASE_URL}/conversations?user_id=${encodeURIComponent(userId)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load conversations (${res.status})`);
        return res.json();
      })
      .then(setConversations)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [userId]);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  const createConversation = useCallback(
    (name) =>
      fetch(`${API_BASE_URL}/conversations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, name: name || null }),
      })
        .then((res) => {
          if (!res.ok) throw new Error(`Failed to create conversation (${res.status})`);
          return res.json();
        })
        .then((conversation) => {
          loadConversations();
          return conversation;
        }),
    [userId, loadConversations],
  );

  return (
    <div>
      <div className="conversations-page__header">
        <h1>Conversations for {userId}</h1>
        <button type="button" onClick={() => setIsCreateOpen(true)}>
          New conversation
        </button>
      </div>
      {loading && <p>Loading...</p>}
      {error && <p className="conversation-list__error">{error}</p>}
      {!loading && !error && <ConversationList conversations={conversations} />}
      {isCreateOpen && (
        <CreateConversationModal onCreate={createConversation} onClose={() => setIsCreateOpen(false)} />
      )}
    </div>
  );
}

export default ConversationsPage;
