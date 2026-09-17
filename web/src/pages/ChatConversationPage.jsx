import { useParams } from "react-router-dom";
import Chat from "../components/Chat.jsx";

function ChatConversationPage() {
  const { conversationId } = useParams();

  return (
    <div>
      <Chat conversationId={conversationId} />
    </div>
  );
}

export default ChatConversationPage;
