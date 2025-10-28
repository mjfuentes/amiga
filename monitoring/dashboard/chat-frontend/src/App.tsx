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
  const { connected, messages, sendMessage, clearChat } = useSocket(token);
  const [chatViewActive, setChatViewActive] = useState(false);

  // Show sidebar when chat view is active or messages exist
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
      />
      <SessionsSidebar visible={showSidebar} />
    </div>
  );
}

export default App;
