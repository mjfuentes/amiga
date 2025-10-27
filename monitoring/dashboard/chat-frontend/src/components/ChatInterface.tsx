import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  MainContainer,
  ChatContainer,
  MessageList,
  Message,
  MessageInput,
  TypingIndicator,
} from '@chatscope/chat-ui-kit-react';
import '@chatscope/chat-ui-kit-styles/dist/default/styles.min.css';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import toast, { Toaster } from 'react-hot-toast';
import { Message as MessageType } from '../types';
import './ChatInterface.css';

interface ChatInterfaceProps {
  messages: MessageType[];
  connected: boolean;
  onSendMessage: (message: string) => void;
  onClearChat: () => Promise<boolean>;
  onLogout: () => void;
}

// Available commands with descriptions
const COMMANDS = [
  { command: '/help', description: 'Show available commands' },
  { command: '/status', description: 'Show active tasks and recent errors' },
  { command: '/clear', description: 'Clear conversation history' },
  { command: '/retry', description: 'Retry failed tasks' },
  { command: '/stop', description: 'Stop a running task by ID' },
  { command: '/stopall', description: 'Stop all running tasks' },
  { command: '/view', description: 'View task result by ID' },
];

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  messages,
  connected,
  onSendMessage,
  onClearChat,
  onLogout,
}) => {
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [showCommands, setShowCommands] = useState(false);
  const [filteredCommands, setFilteredCommands] = useState(COMMANDS);
  const lastMessageCountRef = useRef(messages.length);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const inputListenerAttachedRef = useRef(false);


  // Attach input listener for command autocomplete
  const attachInputListener = useCallback(() => {
    if (inputListenerAttachedRef.current) return;

    const textarea = document.querySelector('.cs-message-input__content-editor') as HTMLTextAreaElement;
    if (textarea) {
      const handleInput = (e: Event) => {
        const target = e.target as HTMLTextAreaElement;
        const value = target.value || target.textContent || '';
        handleInputChange(value);
      };

      textarea.addEventListener('input', handleInput);
      inputListenerAttachedRef.current = true;
      inputRef.current = textarea;

      // Cleanup on unmount
      return () => {
        textarea.removeEventListener('input', handleInput);
        inputListenerAttachedRef.current = false;
      };
    }
  }, []);

  // Focus the input on mount and when messages change
  useEffect(() => {
    // Small delay to ensure DOM is ready
    const timer = setTimeout(() => {
      focusInput();
      attachInputListener();
    }, 100);
    return () => clearTimeout(timer);
  }, [attachInputListener]);

  // Re-focus after sending messages
  useEffect(() => {
    if (messages.length > lastMessageCountRef.current) {
      const lastMessage = messages[messages.length - 1];
      if (lastMessage.role === 'assistant') {
        setIsTyping(false);
        // Re-focus after assistant responds
        focusInput();
      }
    }
    lastMessageCountRef.current = messages.length;
  }, [messages]);

  // Re-attach listener when component re-renders
  useEffect(() => {
    if (!inputListenerAttachedRef.current) {
      const cleanup = attachInputListener();
      return cleanup;
    }
  }, [connected, attachInputListener]);

  // Helper function to focus the input
  const focusInput = () => {
    // Find the textarea within the MessageInput component
    const textarea = document.querySelector('.cs-message-input__content-editor') as HTMLTextAreaElement;
    if (textarea) {
      textarea.focus();
      inputRef.current = textarea;
    }
  };

  // Copy to clipboard helper
  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      toast.success('Copied to clipboard!', {
        duration: 2000,
        position: 'bottom-center',
        style: {
          background: '#3a3a3a',
          color: '#f0f0f0',
          border: '1px solid #4a4a4a',
        },
        iconTheme: {
          primary: '#e07856',
          secondary: '#f0f0f0',
        },
      });
      // Re-focus input after copying
      focusInput();
    }).catch(() => {
      toast.error('Failed to copy', {
        duration: 2000,
        position: 'bottom-center',
        style: {
          background: '#3a3a3a',
          color: '#f0f0f0',
          border: '1px solid #f87171',
        },
      });
    });
  };

  // Handle input change and command filtering
  const handleInputChange = (value: string) => {
    setInputValue(value);

    // Show commands when user types /
    if (value.startsWith('/')) {
      const searchTerm = value.slice(1).toLowerCase();
      const filtered = COMMANDS.filter(cmd =>
        cmd.command.slice(1).toLowerCase().startsWith(searchTerm) ||
        cmd.description.toLowerCase().includes(searchTerm)
      );
      setFilteredCommands(filtered);
      setShowCommands(true);
    } else {
      setShowCommands(false);
    }
  };

  // Handle command selection
  const selectCommand = (command: string) => {
    setInputValue(command + ' ');
    setShowCommands(false);
    // Re-focus after selecting command
    focusInput();
  };

  // Sanitize message before sending (strip HTML tags)
  const sanitizeMessage = (text: string): string => {
    // Remove HTML/XML tags
    let cleaned = text.replace(/<[^>]*>/g, '');
    // Decode common HTML entities
    cleaned = cleaned
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&amp;/g, '&')
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/&nbsp;/g, ' ');
    return cleaned.trim();
  };

  const handleSend = async (message: string) => {
    if (message.trim()) {
      setShowCommands(false);

      // Sanitize message to strip any HTML/XML tags from paste operations
      const cleanMessage = sanitizeMessage(message);

      // Only handle /clear and /help locally, send all other commands to backend
      if (cleanMessage === '/clear') {
        setIsTyping(true);
        await onClearChat();
        setIsTyping(false);
        // Re-focus after clearing
        focusInput();
      } else if (cleanMessage === '/help') {
        // Show help message
        toast((t) => (
          <div style={{ maxWidth: '400px' }}>
            <strong style={{ display: 'block', marginBottom: '8px' }}>Available Commands:</strong>
            {COMMANDS.map(cmd => (
              <div key={cmd.command} style={{ marginBottom: '4px', fontSize: '13px' }}>
                <code style={{ color: '#e07856' }}>{cmd.command}</code> - {cmd.description}
              </div>
            ))}
          </div>
        ), {
          duration: 8000,
          position: 'top-center',
          style: {
            background: '#2a2a2a',
            color: '#f0f0f0',
            border: '1px solid #4a4a4a',
            padding: '16px',
          },
        });
        // Re-focus after showing help
        focusInput();
      } else {
        // Send cleaned message (all other messages including commands)
        onSendMessage(cleanMessage);
        setIsTyping(true);
        // Simulate typing indicator for better UX
        setTimeout(() => setIsTyping(false), 500);
        // Re-focus after sending
        setTimeout(focusInput, 100);
      }
      setInputValue('');
    }
  };



  // Global paste handler to strip HTML formatting
  useEffect(() => {
    const handlePaste = (e: ClipboardEvent) => {
      const target = e.target as HTMLElement;
      // Only intercept paste in textarea within message input
      if (target.tagName !== 'TEXTAREA') return;
      if (!target.closest('.cs-message-input')) return;

      e.preventDefault();
      // Get plain text from clipboard, stripping HTML
      const text = e.clipboardData?.getData('text/plain') || '';

      // Insert at cursor position
      const textarea = target as HTMLTextAreaElement;
      const start = textarea.selectionStart || 0;
      const end = textarea.selectionEnd || 0;
      const currentValue = inputValue || '';
      const newValue = currentValue.substring(0, start) + text + currentValue.substring(end);
      setInputValue(newValue);

      // Set cursor position after pasted text
      setTimeout(() => {
        textarea.selectionStart = textarea.selectionEnd = start + text.length;
      }, 0);
    };

    document.addEventListener('paste', handlePaste, true);
    return () => document.removeEventListener('paste', handlePaste, true);
  }, [inputValue]);

  // Format timestamp
  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();

    if (isToday) {
      return date.toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
      });
    }
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
  };

  // Show landing page when no messages
  if (messages.length === 0) {
    return (
      <div className="chat-interface landing">
        <Toaster />
        <div className="landing-container">
          <div className="landing-content">
            <img src="/chat/amiga-logo.png" alt="AMIGA Logo" className="landing-logo" />
            <div className="landing-input-wrapper">
              {showCommands && filteredCommands.length > 0 && (
                <div className="command-suggestions">
                  {filteredCommands.map(cmd => (
                    <div
                      key={cmd.command}
                      className="command-suggestion"
                      onClick={() => selectCommand(cmd.command)}
                    >
                      <code className="command-name">{cmd.command}</code>
                      <span className="command-desc">{cmd.description}</span>
                    </div>
                  ))}
                </div>
              )}
              <MessageInput
                placeholder="Ask me anything... (type / for commands)"
                value={inputValue}
                onChange={(val) => handleInputChange(val)}
                onSend={handleSend}
                disabled={!connected}
                attachButton={false}
                aria-label="Message input"
              />
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-interface">
      <Toaster />
      <div className="chat-header">
        <div className="chat-title">
          <img src="/chat/amiga-logo.png" alt="AMIGA" className="chat-logo" />
        </div>
      </div>

      <MainContainer>
        <ChatContainer>
          <MessageList
            typingIndicator={
              !connected ? (
                <TypingIndicator content="Connecting..." />
              ) : isTyping ? (
                <TypingIndicator content="Assistant is typing..." />
              ) : null
            }
          >
            {messages.map((msg) => (
              <Message
                key={msg.id}
                model={{
                  message: msg.content,
                  sentTime: new Date(msg.timestamp).toISOString(),
                  sender: msg.role === 'user' ? 'You' : 'Assistant',
                  direction: msg.role === 'user' ? 'outgoing' : 'incoming',
                  position: 'single',
                }}
              >
                <Message.CustomContent>
                  <div className="message-wrapper">
                    <div className="message-header">
                      {msg.role === 'user' && (
                        <div className="user-avatar" aria-label="Your message">
                          <span>You</span>
                        </div>
                      )}
                      {msg.role === 'assistant' && (
                        <div className="assistant-avatar" aria-label="Assistant message">
                          <img src="/chat/amiga-logo.png" alt="AI" className="avatar-logo" />
                        </div>
                      )}
                      <span className="message-time">{formatTime(msg.timestamp)}</span>
                    </div>
                    <div className="message-content">
                      {msg.role === 'assistant' ? (
                        <ReactMarkdown
                          components={{
                            code({ className, children, ...props }: any) {
                              const isInline = !className;
                              const match = /language-(\w+)/.exec(className || '');
                              const language = match ? match[1] : '';
                              const codeString = String(children).replace(/\n$/, '');

                              return isInline ? (
                                <code className="inline-code" {...props}>
                                  {children}
                                </code>
                              ) : (
                                <div className="code-block-wrapper">
                                  <div className="code-block-header">
                                    <span className="code-language">{language || 'code'}</span>
                                    <button
                                      className="copy-code-button"
                                      onClick={() => copyToClipboard(codeString)}
                                      aria-label="Copy code to clipboard"
                                    >
                                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                                        <path d="M5.75 4.75H10.25V1.75H5.75V4.75ZM4.5 1.75C4.5 1.05964 5.05964 0.5 5.75 0.5H10.25C10.9404 0.5 11.5 1.05964 11.5 1.75V4.75H13.25C13.9404 4.75 14.5 5.30964 14.5 6V14C14.5 14.6904 13.9404 15.25 13.25 15.25H2.75C2.05964 15.25 1.5 14.6904 1.5 14V6C1.5 5.30964 2.05964 4.75 2.75 4.75H4.5V1.75Z" fill="currentColor"/>
                                      </svg>
                                      Copy
                                    </button>
                                  </div>
                                  <SyntaxHighlighter
                                    language={language || 'text'}
                                    style={vscDarkPlus}
                                    customStyle={{
                                      margin: 0,
                                      borderRadius: '0 0 8px 8px',
                                      background: 'rgba(0, 0, 0, 0.3)',
                                    }}
                                  >
                                    {codeString}
                                  </SyntaxHighlighter>
                                </div>
                              );
                            },
                          }}
                        >
                          {msg.content}
                        </ReactMarkdown>
                      ) : (
                        <p>{msg.content}</p>
                      )}
                    </div>
                    <div className="message-actions">
                      <button
                        className="action-button"
                        onClick={() => copyToClipboard(msg.content)}
                        aria-label="Copy message"
                        title="Copy message"
                      >
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                          <path d="M5.75 4.75H10.25V1.75H5.75V4.75ZM4.5 1.75C4.5 1.05964 5.05964 0.5 5.75 0.5H10.25C10.9404 0.5 11.5 1.05964 11.5 1.75V4.75H13.25C13.9404 4.75 14.5 5.30964 14.5 6V14C14.5 14.6904 13.9404 15.25 13.25 15.25H2.75C2.05964 15.25 1.5 14.6904 1.5 14V6C1.5 5.30964 2.05964 4.75 2.75 4.75H4.5V1.75Z" fill="currentColor"/>
                        </svg>
                      </button>
                    </div>
                  </div>
                </Message.CustomContent>
              </Message>
            ))}
          </MessageList>
          {showCommands && filteredCommands.length > 0 && (
            <div className="command-suggestions">
              {filteredCommands.map(cmd => (
                <div
                  key={cmd.command}
                  className="command-suggestion"
                  onClick={() => selectCommand(cmd.command)}
                >
                  <code className="command-name">{cmd.command}</code>
                  <span className="command-desc">{cmd.description}</span>
                </div>
              ))}
            </div>
          )}
          <MessageInput
            placeholder="Type your message... (type / for commands)"
            value={inputValue}
            onChange={(val) => handleInputChange(val)}
            onSend={handleSend}
            disabled={!connected}
            attachButton={false}
            aria-label="Message input"
          />
        </ChatContainer>
      </MainContainer>
    </div>
  );
};
