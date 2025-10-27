import { useState, useEffect } from 'react';

interface User {
  user_id: string;
  username: string;
  email: string;
  created_at: string;
  is_admin: boolean;
}

interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
}

// NO AUTHENTICATION MODE - Auto-authenticate with admin user from environment
const ADMIN_USER_ID = process.env.REACT_APP_ADMIN_USER_ID || '521930094';

export const useAuth = () => {
  const [authState, setAuthState] = useState<AuthState>({
    token: 'NO_AUTH_REQUIRED',
    user: {
      user_id: ADMIN_USER_ID,
      username: 'Admin',
      email: 'admin@localhost',
      created_at: new Date().toISOString(),
      is_admin: true
    },
    isAuthenticated: true
  });

  useEffect(() => {
    // Auto-authenticate on mount
    console.log('Auto-authenticated as admin user:', ADMIN_USER_ID);
  }, []);

  // Dummy functions for compatibility
  const login = async (username: string, password: string): Promise<{ success: boolean; error?: string }> => {
    return { success: true };
  };

  const register = async (username: string, email: string, password: string): Promise<{ success: boolean; error?: string }> => {
    return { success: true };
  };

  const logout = () => {
    // Do nothing - no real logout in no-auth mode
    console.log('Logout called but ignored in no-auth mode');
  };

  return {
    ...authState,
    login,
    register,
    logout
  };
};
