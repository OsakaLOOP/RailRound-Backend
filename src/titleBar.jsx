import React, { useState, useEffect, useRef } from 'react';

const TitleBar = () => {
  const [isHovered, setIsHovered] = useState(false);
  // Initialize contextMenu state
  const [contextMenu, setContextMenu] = useState({ visible: false, x: 0, y: 0 });
  // Initialize menuRef
  const menuRef = useRef(null);

  // 调用后端 API 的通用函数
  const callWindowOp = (method) => {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api[method]().catch(() => {});
      console.log(`[Dev] Window action: ${method}`);
    } else {
      console.log(`[Dev] Window action held - pywebview inactivated: ${method}`);
    }
    // Close context menu after action
    setContextMenu({ ...contextMenu, visible: false });
  };

  const handleDoubleClick = () => {
    callWindowOp('toggle_maximize');
  };

  const handleContextMenu = (e) => {
    e.preventDefault(); // 阻止浏览器默认右键菜单
    setContextMenu({
      visible: true,
      x: e.clientX,
      y: e.clientY
    });
  };

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setContextMenu({ ...contextMenu, visible: false });
      }
    };
    window.addEventListener('click', handleClickOutside);
    return () => window.removeEventListener('click', handleClickOutside);
  }, [contextMenu]);

  // 按钮组件 (带 Hover 效果)
  const WinButton = ({ color, hoverColor, icon, onClick }) => {
    const [btnHover, setBtnHover] = useState(false);
    return (
      <button
        onClick={onClick}
        onMouseEnter={() => setBtnHover(true)}
        onMouseLeave={() => setBtnHover(false)}
        style={{
          width: '12px',
          height: '12px',
          borderRadius: '50%',
          border: '1px solid rgba(0,0,0,0.1)',
          backgroundColor: isHovered ? color : '#cbd5e1', // 没 hover 标题栏时显示灰色(可选)，或者一直显示彩色
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'default',
          outline: 'none',
          padding: 0,
          position: 'relative',
          filter: btnHover ? 'brightness(0.9)' : 'none'
        }}
      >
        <span style={{ 
          opacity: isHovered ? 1 : 0,
          transform: isHovered ? 'scale(1) translate(-50%, -50%)' : 'scale(0.5) translate(-100%, -100%)',
          
          color: '#4a4a4a',
          fontSize: '7px', 
          fontWeight: '900',
          position: 'absolute',
          top: '50%',
          left: '50%',
          // 图标本身的过渡动画
          transition: 'opacity 0.2s ease, transform 0.2s ease', 
          transformOrigin: 'center center'
        }}>
          {icon}
        </span>
      </button>
    );
  };

  const styles = {
    container: {
      height: '38px',
      // 背景增加一点半透明和模糊，实现毛玻璃效果 (配合 CSS backdrop-filter)
      background: 'rgba(243, 243, 243, 0.95)', 
      backdropFilter: 'blur(10px)', 
      borderBottom: '1px solid #d1d1d1',
      display: 'flex',
      alignItems: 'center',
      padding: '0 12px',
      userSelect: 'none',
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      zIndex: 9998,
      fontFamily: '-apple-system, BlinkMacSystemFont, sans-serif',
      transition: 'background 0.3s ease'
    },
    dragRegion: {
      flex: 1,
      height: '100%',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      // 这里我们假设你用的是 frameless 窗口，pywebview 会自动识别 class="pywebview-drag-region"
      cursor: 'default',
    },
    controls: {
      display: 'flex',
      gap: '8px',
      zIndex: 20 // 确保按钮在拖拽层之上
    },
    title: {
      fontSize: '13px',
      color: '#4c4c4c',
      fontWeight: 600,
      letterSpacing: '0.5px'
    },
    contextMenu: {
      position: 'fixed',
      top: contextMenu.y,
      left: contextMenu.x,
      background: 'rgba(255, 255, 255, 0.95)',
      backdropFilter: 'blur(20px)',
      border: '1px solid #d1d1d1',
      borderRadius: '6px',
      boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
      padding: '4px',
      zIndex: 9999,
      minWidth: '160px',
      display: 'flex',
      flexDirection: 'column',
      gap: '2px'
    },
    menuItem: {
      padding: '6px 12px',
      fontSize: '13px',
      color: '#333',
      borderRadius: '4px',
      cursor: 'pointer',
      display: 'flex',
      justifyContent: 'space-between',
      border: 'none',
      background: 'transparent',
      textAlign: 'left'
    },
    separator: {
      height: '1px',
      background: '#e5e5e5',
      margin: '2px 6px'
    }
  };

  const MenuItem = ({ label, shortcut, onClick, danger }) => (
    <button 
      onClick={onClick}
      style={styles.menuItem}
      // Fixed duplicate onMouseEnter
      onMouseEnter={(e) => {
         e.currentTarget.style.background = danger ? '#ff5f57' : '#3b82f6';
         e.currentTarget.style.color = 'white';
      }}
      onMouseLeave={(e) => {
         e.currentTarget.style.background = 'transparent';
         e.currentTarget.style.color = '#333';
      }}
    >
      <span>{label}</span>
      {shortcut && <span style={{ opacity: 0.5 }}>{shortcut}</span>}
    </button>
  );

  return (
    <> {/* Using Fragment to wrap everything */}
    <div 
      style={styles.container} 
      onMouseEnter={() => setIsHovered(true)} 
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* 1. 左侧：红绿灯控制区 */}
      <div style={styles.controls}>
        {/* 关闭 (Red) */}
        <WinButton 
          color="#ff5f57" 
          icon={<svg width="8" height="8" viewBox="0 0 10 10"><path d="M1,1 L9,9 M9,1 L1,9" stroke="#5c0002" strokeWidth="1.5" /></svg>} 
          onClick={() => callWindowOp('close')} 
        />
        {/* 最小化 (Yellow) */}
        <WinButton 
          color="#febc2e" 
          icon={<svg width="8" height="8" viewBox="0 0 10 10"><path d="M1,5 L9,5" stroke="#9a5700" strokeWidth="1.5" /></svg>} 
          onClick={() => callWindowOp('minimize')} 
        />
        {/* 最大化 (Green) */}
        <WinButton 
          color="#28c840" 
          icon={<svg width="6" height="6" viewBox="0 0 10 10"><path d="M1,5 L9,5 M5,1 L5,9" stroke="#006500" strokeWidth="1.5" /></svg>} 
          onClick={() => callWindowOp('toggle_maximize')} 
        />
      </div>

      <div className="pywebview-drag-region"
           style={styles.dragRegion}
           onDoubleClick={handleDoubleClick}
           onContextMenu={handleContextMenu}>
        <span style={styles.title}>Railround Python Backend</span>
      </div>

      {/* 3. 右侧：占位 (保持标题居中) */}
      <div style={{ width: '60px' }}></div>
    </div>
    
    {/* 右键菜单 Portal - Now outside the main titlebar div but inside the fragment */}
    {contextMenu.visible && (
        <div ref={menuRef} style={styles.contextMenu}>
            <div style={{ padding: '4px 12px', fontSize: '10px', fontWeight: 'bold', color: '#999', textTransform: 'uppercase' }}>Window Actions</div>
            <MenuItem label="Minimize" onClick={() => callWindowOp('minimize')} />
            <MenuItem label="Zoom" onClick={() => callWindowOp('toggle_maximize')} />
            <div style={styles.separator} />
            <MenuItem label="Reload App" shortcut="Cmd+R" onClick={() => window.location.reload()} />
            <div style={styles.separator} />
            <MenuItem label="Close" danger onClick={() => callWindowOp('close')} />
        </div>
    )}
    </>
  );
};

export default TitleBar;