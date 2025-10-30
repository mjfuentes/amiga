import { useState, useEffect, useCallback, useRef } from 'react';
import { User } from '../types';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:3000/api';
const NO_AUTH_MODE = process.env.REACT_APP_NO_AUTH_MODE !== 'false'; // Enabled by default
const ADMIN_USER_ID = process.env.REACT_APP_ADMIN_USER_ID || '521930094';
const ADMIN_EMAIL = 'matiasj.fuentes@gmail.com';
const ACCESS_TOKEN_KEY = 'chat_access_token';
const REFRESH_TOKEN_KEY = 'chat_refresh_token';
const USER_KEY = 'chat_user';

// Token refresh timing (in minutes)
const TOKEN_REFRESH_INTERVAL = 10; // Refresh every 10 minutes (before 15-minute expiration)

export const useAuth = () => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const refreshTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Clear refresh timer
  const clearRefreshTimer = useCallback(() => {
    if (refreshTimerRef.current) {
      clearInterval(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  // Refresh access token
  const refreshAccessToken = useCallback(async () => {
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    if (!refreshToken) {
      console.log('No refresh token available');
      return false;
    }

    try {
      const response = await fetch(`${API_URL}/auth/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (response.ok) {
        const data = await response.json();
        setToken(data.access_token);
        setUser(data.user);
        localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
        localStorage.setItem(USER_KEY, JSON.stringify(data.user));
        console.log('Access token refreshed successfully');
        return true;
      } else {
        console.error('Token refresh failed');
        // Clear invalid tokens
        localStorage.removeItem(ACCESS_TOKEN_KEY);
        localStorage.removeItem(REFRESH_TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
        setToken(null);
        setUser(null);
        clearRefreshTimer();
        return false;
      }
    } catch (error) {
      console.error('Token refresh error:', error);
      return false;
    }
  }, [clearRefreshTimer]);

  // Setup automatic token refresh
  const setupTokenRefresh = useCallback(() => {
    // Clear any existing timer
    clearRefreshTimer();

    // Setup new refresh interval
    refreshTimerRef.current = setInterval(() => {
      console.log('Running automatic token refresh...');
      refreshAccessToken();
    }, TOKEN_REFRESH_INTERVAL * 60 * 1000);

    console.log(`Token refresh scheduled every ${TOKEN_REFRESH_INTERVAL} minutes`);
  }, [clearRefreshTimer, refreshAccessToken]);

  useEffect(() => {
    const initAuth = async () => {
      if (NO_AUTH_MODE) {
        // No-auth mode: auto-login as admin with email
        const dummyToken = `dummy-token-${ADMIN_USER_ID}`;
        setToken(dummyToken);
        setUser({ user_id: ADMIN_USER_ID, username: ADMIN_EMAIL });
        localStorage.setItem(ACCESS_TOKEN_KEY, dummyToken);
        localStorage.setItem(USER_KEY, JSON.stringify({ user_id: ADMIN_USER_ID, username: ADMIN_EMAIL }));
        setLoading(false);
        return;
      }

      // Check for existing token
      const storedToken = localStorage.getItem(ACCESS_TOKEN_KEY);
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
            setUser(data);
            localStorage.setItem(USER_KEY, JSON.stringify(data));
            setupTokenRefresh(); // Start automatic refresh
          } else {
            // Token invalid, try refresh
            console.log('Stored token invalid, attempting refresh...');
            const refreshed = await refreshAccessToken();
            if (refreshed) {
              setupTokenRefresh();
            } else {
              // Refresh failed, clear everything
              localStorage.removeItem(ACCESS_TOKEN_KEY);
              localStorage.removeItem(REFRESH_TOKEN_KEY);
              localStorage.removeItem(USER_KEY);
            }
          }
        } catch (error) {
          console.error('Token verification failed:', error);
          // Try refresh before giving up
          const refreshed = await refreshAccessToken();
          if (!refreshed) {
            localStorage.removeItem(ACCESS_TOKEN_KEY);
            localStorage.removeItem(REFRESH_TOKEN_KEY);
            localStorage.removeItem(USER_KEY);
          } else {
            setupTokenRefresh();
          }
        }
      }
      setLoading(false);
    };

    initAuth();

    // Cleanup on unmount
    return () => {
      clearRefreshTimer();
    };
  }, [refreshAccessToken, setupTokenRefresh, clearRefreshTimer]);

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
      setToken(data.access_token);
      setUser(data.user);
      localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
      localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
      localStorage.setItem(USER_KEY, JSON.stringify(data.user));
      setupTokenRefresh(); // Start automatic refresh
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
      setToken(data.access_token);
      setUser(data.user);
      localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
      localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
      localStorage.setItem(USER_KEY, JSON.stringify(data.user));
      setupTokenRefresh(); // Start automatic refresh
      return true;
    } catch (error) {
      console.error('Registration error:', error);
      throw error;
    }
  };

  const logout = async () => {
    try {
      // Call logout endpoint to invalidate session
      if (token) {
        await fetch(`${API_URL}/auth/logout`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
      }
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      // Clear local state and storage regardless of API call result
      clearRefreshTimer();
      setToken(null);
      setUser(null);
      localStorage.removeItem(ACCESS_TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    }
  };

  return {
    user,
    token,
    loading,
    login,
    register,
    logout,
    refreshAccessToken,
  };
};
