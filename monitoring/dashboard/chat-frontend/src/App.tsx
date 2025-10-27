import React from 'react';
import { useAuth } from './hooks/useAuth';
import { useSocket } from './hooks/useSocket';
import { AuthModal } from './components/AuthModal';
import { ChatInterface } from './components/ChatInterface';
import './App.css';

function App() {
  const { user, token, loading, login, register, logout } = useAuth();
  const { connected, messages, sendMessage, clearChat } = useSocket(token);

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
      <ChatInterface
        messages={messages}
        connected={connected}
        onSendMessage={sendMessage}
        onClearChat={clearChat}
        onLogout={logout}
      />
    </div>
  );
}

export default App;
