import React from 'react';

// Mock SyntaxHighlighter component for testing
export const Prism: React.FC<{ children?: React.ReactNode; language?: string; style?: any }> = ({ children, language }) => {
  return <pre data-testid="mock-syntax-highlighter" data-language={language}>{children}</pre>;
};
