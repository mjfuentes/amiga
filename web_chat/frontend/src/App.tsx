import React from 'react';
import { useAuth } from './hooks/useAuth';
import { useSocket } from './hooks/useSocket';
import { useChat } from './hooks/useChat';
import AuthModal from './components/AuthModal';
import ChatWindow from './components/ChatWindow';
import './App.css';

function App() {
  const { token, user, isAuthenticated, login, register, logout } = useAuth();
  const { socket, connected } = useSocket(token);
  const { messages, sendMessage, isTyping } = useChat(socket);

  if (!isAuthenticated || !user) {
    return <AuthModal onLogin={login} onRegister={register} />;
  }

  return (
    <div className="App">
      <ChatWindow
        messages={messages}
        isTyping={isTyping}
        connected={connected}
        username={user.username}
        onSendMessage={sendMessage}
        onLogout={logout}
      />
    </div>
  );
}

export default App;
