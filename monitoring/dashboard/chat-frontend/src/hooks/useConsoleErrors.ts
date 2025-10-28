import { useState, useEffect, useCallback } from 'react';

interface ConsoleError {
  message: string;
  timestamp: number;
  stack?: string;
}

export const useConsoleErrors = () => {
  const [errors, setErrors] = useState<ConsoleError[]>([]);

  useEffect(() => {
    // Store original console.error
    const originalError = console.error;

    // Override console.error to capture errors
    console.error = (...args: any[]) => {
      // Call original console.error to maintain normal behavior
      originalError.apply(console, args);

      // Capture error details
      const message = args
        .map((arg) => {
          if (arg instanceof Error) {
            return arg.message;
          }
          if (typeof arg === 'object') {
            try {
              return JSON.stringify(arg);
            } catch {
              return String(arg);
            }
          }
          return String(arg);
        })
        .join(' ');

      const stack = args.find((arg) => arg instanceof Error)?.stack;

      // Add to errors list
      setErrors((prev) => [
        ...prev,
        {
          message,
          timestamp: Date.now(),
          stack,
        },
      ]);
    };

    // Cleanup: restore original console.error
    return () => {
      console.error = originalError;
    };
  }, []);

  const clearErrors = useCallback(() => {
    setErrors([]);
  }, []);

  const copyErrors = useCallback(() => {
    const errorText = errors
      .map(
        (err) =>
          `[${new Date(err.timestamp).toISOString()}] ${err.message}${
            err.stack ? `\n${err.stack}` : ''
          }`
      )
      .join('\n\n');

    return navigator.clipboard.writeText(errorText);
  }, [errors]);

  return {
    errors,
    hasErrors: errors.length > 0,
    errorCount: errors.length,
    clearErrors,
    copyErrors,
  };
};
