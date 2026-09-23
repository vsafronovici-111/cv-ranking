import { BrowserRouter, Route, Routes } from "react-router-dom";
import ChatConversationPage from "./pages/ChatConversationPage.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import ConversationsPage from "./pages/ConversationsPage.jsx";
import ChatConversationPageV2 from "./v2/pages/ChatConversationPage.jsx";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/:userId/chats" element={<ConversationsPage />} />
        <Route path="/chat/:conversationId" element={<ChatConversationPage />} />
        <Route path="/chat/v2/:conversationId" element={<ChatConversationPageV2 />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
