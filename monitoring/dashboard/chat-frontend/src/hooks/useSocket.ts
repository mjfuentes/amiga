import { useEffect, useState, useCallback } from 'react';
import { io, Socket } from 'socket.io-client';
import { Message, SocketResponse } from '../types';

const SOCKET_URL = process.env.REACT_APP_SOCKET_URL || 'http://localhost:3000';
const STORAGE_KEY = 'chat_history';

// Load messages from localStorage
const loadMessages = (): Message[] => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : [];
  } catch (error) {
    console.error('Failed to load chat history:', error);
    return [];
  }
};

// Save messages to localStorage
const saveMessages = (messages: Message[]) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
  } catch (error) {
    console.error('Failed to save chat history:', error);
  }
};

// Clear messages from localStorage
const clearStoredMessages = () => {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (error) {
    console.error('Failed to clear chat history:', error);
  }
};

export const useSocket = (token: string | null) => {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState<Message[]>(loadMessages());

  // Save messages to localStorage whenever they change
  useEffect(() => {
    saveMessages(messages);
  }, [messages]);

  useEffect(() => {
    if (!token) return;

    const newSocket = io(SOCKET_URL, {
      auth: { token },
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

    try {
      const response = await fetch(`${SOCKET_URL}/api/chat/clear`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        // Clear localStorage
        clearStoredMessages();

        // Clear local messages state completely
        setMessages([]);
        console.log('Chat session cleared');
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
  };
};
