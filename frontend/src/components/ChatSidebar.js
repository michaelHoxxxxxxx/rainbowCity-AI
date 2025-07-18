import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { isAuthenticated } from '../services/auth_service';
import './ChatSidebar.css';

function ChatSidebar({ conversations, onSelectConversation, onCreateNewChat }) {
  console.log('ChatSidebar received conversations:', conversations);
  const [searchTerm, setSearchTerm] = useState('');
  // 侧边栏始终显示，不再需要展开状态
  const [isExpanded, setIsExpanded] = useState(true);
  const [isVisible, setIsVisible] = useState(true);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  
  // 检查用户登录状态
  useEffect(() => {
    const checkLoginStatus = () => {
      const loginStatus = isAuthenticated();
      setIsLoggedIn(loginStatus);
    };
    
    checkLoginStatus();
    
    // 清理函数
    return () => {
      document.body.classList.remove('sidebar-expanded');
    };
  }, []);  // 依赖项为空数组，仅在组件挂载时执行一次
  
  // 处理搜索输入变化
  const handleSearchChange = (e) => {
    setSearchTerm(e.target.value);
  };
  
  // 过滤对话列表
  const filteredConversations = conversations && Array.isArray(conversations) ? conversations.filter(conv => 
    (conv.title && conv.title.toLowerCase().includes(searchTerm.toLowerCase())) || 
    (conv.preview && conv.preview.toLowerCase().includes(searchTerm.toLowerCase()))
  ) : [];
  
  console.log('Filtered conversations:', filteredConversations);
  
  // 侧边栏始终显示，不再需要鼠标事件
  // 保留这些函数以避免重构其他代码
  const handleMouseEnter = () => {};
  const handleMouseLeave = () => {};
  
  return (
    <div 
      className="chat-sidebar expanded"
    >
      {/* 移除触发区域，侧边栏始终显示 */}
      
      <div className="sidebar-content">
        {isLoggedIn ? (
          // 已登录用户显示完整侧边栏
          <>
            <div className="sidebar-header">
              <div className="sidebar-actions">
                <button className="search-button">
                  <i className="search-icon"></i>
                  搜索聊天
                </button>
                <button className="new-chat-button" onClick={onCreateNewChat}>
                  <i className="new-chat-icon"></i>
                  创建新聊天
                </button>
              </div>
              <div className="search-container">
                <input
                  type="text"
                  placeholder="搜索聊天记录..."
                  value={searchTerm}
                  onChange={handleSearchChange}
                  className="search-input"
                />
              </div>
            </div>
            
            <div className="conversations-list">
              {filteredConversations.length > 0 ? (
                filteredConversations.map(conv => (
                  <div 
                    key={conv.id || `conv-${Math.random()}`} 
                    className="conversation-item"
                    onClick={() => onSelectConversation(conv.id)}
                  >
                    <div className="conversation-title">{conv.title || '无标题对话'}</div>
                    <div className="conversation-preview">{conv.preview || '无预览内容'}</div>
                    <div className="conversation-time">{new Date(conv.lastUpdated || conv.last_updated || Date.now()).toLocaleDateString()}</div>
                  </div>
                ))
              ) : (
                <div className="no-conversations">
                  {searchTerm ? '没有找到匹配的聊天记录' : '暂无聊天记录'}
                </div>
              )}
            </div>
          </>
        ) : (
          // 未登录用户显示登录提示
          <div className="sidebar-content-wrapper">
            <div className="login-container">
              <div className="login-message">
                <p>请登录以体验完整功能</p>
                <p>登录后可保存聊天记录</p>
                <p>享受更多个性化服务</p>
              </div>
              <Link to="/login" className="login-button">
                立即登录
              </Link>
              <Link to="/signup" className="signup-link">
                没有账号？立即注册
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default ChatSidebar;
