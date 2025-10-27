import React from 'react';

// Mock ReactMarkdown component for testing
const ReactMarkdown: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  return <div data-testid="mock-markdown">{children}</div>;
};

export default ReactMarkdown;
