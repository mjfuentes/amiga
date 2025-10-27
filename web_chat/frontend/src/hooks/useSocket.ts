import { useEffect, useState } from 'react';
import { io, Socket } from 'socket.io-client';

const SOCKET_URL = process.env.REACT_APP_SOCKET_URL || 'http://localhost:3000';
const ADMIN_USER_ID = process.env.REACT_APP_ADMIN_USER_ID || '521930094';

export const useSocket = (token: string | null) => {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    // NO AUTHENTICATION MODE - Create a dummy token for admin user
    const dummyToken = `dummy-token-${ADMIN_USER_ID}`;

    // Create socket connection (no real auth required)
    const newSocket = io(SOCKET_URL, {
      auth: { token: dummyToken },
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 5
    });

    newSocket.on('connect', () => {
      console.log('WebSocket connected to', SOCKET_URL);
      setConnected(true);
    });

    newSocket.on('disconnect', (reason) => {
      console.log('WebSocket disconnected:', reason);
      setConnected(false);
    });

    newSocket.on('connected', (data) => {
      console.log('Connected with user_id:', data.user_id);
    });

    newSocket.on('connect_error', (error) => {
      console.error('Connection error:', error);
      setConnected(false);
    });

    setSocket(newSocket);

    // Cleanup on unmount
    return () => {
      newSocket.close();
    };
  }, []); // No dependency on token - always connect

  return { socket, connected };
};
