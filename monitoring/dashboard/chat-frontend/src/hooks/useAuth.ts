import { useState, useEffect } from 'react';
import { User } from '../types';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:3000/api';
const NO_AUTH_MODE = process.env.REACT_APP_NO_AUTH_MODE !== 'false'; // Enabled by default
const ADMIN_USER_ID = process.env.REACT_APP_ADMIN_USER_ID || '521930094';
const ADMIN_EMAIL = 'matiasj.fuentes@gmail.com';
const TOKEN_KEY = 'chat_token';
const USER_KEY = 'chat_user';

export const useAuth = () => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const initAuth = async () => {
      if (NO_AUTH_MODE) {
        // No-auth mode: auto-login as admin with email
        const dummyToken = `dummy-token-${ADMIN_USER_ID}`;
        setToken(dummyToken);
        setUser({ user_id: ADMIN_USER_ID, username: ADMIN_EMAIL });
        localStorage.setItem(TOKEN_KEY, dummyToken);
        localStorage.setItem(USER_KEY, JSON.stringify({ user_id: ADMIN_USER_ID, username: ADMIN_EMAIL }));
        setLoading(false);
        return;
      }

      // Check for existing token
      const storedToken = localStorage.getItem(TOKEN_KEY);
      if (storedToken) {
        try {
          const response = await fetch(`${API_URL}/auth/verify`, {
            headers: {
              Authorization: `Bearer ${storedToken}`,
            },
          });

          if (response.ok) {
            const data = await response.json();
            setToken(storedToken);
            setUser(data.user);
            localStorage.setItem(USER_KEY, JSON.stringify(data.user));
          } else {
            localStorage.removeItem(TOKEN_KEY);
            localStorage.removeItem(USER_KEY);
          }
        } catch (error) {
          console.error('Token verification failed:', error);
          localStorage.removeItem(TOKEN_KEY);
          localStorage.removeItem(USER_KEY);
        }
      }
      setLoading(false);
    };

    initAuth();
  }, []);

  const login = async (username: string, password: string) => {
    try {
      const response = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Login failed');
      }

      const data = await response.json();
      setToken(data.token);
      setUser(data.user);
      localStorage.setItem(TOKEN_KEY, data.token);
      localStorage.setItem(USER_KEY, JSON.stringify(data.user));
      return true;
    } catch (error) {
      console.error('Login error:', error);
      throw error;
    }
  };

  const register = async (username: string, password: string) => {
    try {
      const response = await fetch(`${API_URL}/auth/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Registration failed');
      }

      const data = await response.json();
      setToken(data.token);
      setUser(data.user);
      localStorage.setItem(TOKEN_KEY, data.token);
      localStorage.setItem(USER_KEY, JSON.stringify(data.user));
      return true;
    } catch (error) {
      console.error('Registration error:', error);
      throw error;
    }
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  };

  return {
    user,
    token,
    loading,
    login,
    register,
    logout,
  };
};
