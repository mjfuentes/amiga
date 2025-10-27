import { useState, useEffect } from 'react';
import { Socket } from 'socket.io-client';

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  type?: 'direct' | 'task_started' | 'task_progress' | 'task_completed' | 'task_failed';
  task_id?: string;
}

export const useChat = (socket: Socket | null) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);

  useEffect(() => {
    if (!socket) return;

    // Handle direct responses
    socket.on('response', (data) => {
      const message: Message = {
        role: 'assistant',
        content: data.message,
        timestamp: new Date().toISOString(),
        type: data.type,
        task_id: data.task_id
      };
      setMessages(prev => [...prev, message]);
      setIsTyping(false);
    });

    // Handle task updates
    socket.on('task_update', (data) => {
      const message: Message = {
        role: 'assistant',
        content: `**Task #${data.task_id}** status: ${data.status}`,
        timestamp: new Date().toISOString(),
        type: 'task_progress',
        task_id: data.task_id
      };
      setMessages(prev => [...prev, message]);
    });

    // Handle task progress
    socket.on('task_progress', (data) => {
      const message: Message = {
        role: 'assistant',
        content: data.message,
        timestamp: new Date().toISOString(),
        type: 'task_progress',
        task_id: data.task_id
      };
      setMessages(prev => [...prev, message]);
    });

    // Handle task completion
    socket.on('task_completed', (data) => {
      const message: Message = {
        role: 'assistant',
        content: `**Task #${data.task_id} completed**\n\n${data.result}`,
        timestamp: new Date().toISOString(),
        type: 'task_completed',
        task_id: data.task_id
      };
      setMessages(prev => [...prev, message]);
    });

    // Handle task failure
    socket.on('task_failed', (data) => {
      const message: Message = {
        role: 'assistant',
        content: `**Task #${data.task_id} failed**\n\nError: ${data.error}`,
        timestamp: new Date().toISOString(),
        type: 'task_failed',
        task_id: data.task_id
      };
      setMessages(prev => [...prev, message]);
    });

    // Handle errors
    socket.on('error', (data) => {
      const message: Message = {
        role: 'assistant',
        content: `⚠️ Error: ${data.message}`,
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, message]);
      setIsTyping(false);
    });

    // Cleanup
    return () => {
      socket.off('response');
      socket.off('task_update');
      socket.off('task_progress');
      socket.off('task_completed');
      socket.off('task_failed');
      socket.off('error');
    };
  }, [socket]);

  const sendMessage = (content: string) => {
    if (!socket || !content.trim()) return;

    const userMessage: Message = {
      role: 'user',
      content,
      timestamp: new Date().toISOString()
    };

    setMessages(prev => [...prev, userMessage]);
    setIsTyping(true);

    socket.emit('message', { message: content });
  };

  const clearMessages = () => {
    setMessages([]);
  };

  return { messages, sendMessage, clearMessages, isTyping };
};
