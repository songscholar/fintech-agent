import type {
  ClipboardEvent,
  DragEvent,
  MouseEvent,
  ChangeEvent,
  KeyboardEvent,
  CompositionEvent
} from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import clsx from 'clsx';

type UploadItem = {
  id: string;
  name: string;
  size: number;
  type: string;
};

type Message = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  attachments?: UploadItem[];
};

const initialConversations = [
  {
    id: 'c1',
    title: '周报梳理',
    snippet: '整理本周亮点与下周计划',
    time: '今天'
  },
  {
    id: 'c2',
    title: '方案润色',
    snippet: '把产品介绍写得更清晰',
    time: '昨天'
  },
  {
    id: 'c3',
    title: '市场点评',
    snippet: '简要总结行业动态与风险',
    time: '周二'
  }
];

const prompts = [
  '把这段文字改写成更简洁、口语化的说明：',
  '帮我写一份周会的开场稿，语气平和且有信心。',
  '生成一条朋友圈文案，主题是团队上线新功能。'
];

const initialMessages: Message[] = [
  {
    id: 'm1',
    role: 'assistant',
    content: '你好，我是你的 AI 助手，可以陪你写作、总结或推敲想法。想先聊点什么？',
    timestamp: '今天 · 09:18'
  },
  {
    id: 'm2',
    role: 'user',
    content: '写一段产品介绍，突出体验流畅、视觉简洁、数据安全。',
    timestamp: '今天 · 09:19'
  },
  {
    id: 'm3',
    role: 'assistant',
    content:
      '好的，这是一个简洁版本：\n\n我们提供极简且顺滑的产品体验，关键操作无需复杂学习。界面保持留白与柔和对比，让信息更聚焦。数据传输与存储采用加密与分级权限，确保团队协作时的安全与可控。',
    timestamp: '今天 · 09:19'
  }
];

function App() {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [input, setInput] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [activeId] = useState(initialConversations[0].id);
  const [user, setUser] = useState<{ name: string; email: string } | null>(null);
  const [loginForm, setLoginForm] = useState({ name: '', email: '' });
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [showLogin, setShowLogin] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [menuClosing, setMenuClosing] = useState(false);
  const [hoverMsgId, setHoverMsgId] = useState<string | null>(null);
  const [editingMsgId, setEditingMsgId] = useState<string | null>(null);
  const [isComposing, setIsComposing] = useState(false);
  const hideMenuTimer = useRef<number | null>(null);
  const hideMenuCloseTimer = useRef<number | null>(null);
  const avatarWrapRef = useRef<HTMLDivElement | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [editingContext, setEditingContext] = useState<{
    userId: string;
    assistantId?: string;
  } | null>(null);

  const accentColor = useMemo(() => {
    const palette = ['#6c5ce7', '#22a2c3', '#6ba368'];
    return palette[messages.length % palette.length];
  }, [messages.length]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  useEffect(() => {
    return () => {
      if (hideMenuTimer.current) {
        window.clearTimeout(hideMenuTimer.current);
      }
      if (hideMenuCloseTimer.current) {
        window.clearTimeout(hideMenuCloseTimer.current);
      }
    };
  }, []);

  const mockReply = (text: string) => {
    const brief = text.length > 36 ? `${text.slice(0, 36)}...` : text || '你的想法';
    return `好的，我理解了「${brief}」，下面给出一个更克制且清晰的版本，并提示可拓展的点：\n\n1) 简化主线，保留重点。\n2) 增加一句场景化示例。\n3) 用一句收尾强调价值。`;
  };

  const handleSend = (preset?: string) => {
    const content = (preset ?? input).trim();
    if ((!content && uploads.length === 0) || isThinking) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      timestamp: '刚刚',
      attachments: uploads
    };
    setMessages((prev) => {
      if (editingContext) {
        const idx = prev.findIndex((m) => m.id === editingContext.userId);
        let base = prev;
        if (idx !== -1) {
          const assistantAfter = editingContext.assistantId
            ? prev.find((m) => m.id === editingContext.assistantId)
            : prev.slice(idx + 1).find((m) => m.role === 'assistant');
          const assistantId = assistantAfter?.id;
          base = prev.filter((m, i) => {
            if (i === idx) return false;
            if (assistantId && m.id === assistantId) return false;
            return true;
          });
        }
        return [...base, userMsg];
      }
      return [...prev, userMsg];
    });
    setInput('');
    setUploads([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    setEditingMsgId(null);
    setEditingContext(null);
    setIsThinking(true);

    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: mockReply(content),
          timestamp: '几秒前'
        }
      ]);
      setIsThinking(false);
    }, 680);
  };

  const handleFiles = (files: FileList | null) => {
    if (!files) return;
    const next: UploadItem[] = Array.from(files).map((file) => ({
      id: crypto.randomUUID(),
      name: file.name,
      size: file.size,
      type: file.type
    }));
    setUploads((prev) => [...prev, ...next].slice(-5));
  };

  const openFilePicker = () => {
    fileInputRef.current?.click();
  };

  const handlePaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    if (e.clipboardData?.files?.length) {
      handleFiles(e.clipboardData.files);
    }
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer?.files?.length) {
      handleFiles(e.dataTransfer.files);
    }
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleLogin = () => {
    if (!loginForm.name.trim()) return;
    setUser({
      name: loginForm.name.trim(),
      email: loginForm.email.trim() || '未填写'
    });
    setShowLogin(false);
  };

  const handleLogout = () => {
    setUser(null);
    setUploads([]);
    setInput('');
    setShowMenu(false);
  };

  const handleEditProfile = () => {
    setLoginForm({
      name: user?.name ?? '',
      email: user?.email === '未填写' ? '' : user?.email ?? ''
    });
    setShowMenu(false);
    setShowLogin(true);
  };

  const removeUpload = (id: string) => {
    setUploads((prev) => prev.filter((f) => f.id !== id));
  };
  /*设置下拉列表修改时间，默认是毫秒*/ 
  const startHideMenu = () => {
    if (hideMenuTimer.current) window.clearTimeout(hideMenuTimer.current);
    if (hideMenuCloseTimer.current) window.clearTimeout(hideMenuCloseTimer.current);

    hideMenuTimer.current = window.setTimeout(() => {
      setMenuClosing(true);
      hideMenuCloseTimer.current = window.setTimeout(() => {
        setShowMenu(false);
        setMenuClosing(false);
      }, 200); // 对应 CSS 退出动画时长
    }, 250);
  };

  const stopHideMenu = () => {
    if (hideMenuTimer.current) {
      window.clearTimeout(hideMenuTimer.current);
      hideMenuTimer.current = null;
    }
    if (hideMenuCloseTimer.current) {
      window.clearTimeout(hideMenuCloseTimer.current);
      hideMenuCloseTimer.current = null;
    }
    setMenuClosing(false);
  };

  const handleAvatarLeave = (e: MouseEvent<HTMLDivElement>) => {
    const next = e.relatedTarget as Node | null;
    if (avatarWrapRef.current && next && avatarWrapRef.current.contains(next)) return;
    startHideMenu();
  };

  const handleMenuLeave = (e: MouseEvent<HTMLDivElement>) => {
    const next = e.relatedTarget as Node | null;
    if (avatarWrapRef.current && next && avatarWrapRef.current.contains(next)) return;
    startHideMenu();
  };

  const resizeTextarea = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    const style = window.getComputedStyle(el);
    const lineHeight = parseFloat(style.lineHeight || '20');
    const padding =
      parseFloat(style.paddingTop || '0') + parseFloat(style.paddingBottom || '0');
    const maxHeight = lineHeight * 5 + padding;
    const nextHeight = Math.min(el.scrollHeight, maxHeight);
    el.style.height = `${nextHeight}px`;
    el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden';
  };

  const handleInputChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    resizeTextarea();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleCompositionStart = (_e: CompositionEvent<HTMLTextAreaElement>) => {
    setIsComposing(true);
  };

  const handleCompositionEnd = (_e: CompositionEvent<HTMLTextAreaElement>) => {
    setIsComposing(false);
  };

  useEffect(() => {
    resizeTextarea();
  }, [input]);

  const latestAssistantId = useMemo(() => {
    const last = [...messages].reverse().find((m) => m.role === 'assistant');
    return last?.id ?? null;
  }, [messages]);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
  };

  const handleRegenerate = (msg: Message) => {
    if (msg.role !== 'assistant') return;
    const idx = messages.findIndex((m) => m.id === msg.id);
    const sourceUser = [...messages.slice(0, idx)].reverse().find((m) => m.role === 'user');
    const prompt = sourceUser?.content ?? msg.content;
    setIsThinking(true);
    setTimeout(() => {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msg.id
            ? { ...m, id: crypto.randomUUID(), content: mockReply(prompt), timestamp: '刚刚' }
            : m
        )
      );
      setIsThinking(false);
    }, 600);
  };

  const handleEditUserMessage = (msg: Message) => {
    setEditingMsgId(msg.id);
    const idx = messages.findIndex((m) => m.id === msg.id);
    const assistantAfter = messages.slice(idx + 1).find((m) => m.role === 'assistant');
    setEditingContext({ userId: msg.id, assistantId: assistantAfter?.id });
    setInput(msg.content);
    setUploads(msg.attachments ?? []);
    textareaRef.current?.focus();
    resizeTextarea();
  };

  return (
    <div className="layout">
      <div className="ambient softly" />
      <div className="ambient glow" />

      <aside className="rail glass">
        <div className="brand">
          <div className="logo">
            <div className="logo-core" />
          </div>
          <div>
            <div className="brand-title">FinChat</div>
            <div className="brand-sub">简洁 · 克制 · 清晰</div>
          </div>
        </div>

        <button className="pill-btn primary">+ 新建对话</button>

        <div className="rail-block">
          <div className="section-head">最近</div>
          <div className="list">
            {initialConversations.map((item) => (
              <button
                key={item.id}
                className={clsx('list-item', activeId === item.id && 'active')}
              >
                <div className="item-title">{item.title}</div>
                <div className="item-sub">{item.snippet}</div>
                <div className="item-meta">{item.time}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="rail-footer">
          <div className="tag">浅色</div>
          <div className="tag">透明玻璃</div>
        </div>
      </aside>

      <main className="main">
        <header className="top glass">
          <div className="top-left">
            <div className="title">对话</div>
            <div className="status">
              <span className="dot" style={{ background: accentColor }} />
              连接稳定
            </div>
          </div>
          <div className="top-actions">
            <button className="pill-btn ghost">历史</button>
            <button className="pill-btn ghost">偏好</button>
            {user ? (
              <div
                className="avatar-wrap"
                ref={avatarWrapRef}
                onMouseEnter={() => {
                  stopHideMenu();
                  if (!showMenu) {
                    setShowMenu(true);
                  }
                }}
                onMouseLeave={handleAvatarLeave}
              >
                <button
                  className="avatar-btn"
                  onClick={() => {
                    if (showMenu) {
                      startHideMenu();
                    } else {
                      stopHideMenu();
                      setShowMenu(true);
                    }
                  }}
                  aria-label="用户菜单"
                  type="button"
                >
                  {user.name.slice(0, 1).toUpperCase()}
                </button>
                {showMenu && (
                  <div
                    className={clsx('menu glass', menuClosing && 'closing')}
                    onMouseEnter={stopHideMenu}
                    onMouseLeave={handleMenuLeave}
                  >
                    <button className="menu-item" onClick={handleEditProfile}>
                      修改资料
                    </button>
                    <button className="menu-item" onClick={handleLogout}>
                      退出
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <button className="pill-btn subtle" onClick={() => setShowLogin(true)}>
                登录
              </button>
            )}
          </div>
        </header>

        <section className="hero glass">
          <div>
            <div className="eyebrow">轻盈风格</div>
            <div className="hero-title">留白、柔和、无负担的对话体验</div>
            <div className="hero-desc">
              更素的配色、更柔的阴影与玻璃质感，弱化噪点，保留重点。
            </div>
            <div className="chips">
              <span className="chip">透明玻璃</span>
              <span className="chip">留白布局</span>
              <span className="chip">轻微动效</span>
            </div>
          </div>
          <div className="mini-cards">
            <div className="mini glass">
              <div className="mini-title">写作</div>
              <div className="mini-desc">摘要、润色、改写，保持克制语气。</div>
            </div>
            <div className="mini glass">
              <div className="mini-title">分析</div>
              <div className="mini-desc">拆解要点，给出循序渐进的建议。</div>
            </div>
            <div className="mini glass">
              <div className="mini-title">灵感</div>
              <div className="mini-desc">随时记录，再帮你整理成条理清晰的版本。</div>
            </div>
          </div>
        </section>

        <section className="chat glass">
          <div className="messages">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={clsx('message', msg.role === 'user' ? 'user' : 'assistant')}
                onMouseEnter={() => setHoverMsgId(msg.id)}
                onMouseLeave={() => setHoverMsgId((prev) => (prev === msg.id ? null : prev))}
              >
                <div className="avatar">{msg.role === 'user' ? '🙂' : '✨'}</div>
                <div className="bubble">
                  <div className="bubble-meta">
                    <span className="who">{msg.role === 'user' ? '你' : 'AI'}</span>
                    <span className="time">{msg.timestamp}</span>
                  </div>
                  <div className="bubble-text">
                    {msg.content.split('\n').map((line, idx) => (
                      <p key={idx}>{line}</p>
                    ))}
                  </div>
                  {msg.role === 'assistant' && (
                    <div
                      className={clsx(
                        'msg-actions',
                        (hoverMsgId === msg.id || msg.id === latestAssistantId) && 'visible'
                      )}
                    >
                      <button className="action-btn" onClick={() => handleCopy(msg.content)}>
                        复制
                      </button>
                      <button className="action-btn" onClick={() => handleRegenerate(msg)}>
                        重新生成
                      </button>
                      <button className="action-btn">👍</button>
                      <button className="action-btn">👎</button>
                    </div>
                  )}
                  {msg.role === 'user' && (
                    <div
                      className={clsx('msg-actions', hoverMsgId === msg.id && 'visible')}
                    >
                      <button className="action-btn" onClick={() => handleCopy(msg.content)}>
                        复制
                      </button>
                      <button className="action-btn" onClick={() => handleEditUserMessage(msg)}>
                        重新编辑
                      </button>
                    </div>
                  )}
                  {!!msg.attachments?.length && (
                    <div className="attachments">
                      {msg.attachments.map((file) => (
                        <span key={file.id} className="attach-pill">
                          📎 {file.name}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {isThinking && (
              <div className="message assistant thinking">
                <div className="avatar">✨</div>
                <div className="bubble">
                  <div className="bubble-meta">
                    <span className="who">AI</span>
                    <span className="time">输入中…</span>
                  </div>
                  <div className="loader">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <div className="prompt-grid">
            {prompts.map((prompt) => (
              <button
                key={prompt}
                className="prompt"
                onClick={() => handleSend(prompt)}
                disabled={!user}
              >
                {prompt}
              </button>
            ))}
          </div>

          <div className="composer">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInputChange}
              placeholder={
                user ? '和我聊聊：描述你的想法或想要的风格' : '请先登录后再开始对话'
              }
              rows={1}
              onPaste={handlePaste}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onKeyDown={handleKeyDown}
              onCompositionStart={handleCompositionStart}
              onCompositionEnd={handleCompositionEnd}
              disabled={!user}
            />
            {uploads.length > 0 && (
              <div className="uploads-inline">
                {uploads.map((file) => (
                  <span key={file.id} className="upload-pill">
                    {file.name} · {(file.size / 1024).toFixed(1)} KB
                    <button
                      className="close-upload"
                      onClick={() => removeUpload(file.id)}
                      aria-label="移除附件"
                      type="button"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className={clsx('composer-actions', isDragging && 'dragging')}>
              <div className="actions-left">
                <button
                  className="icon-btn ghost"
                  onClick={openFilePicker}
                  title="上传文件 / 图片"
                  type="button"
                >
                  📎
                </button>
                <input
                  id="fileUpload"
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept="image/*,.pdf,.doc,.docx,.txt,.md"
                  onChange={(e) => handleFiles(e.target.files)}
                  style={{ display: 'none' }}
                />
                <div className="hint">Shift+Enter 换行 · Enter 发送 · 支持粘贴/拖拽文件</div>
              </div>
              <button
                className="pill-btn primary"
                onClick={() => handleSend()}
                disabled={(!input.trim() && uploads.length === 0) || isThinking}
              >
                发送
              </button>
            </div>
          </div>
        </section>
      </main>

      {showLogin && (
        <div className="auth-overlay" onClick={() => setShowLogin(false)}>
          <div className="auth-card glass" onClick={(e) => e.stopPropagation()}>
            <div className="auth-title">登录</div>
            <div className="auth-desc">填写昵称与邮箱，个性化你的体验。</div>
            <div className="form">
              <label className="field">
                <span>昵称</span>
                <input
                  type="text"
                  value={loginForm.name}
                  onChange={(e) => setLoginForm((prev) => ({ ...prev, name: e.target.value }))}
                  placeholder="如：Alex"
                />
              </label>
              <label className="field">
                <span>邮箱（可选）</span>
                <input
                  type="email"
                  value={loginForm.email}
                  onChange={(e) => setLoginForm((prev) => ({ ...prev, email: e.target.value }))}
                  placeholder="you@example.com"
                />
              </label>
            </div>
            <button className="pill-btn primary" onClick={handleLogin} disabled={!loginForm.name.trim()}>
              登录
            </button>
            <div className="auth-hint">可随时在右上角头像菜单中退出或修改资料。</div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;

