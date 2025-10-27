/**
 * Tests for useAuth hook - NO_AUTH_MODE authentication feature
 *
 * Tests verify:
 * 1. NO_AUTH_MODE enabled by default (env var not set)
 * 2. Auto-login sets email correctly
 * 3. User object structure is correct
 * 4. Token stored in localStorage
 * 5. Logout functionality
 *
 * NOTE: Testing different NO_AUTH_MODE states requires separate test runs with
 * different environment configurations because the constant is evaluated at module load time.
 */

import { renderHook, waitFor, act } from '@testing-library/react';
import { useAuth } from './useAuth';

// Mock fetch globally
global.fetch = jest.fn();

describe('useAuth - NO_AUTH_MODE (Default Enabled)', () => {
  beforeEach(() => {
    // Clear localStorage and mocks before each test
    localStorage.clear();
    jest.clearAllMocks();
    (global.fetch as any).mockClear();
  });

  describe('Auto-login behavior', () => {
    test('auto-login sets email correctly', async () => {
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Verify user has correct email
      expect(result.current.user).not.toBeNull();
      expect(result.current.user?.username).toBe('matiasj.fuentes@gmail.com');
    });

    test('user object structure is correct', async () => {
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Verify user object has required fields
      expect(result.current.user).toMatchObject({
        user_id: expect.any(String),
        username: expect.any(String),
      });

      // Verify specific values (default admin user)
      expect(result.current.user?.user_id).toBe('521930094');
      expect(result.current.user?.username).toBe('matiasj.fuentes@gmail.com');
    });

    test('token is stored in localStorage', async () => {
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Verify token in localStorage
      const storedToken = localStorage.getItem('token');
      expect(storedToken).not.toBeNull();
      expect(storedToken).toBe('dummy-token-521930094');
    });

    test('token in state matches localStorage', async () => {
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Verify token consistency
      expect(result.current.token).toBe(localStorage.getItem('token'));
      expect(result.current.token).toBe('dummy-token-521930094');
    });

    test('does not call fetch API in NO_AUTH_MODE', async () => {
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Verify fetch was NOT called (no API verification in NO_AUTH_MODE)
      expect(global.fetch).not.toHaveBeenCalled();
    });

    test('completes initialization quickly', async () => {
      const startTime = Date.now();
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      const endTime = Date.now();
      const duration = endTime - startTime;

      // Should complete in under 100ms (no network calls)
      expect(duration).toBeLessThan(100);
      expect(result.current.user).not.toBeNull();
    });

    test('sets all required state fields', async () => {
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Verify all hook return values are set
      expect(result.current).toHaveProperty('user');
      expect(result.current).toHaveProperty('token');
      expect(result.current).toHaveProperty('loading');
      expect(result.current).toHaveProperty('login');
      expect(result.current).toHaveProperty('register');
      expect(result.current).toHaveProperty('logout');

      // Verify functions are callable
      expect(typeof result.current.login).toBe('function');
      expect(typeof result.current.register).toBe('function');
      expect(typeof result.current.logout).toBe('function');
    });

    test('user_id matches expected admin ID', async () => {
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Default admin user ID should be 521930094
      expect(result.current.user?.user_id).toBe('521930094');
      expect(result.current.token).toContain('521930094');
    });

    test('username is email format', async () => {
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Verify username is a valid email
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      expect(result.current.user?.username).toMatch(emailRegex);
      expect(result.current.user?.username).toBe('matiasj.fuentes@gmail.com');
    });

    test('token follows expected format', async () => {
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Token should be dummy-token-{user_id}
      expect(result.current.token).toMatch(/^dummy-token-\d+$/);
      expect(result.current.token).toBe('dummy-token-521930094');
    });
  });

  describe('Logout functionality', () => {
    test('logout clears user state', async () => {
      const { result } = renderHook(() => useAuth());

      // Wait for auto-login
      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Verify auto-login succeeded
      expect(result.current.user).not.toBeNull();
      const initialUser = result.current.user;

      // Logout
      act(() => {
        result.current.logout();
      });

      // Verify user cleared
      expect(result.current.user).toBeNull();
      expect(result.current.user).not.toEqual(initialUser);
    });

    test('logout clears token state', async () => {
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.token).not.toBeNull();

      // Logout
      act(() => {
        result.current.logout();
      });

      // Verify token cleared
      expect(result.current.token).toBeNull();
    });

    test('logout removes token from localStorage', async () => {
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(localStorage.getItem('token')).not.toBeNull();

      // Logout
      act(() => {
        result.current.logout();
      });

      // Verify localStorage cleared
      expect(localStorage.getItem('token')).toBeNull();
    });

    test('logout is idempotent', async () => {
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Logout multiple times
      act(() => {
        result.current.logout();
        result.current.logout();
        result.current.logout();
      });

      // Should still be logged out with no errors
      expect(result.current.user).toBeNull();
      expect(result.current.token).toBeNull();
      expect(localStorage.getItem('token')).toBeNull();
    });
  });

  describe('Edge cases', () => {
    test('handles multiple hook instances with shared localStorage', async () => {
      const { result: result1 } = renderHook(() => useAuth());
      const { result: result2 } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result1.current.loading).toBe(false);
        expect(result2.current.loading).toBe(false);
      });

      // Both instances should have same token in state
      expect(result1.current.token).toBe(result2.current.token);

      // Both should reference same localStorage
      expect(result1.current.token).toBe(localStorage.getItem('token'));
      expect(result2.current.token).toBe(localStorage.getItem('token'));
    });

    test('logout from one instance affects localStorage for all', async () => {
      const { result: result1 } = renderHook(() => useAuth());
      const { result: result2 } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result1.current.loading).toBe(false);
        expect(result2.current.loading).toBe(false);
      });

      // Logout from first instance
      act(() => {
        result1.current.logout();
      });

      // localStorage should be cleared (affects all instances)
      expect(localStorage.getItem('token')).toBeNull();

      // First instance state should be cleared
      expect(result1.current.user).toBeNull();
      expect(result1.current.token).toBeNull();

      // Second instance still has its own state (not reactive to localStorage changes)
      // This is expected behavior - each hook instance manages its own state
      expect(result2.current.user).not.toBeNull();
      expect(result2.current.token).not.toBeNull();
    });

    test('initializes with loading state', () => {
      const { result } = renderHook(() => useAuth());

      // Should start with some initial state
      expect(result.current).toBeDefined();
      expect(result.current.loading).toBeDefined();
    });

    test('user and token are consistent', async () => {
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // If user is set, token should be set
      if (result.current.user) {
        expect(result.current.token).not.toBeNull();
      }

      // If token is set, user should be set
      if (result.current.token) {
        expect(result.current.user).not.toBeNull();
      }

      // In NO_AUTH_MODE, both should be set
      expect(result.current.user).not.toBeNull();
      expect(result.current.token).not.toBeNull();
    });

    test('localStorage persistence after hook unmount', async () => {
      const { result, unmount } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      const token = localStorage.getItem('token');
      expect(token).not.toBeNull();

      // Unmount hook
      unmount();

      // Token should still be in localStorage
      expect(localStorage.getItem('token')).toBe(token);
    });

    test('loading transitions to false after initialization', async () => {
      const { result } = renderHook(() => useAuth());

      // Wait for loading to complete
      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      }, { timeout: 1000 });

      // Should be fully initialized
      expect(result.current.loading).toBe(false);
      expect(result.current.user).not.toBeNull();
      expect(result.current.token).not.toBeNull();
    });
  });

  describe('Login and Register functionality (NO_AUTH_MODE)', () => {
    test('login function exists but is not needed in NO_AUTH_MODE', async () => {
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Login function should exist
      expect(typeof result.current.login).toBe('function');

      // Already logged in via NO_AUTH_MODE
      expect(result.current.user).not.toBeNull();
      expect(result.current.token).not.toBeNull();
    });

    test('register function exists but is not needed in NO_AUTH_MODE', async () => {
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Register function should exist
      expect(typeof result.current.register).toBe('function');

      // Already logged in via NO_AUTH_MODE
      expect(result.current.user).not.toBeNull();
      expect(result.current.token).not.toBeNull();
    });
  });

  describe('Type correctness', () => {
    test('user matches User interface', async () => {
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // User should have correct shape
      const user = result.current.user;
      expect(user).toBeDefined();
      expect(user).toHaveProperty('user_id');
      expect(user).toHaveProperty('username');

      // Values should be strings
      expect(typeof user?.user_id).toBe('string');
      expect(typeof user?.username).toBe('string');
    });

    test('token is string when set', async () => {
      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(typeof result.current.token).toBe('string');
    });

    test('loading is boolean', async () => {
      const { result } = renderHook(() => useAuth());

      expect(typeof result.current.loading).toBe('boolean');

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(typeof result.current.loading).toBe('boolean');
    });
  });
});

/**
 * Integration test notes:
 *
 * Environment variable testing:
 * - NO_AUTH_MODE defaults to enabled (process.env.REACT_APP_NO_AUTH_MODE !== 'false')
 * - To test with NO_AUTH_MODE disabled, run: REACT_APP_NO_AUTH_MODE=false npm test
 * - Constants are evaluated at module load time, so runtime changes don't affect behavior
 *
 * Test coverage:
 * ✅ Auto-login sets email correctly
 * ✅ User object structure is correct
 * ✅ Token stored in localStorage
 * ✅ Token format and consistency
 * ✅ Logout functionality
 * ✅ Multiple hook instances
 * ✅ Type correctness
 *
 * Manual testing required for:
 * - NO_AUTH_MODE=false behavior (requires separate test run with env var)
 * - Traditional authentication flow (requires backend integration)
 */
