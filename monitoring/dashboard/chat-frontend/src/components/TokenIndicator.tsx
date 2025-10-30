import React from 'react';
import './TokenIndicator.css';

interface TokenIndicatorProps {
  totalTokens: {
    input: number;
    output: number;
  };
}

export const TokenIndicator: React.FC<TokenIndicatorProps> = ({ totalTokens }) => {
  const total = totalTokens.input + totalTokens.output;
  
  // Don't show if no tokens used yet
  if (total === 0) return null;

  // Format numbers with commas for readability
  const formatNumber = (num: number): string => {
    return num.toLocaleString();
  };

  return (
    <div className="token-indicator">
      <div className="token-icon">🔢</div>
      <div className="token-details">
        <div className="token-total">{formatNumber(total)}</div>
        <div className="token-breakdown">
          <span className="token-in" title="Input tokens">{formatNumber(totalTokens.input)} in</span>
          {' · '}
          <span className="token-out" title="Output tokens">{formatNumber(totalTokens.output)} out</span>
        </div>
      </div>
    </div>
  );
};
