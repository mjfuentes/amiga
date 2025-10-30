import React, { useState } from 'react';
import { useAuth } from './hooks/useAuth';
import { useSocket } from './hooks/useSocket';
import { AuthModal } from './components/AuthModal';
import { ChatInterface } from './components/ChatInterface';
import { TaskSidebar } from './components/TaskSidebar';
import { SessionsSidebar } from './components/SessionsSidebar';
import './App.css';

function App() {
  const { user, token, loading, login, register, logout } = useAuth();
  const { connected, messages, sendMessage, clearChat, totalTokens } = useSocket(token);
  const [chatViewActive, setChatViewActive] = useState(false);

  /**
   * SIDEBAR VISIBILITY CONTROL (Navigation Pattern)
   * ===============================================
   *
   * Sidebars (TaskSidebar and SessionsSidebar) are HIDDEN on the landing page
   * and SHOWN when the user begins interacting with the chat.
   *
   * Visibility conditions:
   * 1. chatViewActive: User typed anything into input (triggers chat view)
   * 2. messages.length > 0: User sent at least one message
   *
   * UX Flow:
   * - Landing page (home screen): Clean, centered input with AMIGA logo, NO sidebars
   * - User types anything → chatViewActive becomes true → sidebars appear
   * - After /clear: Returns to landing page (chatViewActive=false, messages=[])
   *
   * This creates an intentional "reveal" pattern where the full interface appears
   * only after the user engages with the input.
   */
  const showSidebar = chatViewActive || messages.length > 0;

  if (loading) {
    return (
      <div className="app-loading">
        <div className="spinner"></div>
        <p>Loading...</p>
      </div>
    );
  }

  if (!user || !token) {
    return <AuthModal onLogin={login} onRegister={register} />;
  }

  return (
    <div className="App">
      <TaskSidebar visible={showSidebar} />
      <ChatInterface
        messages={messages}
        connected={connected}
        onSendMessage={sendMessage}
        onClearChat={clearChat}
        onLogout={logout}
        chatViewActive={chatViewActive}
        setChatViewActive={setChatViewActive}
        totalTokens={totalTokens}
      />
      <SessionsSidebar visible={showSidebar} />
    </div>
  );
}

export default App;
