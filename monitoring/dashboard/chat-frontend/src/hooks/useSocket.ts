import { useEffect, useState, useCallback } from 'react';
import { io, Socket } from 'socket.io-client';
import { Message, SocketResponse } from '../types';

const SOCKET_URL = process.env.REACT_APP_SOCKET_URL || 'http://localhost:3000';

// Generate unique session ID for this browser window
// Uses sessionStorage to ensure each window/tab gets unique ID
const getSessionId = (): string => {
  let sessionId = sessionStorage.getItem('amiga_session_id');
  if (!sessionId) {
    sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    sessionStorage.setItem('amiga_session_id', sessionId);
    console.log('Generated new session ID:', sessionId);
  }
  return sessionId;
};

// Session-specific storage key (unique per browser window)
const getStorageKey = (): string => {
  const sessionId = getSessionId();
  return `chat_history_${sessionId}`;
};

// Load messages from sessionStorage (window-specific)
const loadMessages = (): Message[] => {
  try {
    const stored = sessionStorage.getItem(getStorageKey());
    return stored ? JSON.parse(stored) : [];
  } catch (error) {
    console.error('Failed to load chat history:', error);
    return [];
  }
};

// Save messages to sessionStorage (window-specific)
const saveMessages = (messages: Message[]) => {
  try {
    sessionStorage.setItem(getStorageKey(), JSON.stringify(messages));
  } catch (error) {
    console.error('Failed to save chat history:', error);
  }
};

// Clear messages from sessionStorage
const clearStoredMessages = () => {
  try {
    sessionStorage.removeItem(getStorageKey());
  } catch (error) {
    console.error('Failed to clear chat history:', error);
  }
};

export const useSocket = (token: string | null) => {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState<Message[]>(loadMessages());
  const [totalTokens, setTotalTokens] = useState({ input: 0, output: 0 });

  // Save messages to localStorage whenever they change
  useEffect(() => {
    saveMessages(messages);
  }, [messages]);

  useEffect(() => {
    if (!token) return;

    // Get unique session ID for this browser window
    const sessionId = getSessionId();
    console.log('Connecting with session ID:', sessionId);

    const newSocket = io(SOCKET_URL, {
      auth: { token, session_id: sessionId },
      transports: ['polling', 'websocket'],
    });

    newSocket.on('connect', () => {
      console.log('Connected to server');
      setConnected(true);
    });

    newSocket.on('disconnect', () => {
      console.log('Disconnected from server');
      setConnected(false);
    });

    newSocket.on('connected', (data) => {
      console.log('Server acknowledged connection:', data);
    });

    newSocket.on('response', (data: SocketResponse) => {
      console.log('Received response:', data);
      const newMessage: Message = {
        id: Date.now().toString(),
        content: data.message,
        role: 'assistant',
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, newMessage]);

      // Accumulate tokens if provided
      if (data.tokens) {
        setTotalTokens((prev) => ({
          input: prev.input + (data.tokens?.input || 0),
          output: prev.output + (data.tokens?.output || 0),
        }));
      }
    });

    newSocket.on('command_result', (data: any) => {
      console.log('Received command result:', data);
      const newMessage: Message = {
        id: Date.now().toString(),
        content: data.message,
        role: 'assistant',
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, newMessage]);
    });

    newSocket.on('error', (data) => {
      console.error('Socket error:', data);
    });

    newSocket.on('clear_chat', (data) => {
      console.log('Received clear_chat event:', data);
      // Clear localStorage
      clearStoredMessages();

      // Clear messages completely
      setMessages([]);

      // Reset token counter
      setTotalTokens({ input: 0, output: 0 });
    });

    setSocket(newSocket);

    return () => {
      newSocket.close();
    };
  }, [token]);

  const sendMessage = useCallback(
    (content: string) => {
      if (!socket || !connected) {
        console.error('Socket not connected');
        return;
      }

      // Add user message to UI
      const userMessage: Message = {
        id: Date.now().toString(),
        content,
        role: 'user',
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, userMessage]);

      // Send to server
      socket.emit('message', { message: content });
    },
    [socket, connected]
  );

  const clearChat = useCallback(async (): Promise<boolean> => {
    if (!token) {
      console.error('No token available');
      return false;
    }

    const sessionId = getSessionId();

    try {
      const response = await fetch(`${SOCKET_URL}/api/chat/clear`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ session_id: sessionId }),
      });

      if (response.ok) {
        // Clear sessionStorage
        clearStoredMessages();

        // Clear local messages state completely
        setMessages([]);

        // Reset token counter
        setTotalTokens({ input: 0, output: 0 });

        console.log('Chat session cleared for session:', sessionId);
        return true;
      } else {
        console.error('Failed to clear chat:', response.statusText);
        return false;
      }
    } catch (error) {
      console.error('Error clearing chat:', error);
      return false;
    }
  }, [token]);

  return {
    connected,
    messages,
    sendMessage,
    clearChat,
    totalTokens,
  };
};
