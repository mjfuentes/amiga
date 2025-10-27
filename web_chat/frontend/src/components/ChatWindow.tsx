import React, { useRef, useEffect, useState } from 'react';
import MessageBubble from './MessageBubble';
import { Message } from '../hooks/useChat';

interface ChatWindowProps {
  messages: Message[];
  isTyping: boolean;
  connected: boolean;
  username: string;
  onSendMessage: (message: string) => void;
  onLogout: () => void;
}

const ChatWindow: React.FC<ChatWindowProps> = ({
  messages,
  isTyping,
  connected,
  username,
  onSendMessage,
  onLogout
}) => {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && connected) {
      onSendMessage(input);
      setInput('');
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-6 py-4 shadow-sm flex justify-between items-center">
        <div>
          <h1 className="text-xl font-semibold text-gray-800">AgentLab Chat</h1>
          <div className="flex items-center space-x-2 mt-1">
            <div
              className={`w-2 h-2 rounded-full ${
                connected ? 'bg-green-500' : 'bg-red-500'
              }`}
            />
            <span className="text-sm text-gray-600">
              {connected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </div>
        <div className="flex items-center space-x-4">
          <span className="text-sm text-gray-600">
            Logged in as <strong>{username}</strong>
          </span>
          <button
            onClick={onLogout}
            className="px-4 py-2 text-sm bg-gray-200 hover:bg-gray-300 rounded-md transition"
          >
            Logout
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-500 mt-8">
            <p className="text-lg">Welcome to AgentLab Chat!</p>
            <p className="text-sm mt-2">
              Ask me anything about your code, or request coding tasks.
            </p>
          </div>
        )}

        {messages.map((msg, idx) => (
          <MessageBubble key={idx} message={msg} />
        ))}

        {isTyping && (
          <div className="flex items-center space-x-2 text-gray-500 mb-4">
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100" />
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200" />
            <span className="text-sm ml-2">Assistant is thinking...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="bg-white border-t px-6 py-4">
        <form onSubmit={handleSubmit} className="flex space-x-4">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={connected ? "Type your message..." : "Connecting..."}
            disabled={!connected}
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={!input.trim() || !connected}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
          >
            Send
          </button>
        </form>
        <div className="text-xs text-gray-500 mt-2">
          Powered by Claude API. Press Enter to send.
        </div>
      </div>
    </div>
  );
};

export default ChatWindow;
