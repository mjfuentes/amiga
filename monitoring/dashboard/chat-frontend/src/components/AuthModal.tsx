import React, { useState, useEffect } from 'react';
import './AuthModal.css';

interface AuthModalProps {
  onLogin: (username: string, password: string) => Promise<boolean>;
  onRegister: (username: string, password: string) => Promise<boolean>;
}

export const AuthModal: React.FC<AuthModalProps> = ({ onLogin, onRegister }) => {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (isLogin) {
        await onLogin(username, password);
      } else {
        await onRegister(username, password);
      }
    } catch (err: any) {
      setError(err.message || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  // Clear error when switching modes
  useEffect(() => {
    setError('');
    setPassword('');
  }, [isLogin]);

  return (
    <div className="auth-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="auth-modal-title">
      <div className="auth-modal">
        <div className="auth-modal-header">
          <div className="auth-modal-icon">🤖</div>
          <h2 id="auth-modal-title">{isLogin ? 'Welcome Back' : 'Create Account'}</h2>
          <p className="auth-modal-subtitle">
            {isLogin ? 'Sign in to continue to AMIGA' : 'Sign up to get started with AMIGA'}
          </p>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
              autoComplete="username"
              placeholder="Enter your username"
              aria-required="true"
              aria-invalid={!!error}
              aria-describedby={error ? "auth-error" : undefined}
            />
          </div>
          <div className="form-group">
            <label htmlFor="password">Password</label>
            <div className="password-input-wrapper">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete={isLogin ? 'current-password' : 'new-password'}
                placeholder="Enter your password"
                aria-required="true"
                aria-invalid={!!error}
                aria-describedby={error ? "auth-error" : undefined}
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? (
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <path d="M3.26 11.6C2.93 11.09 2.68 10.57 2.5 10C3.73 6.77 6.63 4.5 10 4.5C10.55 4.5 11.09 4.57 11.6 4.68L10.86 5.42C10.58 5.37 10.29 5.35 10 5.35C7.12 5.35 4.78 7.29 3.86 10C4.08 10.6 4.42 11.16 4.86 11.66L3.26 11.6ZM10 14.65C9.45 14.65 8.91 14.58 8.4 14.47L9.14 13.73C9.42 13.78 9.71 13.8 10 13.8C12.88 13.8 15.22 11.86 16.14 9.15C15.92 8.55 15.58 7.99 15.14 7.49L16.74 7.55C17.07 8.06 17.32 8.58 17.5 9.15C16.27 12.38 13.37 14.65 10 14.65ZM10 7.5C8.62 7.5 7.5 8.62 7.5 10C7.5 10.37 7.58 10.72 7.72 11.03L6.28 9.59C6.19 9.87 6.15 10.17 6.15 10.5C6.15 11.88 7.27 13 8.65 13C8.98 13 9.28 12.96 9.56 12.87L8.12 11.43C7.81 11.29 7.46 11.21 7.09 11.21C6.71 11.21 6.36 11.29 6.05 11.43L7.49 9.99C7.63 9.68 7.71 9.33 7.71 8.95C7.71 8.57 7.63 8.22 7.49 7.91L8.93 9.35C9.24 9.49 9.59 9.57 9.96 9.57C10.34 9.57 10.69 9.49 11 9.35L12.44 10.79C12.53 10.51 12.57 10.21 12.57 9.88C12.57 8.5 11.45 7.38 10.07 7.38L10 7.5Z" fill="currentColor"/>
                    <line x1="2" y1="2" x2="18" y2="18" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                ) : (
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <path d="M10 5C6.63 5 3.73 7.27 2.5 10.5C3.73 13.73 6.63 16 10 16C13.37 16 16.27 13.73 17.5 10.5C16.27 7.27 13.37 5 10 5ZM10 14C8.07 14 6.5 12.43 6.5 10.5C6.5 8.57 8.07 7 10 7C11.93 7 13.5 8.57 13.5 10.5C13.5 12.43 11.93 14 10 14ZM10 8.5C8.9 8.5 8 9.4 8 10.5C8 11.6 8.9 12.5 10 12.5C11.1 12.5 12 11.6 12 10.5C12 9.4 11.1 8.5 10 8.5Z" fill="currentColor"/>
                  </svg>
                )}
              </button>
            </div>
          </div>
          {error && (
            <div id="auth-error" className="error-message" role="alert">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M8 1C4.13 1 1 4.13 1 8C1 11.87 4.13 15 8 15C11.87 15 15 11.87 15 8C15 4.13 11.87 1 8 1ZM8.5 11.5H7.5V10.5H8.5V11.5ZM8.5 9.5H7.5V4.5H8.5V9.5Z" fill="currentColor"/>
              </svg>
              {error}
            </div>
          )}
          <button type="submit" disabled={loading} className="submit-button">
            {loading ? (
              <>
                <span className="spinner-small"></span>
                {isLogin ? 'Signing in...' : 'Creating account...'}
              </>
            ) : (
              isLogin ? 'Sign In' : 'Create Account'
            )}
          </button>
        </form>
        <div className="auth-toggle">
          {isLogin ? "Don't have an account? " : 'Already have an account? '}
          <button type="button" onClick={() => setIsLogin(!isLogin)} className="toggle-button">
            {isLogin ? 'Sign Up' : 'Sign In'}
          </button>
        </div>
      </div>
    </div>
  );
};
