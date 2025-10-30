import React from 'react';
import './TokenIndicator.css';

interface TokenIndicatorProps {
  totalTokens: {
    input: number;
    output: number;
  };
}

const MAX_TOKENS = 200000; // Claude Sonnet 4.5 context window

export const TokenIndicator: React.FC<TokenIndicatorProps> = ({ totalTokens }) => {
  const contextTokens = totalTokens.input; // Input tokens = current conversation context

  // Don't show if no tokens used yet
  if (contextTokens === 0) return null;

  // Format numbers with commas for readability
  const formatNumber = (num: number): string => {
    return num.toLocaleString();
  };

  // Calculate percentage for visual indicator
  const percentage = (contextTokens / MAX_TOKENS) * 100;

  // Determine warning level
  const getWarningClass = () => {
    if (percentage > 90) return 'token-critical';
    if (percentage > 75) return 'token-warning';
    return '';
  };

  return (
    <div className={`token-indicator ${getWarningClass()}`}>
      <div className="token-icon">🔢</div>
      <div className="token-details">
        <div className="token-count">
          {formatNumber(contextTokens)} <span className="token-separator">/</span> {formatNumber(MAX_TOKENS)}
        </div>
        <div className="token-label">tokens</div>
      </div>
    </div>
  );
};
