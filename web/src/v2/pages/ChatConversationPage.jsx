import { useParams } from "react-router-dom";
import ChatV2 from "../components/Chat.jsx";

function ChatConversationPageV2() {
  const { conversationId } = useParams();

  return (
    <div>
      <ChatV2 conversationId={conversationId} />
    </div>
  );
}

export default ChatConversationPageV2;
