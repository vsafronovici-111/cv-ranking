import { BrowserRouter, Route, Routes } from "react-router-dom";
import ChatConversationPage from "./pages/ChatConversationPage.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import ConversationsPage from "./pages/ConversationsPage.jsx";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/:userId/chats" element={<ConversationsPage />} />
        <Route path="/chat/:conversationId" element={<ChatConversationPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
