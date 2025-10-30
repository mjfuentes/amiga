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
import { TaskModal } from './TaskModal';
import { TokenIndicator } from './TokenIndicator';
import './ChatInterface.css';

interface ChatInterfaceProps {
  messages: MessageType[];
  connected: boolean;
  onSendMessage: (message: string) => void;
  onClearChat: () => Promise<boolean>;
  onLogout: () => void;
  chatViewActive: boolean;
  setChatViewActive: (active: boolean) => void;
  totalTokens: {
    input: number;
    output: number;
  };
}

// Available commands with descriptions
const COMMANDS = [
  { command: '/help', description: 'Show available commands' },
  { command: '/status', description: 'Show active tasks and recent errors' },
  { command: '/clear', description: 'Clear conversation history' },
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
  chatViewActive,
  setChatViewActive,
  totalTokens,
}) => {
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [showCommands, setShowCommands] = useState(false);
  const [filteredCommands, setFilteredCommands] = useState(COMMANDS);
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const [isShuttingDown, setIsShuttingDown] = useState(false);
  const [taskStatusMap, setTaskStatusMap] = useState<Map<string, string>>(new Map());
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [isTaskModalOpen, setIsTaskModalOpen] = useState(false);
  const lastMessageCountRef = useRef(messages.length);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const inputListenerAttachedRef = useRef(false);
  const handleSendRef = useRef<((message: string) => Promise<void>) | null>(null);
  const lastUserMessageRef = useRef<HTMLDivElement | null>(null);
  const cursorPositionRef = useRef<number | null>(null);

  // Helper function to focus the input
  const focusInput = () => {
    // Find the textarea within the MessageInput component
    const textarea = document.querySelector('.cs-message-input__content-editor') as HTMLTextAreaElement;
    if (textarea) {
      textarea.focus();
      inputRef.current = textarea;
    }
  };

  // Helper function to scroll to show the user's sent message and subsequent conversation
  const scrollToUserMessage = () => {
    if (lastUserMessageRef.current) {
      // Smooth scroll to bring the last user message into view at the top
      lastUserMessageRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
        inline: 'nearest'
      });
    }
  };

  // Handle command selection
  const selectCommand = (command: string) => {
    setInputValue(command + ' ');
    setShowCommands(false);
    // Re-focus after selecting command
    focusInput();
  };

  // Attach input listener for command autocomplete
  const attachInputListener = useCallback(() => {
    if (inputListenerAttachedRef.current) return;

    const textarea = document.querySelector('.cs-message-input__content-editor') as HTMLTextAreaElement;
    if (textarea) {
      const handleInput = (e: Event) => {
        const target = e.target as HTMLTextAreaElement;
        const value = target.value || target.textContent || '';
        // Store cursor position before state update
        cursorPositionRef.current = target.selectionStart;
        handleInputChange(value);
      };

      const handleKeyDown = (e: KeyboardEvent) => {
        if (!showCommands || filteredCommands.length === 0) return;

        switch (e.key) {
          case 'ArrowDown':
            e.preventDefault();
            setHighlightedIndex(prev => (prev + 1) % filteredCommands.length);
            break;
          case 'ArrowUp':
            e.preventDefault();
            setHighlightedIndex(prev => (prev - 1 + filteredCommands.length) % filteredCommands.length);
            break;
          case 'Enter':
            if (showCommands) {
              e.preventDefault();
              const selectedCommand = filteredCommands[highlightedIndex].command;
              // Insert command and immediately send it
              setInputValue(selectedCommand);
              setShowCommands(false);
              // Send the command using the ref
              setTimeout(() => {
                if (handleSendRef.current) {
                  handleSendRef.current(selectedCommand);
                }
              }, 0);
            }
            break;
          case 'Escape':
            e.preventDefault();
            setShowCommands(false);
            break;
        }
      };

      textarea.addEventListener('input', handleInput);
      textarea.addEventListener('keydown', handleKeyDown);
      inputListenerAttachedRef.current = true;
      inputRef.current = textarea;

      // Cleanup on unmount
      return () => {
        textarea.removeEventListener('input', handleInput);
        textarea.removeEventListener('keydown', handleKeyDown);
        inputListenerAttachedRef.current = false;
      };
    }
  }, [showCommands, filteredCommands, highlightedIndex]);

  // Focus the input on mount and when messages change
  useEffect(() => {
    // Small delay to ensure DOM is ready
    const timer = setTimeout(() => {
      focusInput();
      attachInputListener();
    }, 100);
    return () => clearTimeout(timer);
  }, [attachInputListener]);

  // Restore cursor position after input value changes
  useEffect(() => {
    if (cursorPositionRef.current !== null && inputRef.current) {
      const position = cursorPositionRef.current;
      // Use setTimeout to ensure DOM has updated
      setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.selectionStart = position;
          inputRef.current.selectionEnd = position;
        }
        cursorPositionRef.current = null;
      }, 0);
    }
  }, [inputValue]);

  // Re-focus after sending messages and handle auto-scroll
  useEffect(() => {
    if (messages.length > lastMessageCountRef.current) {
      const lastMessage = messages[messages.length - 1];

      // If user just sent a message, scroll to show it
      if (lastMessage.role === 'user') {
        setTimeout(() => {
          scrollToUserMessage();
        }, 100);
      }

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

  // Fetch task status data via SSE
  useEffect(() => {
    let eventSource: EventSource | null = null;
    let retryCount = 0;
    let retryTimeout: NodeJS.Timeout | null = null;
    const MAX_RETRY_DELAY = 30000; // 30 seconds max

    const connectSSE = () => {
      try {
        // Use same base URL as WebSocket (respects REACT_APP_SOCKET_URL)
        const baseUrl = process.env.REACT_APP_SOCKET_URL || window.location.origin;
        const sseUrl = `${baseUrl}/api/stream/metrics?hours=24`;
        eventSource = new EventSource(sseUrl);

        eventSource.onopen = () => {
          console.log('ChatInterface SSE connection established');
          retryCount = 0; // Reset retry count on successful connection
        };

        eventSource.onmessage = (event) => {
          try {
            // Skip empty or heartbeat messages
            if (!event.data || event.data.trim() === '' || event.data.trim() === ': heartbeat') {
              return;
            }

            const data = JSON.parse(event.data);
            const tasks = data?.overview?.task_statistics?.recent_24h?.tasks;
            if (tasks && Array.isArray(tasks)) {
              const statusMap = new Map<string, string>();
              tasks.forEach((task: any) => {
                statusMap.set(task.task_id, task.status);
              });
              setTaskStatusMap(statusMap);
            }
          } catch (error) {
            console.error('Failed to parse SSE data:', error);
          }
        };

        eventSource.onerror = (error) => {
          // Only log errors after first retry attempt (suppress initial connection errors)
          if (retryCount > 0) {
            console.warn('ChatInterface SSE connection failed, retrying...', {
              readyState: eventSource?.readyState,
              retryCount
            });
          }

          eventSource?.close();

          // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s (max)
          const delay = Math.min(1000 * Math.pow(2, retryCount), MAX_RETRY_DELAY);
          retryCount++;

          retryTimeout = setTimeout(connectSSE, delay);
        };
      } catch (error) {
        console.error('Failed to create EventSource:', error);
      }
    };

    // Small delay before initial connection to ensure server is ready
    const initialDelay = setTimeout(connectSSE, 500);

    return () => {
      clearTimeout(initialDelay);
      if (retryTimeout) {
        clearTimeout(retryTimeout);
      }
      if (eventSource) {
        eventSource.close();
      }
    };
  }, []);

  // Copy to clipboard helper
  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      toast.success('Copied to clipboard!', {
        duration: 2000,
        position: 'bottom-right',
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
        position: 'bottom-right',
        style: {
          background: '#3a3a3a',
          color: '#f0f0f0',
          border: '1px solid #f87171',
        },
      });
    });
  };

  // Get status color for task status indicators
  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'running':
        return '#6a9fb5'; // Blue
      case 'completed':
        return '#7cb342'; // Green
      case 'failed':
        return '#f87171'; // Red
      case 'pending':
        return '#888'; // Gray
      case 'stopped':
        return '#888'; // Gray
      default:
        return 'transparent';
    }
  };

  // Process text to linkify task IDs (e.g., #task_abc123 or #47f03a)
  const linkifyTaskIds = (text: string): React.ReactNode => {
    // Match pattern: #<task_id> where task_id is either:
    // - task_[alphanumeric with underscores]
    // - 6-character hex string (for short task IDs like #47f03a)
    const taskIdRegex = /#((?:task_[a-zA-Z0-9_]+)|(?:[a-f0-9]{6}))/g;
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let match;

    while ((match = taskIdRegex.exec(text)) !== null) {
      // Add text before match
      if (match.index > lastIndex) {
        parts.push(text.substring(lastIndex, match.index));
      }

      // Add clickable link for task ID with status indicator
      const taskId = match[1]; // Extract task_xxx or hex without #
      // For short hex IDs, use the hex directly; for task_ format, keep as is
      const urlTaskId = taskId.startsWith('task_') ? taskId : `task_${taskId}`;
      const status = taskStatusMap.get(urlTaskId);
      const statusColor = status ? getStatusColor(status) : 'transparent';

      parts.push(
        <a
          key={`task-${taskId}-${match.index}`}
          href={`/dashboard#${urlTaskId}?ref=chat`}
          className="task-link"
          data-status={status || 'running'}
          onClick={(e) => {
            e.preventDefault();
            // Open task modal instead of navigating
            setSelectedTaskId(taskId);
            setIsTaskModalOpen(true);
          }}
          title={`Click to view in dashboard${status ? ` (${status})` : ''}`}
        >
          {status && (
            <span
              className="task-status-dot"
              style={{ backgroundColor: statusColor }}
              aria-label={`Task status: ${status}`}
            />
          )}
          #{taskId}
        </a>
      );

      lastIndex = match.index + match[0].length;
    }

    // Add remaining text
    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }

    return parts.length > 0 ? parts : text;
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
      setHighlightedIndex(0); // Reset to first command
      setShowCommands(true);
    } else {
      setShowCommands(false);
    }
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

  const handleSend = useCallback(async (message: string) => {
    /**
     * NAVIGATION TRIGGER: Landing → Chat View
     * ========================================
     *
     * This handles the transition from the landing page to the full chat interface.
     *
     * Behavior:
     * - Empty Enter on landing: Activates chat view (shows sidebars) without sending
     * - Any text + Enter: Sends message AND activates chat view
     *
     * This ensures the sidebars appear as soon as the user engages with input,
     * creating a smooth reveal effect from the clean landing page to full UI.
     */
    // Handle empty Enter press on landing page - activate chat view without sending message
    if (!message.trim() && messages.length === 0) {
      setChatViewActive(true);
      return;
    }

    if (message.trim()) {
      setShowCommands(false);

      // Sanitize message to strip any HTML/XML tags from paste operations
      const cleanMessage = sanitizeMessage(message);

      // Clear input immediately after sending
      setInputValue('');

      // Only handle /clear and /help locally, send all other commands to backend
      if (cleanMessage === '/clear') {
        // Only animate if there are messages (chat has begun)
        if (messages.length > 0) {
          setIsShuttingDown(true);
          // Wait for animation to complete (600ms) before clearing
          await new Promise(resolve => setTimeout(resolve, 600));
        }
        setIsTyping(true);
        await onClearChat();
        setIsTyping(false);
        setIsShuttingDown(false);
        // Reset chat view to landing page
        setChatViewActive(false);
        // Re-focus after clearing (with delay for re-render)
        setTimeout(focusInput, 100);
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
          duration: 4000,
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
        setIsTyping(true);
        onSendMessage(cleanMessage);
        // Re-focus after sending
        setTimeout(focusInput, 100);
      }
    }
  }, [messages.length, onClearChat, onSendMessage, setChatViewActive]);

  // Update ref when handleSend changes
  useEffect(() => {
    handleSendRef.current = handleSend;
  }, [handleSend]);

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

  /**
   * LANDING PAGE RENDERING
   * ======================
   *
   * Shows clean landing view when:
   * - No messages have been sent (messages.length === 0)
   * - Chat view not activated (chatViewActive === false)
   *
   * Landing UI features:
   * - Centered AMIGA logo (clickable → dashboard)
   * - Large input box with command autocomplete
   * - NO sidebars (TaskSidebar and SessionsSidebar hidden via App.tsx showSidebar)
   *
   * Transition trigger:
   * - User types anything → handleSend activates chatViewActive
   * - Sidebars appear (controlled by App.tsx)
   * - Layout changes from centered to full chat interface
   */
  // Show landing page when no messages and chat view not active
  if (messages.length === 0 && !chatViewActive) {
    return (
      <div className="chat-interface landing">
        <Toaster position="bottom-right" />
        <div className="landing-container">
          <div className="landing-content">
            <img
              src="/amiga-logo.png"
              alt="AMIGA Logo"
              className="landing-logo clickable"
              onClick={() => window.location.href = '/dashboard'}
              title="View monitoring dashboard"
            />
            <div className="landing-input-wrapper">
              {showCommands && filteredCommands.length > 0 && (
                <div className="command-suggestions">
                  {filteredCommands.map((cmd, idx) => (
                    <div
                      key={cmd.command}
                      className={`command-suggestion ${idx === highlightedIndex ? 'highlighted' : ''}`}
                      onClick={() => selectCommand(cmd.command)}
                    >
                      <code className="command-name">{cmd.command}</code>
                      <span className="command-desc">{cmd.description}</span>
                    </div>
                  ))}
                </div>
              )}
              <MessageInput
                placeholder="How can I help? (type / for commands)"
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
    <div className={`chat-interface ${isShuttingDown ? 'shutting-down' : ''}`}>
      <Toaster position="bottom-right" />
      <div className="chat-header">
        <div className="chat-title">
          <img
            src="/amiga-logo.png"
            alt="AMIGA"
            className="chat-logo clickable"
            onClick={() => window.location.href = '/dashboard'}
            title="View monitoring dashboard"
          />
        </div>
        <TokenIndicator totalTokens={totalTokens} />
      </div>

      <MainContainer>
        <ChatContainer>
          <MessageList
            typingIndicator={
              !connected ? (
                <TypingIndicator content="Connecting..." />
              ) : isTyping ? (
                <TypingIndicator content="thinking..." />
              ) : null
            }
          >
            {messages.map((msg, index) => (
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
                  <div
                    className="message-wrapper"
                    ref={msg.role === 'user' && index === messages.length - 1 ? lastUserMessageRef : null}
                  >
                    <div className="message-header">
                      {msg.role === 'user' && (
                        <div className="user-avatar" aria-label="Your message" />
                      )}
                      {msg.role === 'assistant' && (
                        <div className="assistant-avatar" aria-label="Assistant message">
                          <img src="/amiga-logo.png" alt="AI" className="avatar-logo" />
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

                              // Check if inline code contains a task ID (e.g., #task_abc, #abc123, task_abc, or abc123)
                              if (isInline) {
                                const taskIdMatch = /^#?((?:task_[a-zA-Z0-9_]+)|(?:[a-f0-9]{6}))$/.exec(codeString);
                                if (taskIdMatch) {
                                  const taskId = taskIdMatch[1];
                                  const urlTaskId = taskId.startsWith('task_') ? taskId : `task_${taskId}`;
                                  const status = taskStatusMap.get(urlTaskId);
                                  const statusColor = status ? getStatusColor(status) : 'transparent';
                                  return (
                                    <a
                                      href={`/dashboard#${urlTaskId}?ref=chat`}
                                      className="task-link inline-code"
                                      data-status={status || 'running'}
                                      onClick={(e) => {
                                        e.preventDefault();
                                        // Open task modal
                                        setSelectedTaskId(urlTaskId);
                                        setIsTaskModalOpen(true);
                                      }}
                                      title={`Click to view in dashboard${status ? ` (${status})` : ''}`}
                                      {...props}
                                    >
                                      {status && (
                                        <span
                                          className="task-status-dot"
                                          style={{ backgroundColor: statusColor }}
                                          aria-label={`Task status: ${status}`}
                                        />
                                      )}
                                      {codeString}
                                    </a>
                                  );
                                }

                                // Regular inline code
                                return (
                                  <code className="inline-code" {...props}>
                                    {children}
                                  </code>
                                );
                              }

                              // Code blocks
                              return (
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
                            p({ children }: any) {
                              // Process text nodes to linkify task IDs
                              if (typeof children === 'string') {
                                return <p>{linkifyTaskIds(children)}</p>;
                              }
                              // Handle arrays of children (mixed content)
                              if (Array.isArray(children)) {
                                const processedChildren = children.map((child, idx) => {
                                  if (typeof child === 'string') {
                                    return <React.Fragment key={idx}>{linkifyTaskIds(child)}</React.Fragment>;
                                  }
                                  return child;
                                });
                                return <p>{processedChildren}</p>;
                              }
                              return <p>{children}</p>;
                            },
                            text({ children }: any) {
                              // Process plain text nodes
                              if (typeof children === 'string') {
                                return <>{linkifyTaskIds(children)}</>;
                              }
                              return <>{children}</>;
                            },
                          }}
                        >
                          {msg.content}
                        </ReactMarkdown>
                      ) : (
                        <p>{linkifyTaskIds(msg.content)}</p>
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
        </ChatContainer>
        <div className="message-input-wrapper">
          {showCommands && filteredCommands.length > 0 && (
            <div className="command-suggestions">
              {filteredCommands.map((cmd, idx) => (
                <div
                  key={cmd.command}
                  className={`command-suggestion ${idx === highlightedIndex ? 'highlighted' : ''}`}
                  onClick={() => selectCommand(cmd.command)}
                >
                  <code className="command-name">{cmd.command}</code>
                  <span className="command-desc">{cmd.description}</span>
                </div>
              ))}
            </div>
          )}
          <MessageInput
            key={`chat-input-${connected}-${messages.length}`}
            placeholder="Type your message... (type / for commands)"
            value={inputValue}
            onChange={(val) => handleInputChange(val)}
            onSend={handleSend}
            disabled={!connected}
            attachButton={false}
            aria-label="Message input"
          />
        </div>
      </MainContainer>

      {/* Task Modal */}
      <TaskModal
        taskId={selectedTaskId}
        isOpen={isTaskModalOpen}
        onClose={() => {
          setIsTaskModalOpen(false);
          setSelectedTaskId(null);
        }}
      />
    </div>
  );
};
