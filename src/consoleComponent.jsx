import React, { useState, useEffect, useRef } from 'react';
import { Terminal, Trash2, ChevronDown, Activity, Cpu, HardDrive, Wifi, Zap } from 'lucide-react';

const TimeAgo = ({ seconds }) => {
  if (seconds < 0) return <span className="text-gray-400">Never</span>;
  if (seconds < 60) return <span className="text-green-600">Just now</span>;
  if (seconds < 3600) return <span className="text-green-600">{Math.floor(seconds / 60)}m ago</span>;
  if (seconds < 86400) return <span className="text-gray-600">{Math.floor(seconds / 3600)}h ago</span>;
  return <span className="text-red-500">{Math.floor(seconds / 86400)}d ago</span>;
};

const StatusDot = ({ indicator }) => {
  const colors = {
    green: 'bg-green-500',
    yellow: 'bg-yellow-400 animate-pulse',
    red: 'bg-red-500',
    gray: 'bg-gray-300'
  };
  return <div className={`w-3 h-3 rounded-full ${colors[indicator] || colors.gray} mr-2`} />;
};

const usePerformanceData = () => {
  const call = async (method, ...args) => {
    // 检查 pywebview readiness 并执行调用
    if (window.pywebview && window.pywebview.api && window.pywebview.api[method]) {
      return await window.pywebview.api[method](...args);
    } 
    // 调试模式下的 Mock 数据生成
    else if (method === 'retrive_performance_data') {
        return [0,0,0,0,0,0];
    }
    console.error(`Backend method "${method}" not available.`); 
    return [];
  };
  return { call };
};

const MiniGraph = ({ label, value, history, color, icon: Icon, fixedMax = null }) => {
  const maxVal = fixedMax !== null 
    ? fixedMax 
    : Math.max(...history, 10);
  
  const normalize = (v) => {
    const p = (v / maxVal) * 100;
    return Math.min(Math.max(p, 0), 100); 
  };

  const colors = {
    'text-blue-400': '#60a5fa',
    'text-purple-400': '#c084fc',
    'text-emerald-400': '#34d399',
    'text-orange-400': '#fb923c',
  };
  const themeColor = colors[color] || '#cbd5e1';

  return (
    <div className="bg-slate-50 border border-[#3e3e42] flex flex-col h-full overflow-hidden relative group">
      {/* 头部信息 */}
      <div className="absolute top-1 left-1.5 z-10 flex flex-col">
        <span className="text-[10px] text-gray-400 font-bold uppercase tracking-wider flex items-center gap-1">
          <Icon size={10} /> {label}
        </span>
        <span className={`text-sm font-mono font-bold leading-tight ${color}`}>{' '}{value}</span>
      </div>
      
      {/* SVG 曲线 */}
      <div className="absolute bottom-0 left-0 right-0 top-0 pt-4 opacity-80">
        <svg className="w-full h-full" preserveAspectRatio="none">

          <polygon 
            fill={themeColor} 
            fillOpacity="0.15" 
            points={`0,100 ${history.map((v, i) => `${i * (100 / (history.length - 1))},${100 - normalize(v)}`).join(' ')} 100,100`} 
          />
          <polyline 
            fill="none" 
            stroke={themeColor} 
            strokeWidth="1.5" 
            vectorEffect="non-scaling-stroke"
            points={history.map((v, i) => `${i * (100 / (history.length - 1))},${100 - normalize(v)}`).join(' ')} 
          />
        </svg>
      </div>
      {/* 装饰网格线 */}
      <div className="absolute inset-0 grid grid-cols-4 grid-rows-2 opacity-5 pointer-events-none">
         {[...Array(8)].map((_,i) => <div key={i} className="border-r border-b border-white"></div>)}
      </div>
    </div>
  );
};

const ConsolePanel = () => {
  const { call } = usePerformanceData();
  const [isOpen, setIsOpen] = useState(false);
  const [logs, setLogs] = useState([]);
  const bottomRef = useRef(null);
  const isSendingRef = useRef(false);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [dashboard, setDashboard] = useState({});
  const [api, setApi] = useState(null);

  const POINTS = 10;

  useEffect(() => {
    if (window.pywebview && window.pywebview.api) {
      setApi(window.pywebview.api);
    }
  }, []);

  useEffect(() => {
    if (!api) return;
    const poll = async () => {
      try {
        const data = await api.get_dashboard_data();
        setDashboard(data);
      } catch(e) {}
    };
    poll();
    const timer = setInterval(poll, 500); // 0.5秒刷新
    return () => clearInterval(timer);
  }, [api]);

  const formatUnit = (val, baseUnit) => {
    if (val >= 1024) {
      const nextUnit = baseUnit === 'KB/s' ? 'MB/s' : 'GB/s';
      return `${(val / 1024).toFixed(1)} ${nextUnit}`;
    }
    return `${val.toFixed(0)} ${baseUnit}`;
  };

  const [monitor, setMonitor] = useState({
    cpu: { val: 0, hist: Array(POINTS).fill(0) },
    ram: { val: 0, hist: Array(POINTS).fill(0) },
    diskR: { val: 0, hist: Array(POINTS).fill(0) }, 
    diskW: { val: 0, hist: Array(POINTS).fill(0) }, 
    netD: { val: 0, hist: Array(POINTS).fill(0) },  
    netU: { val: 0, hist: Array(POINTS).fill(0) },  
  });

  useEffect(() => {//log 循环
    const originalLog = console.log;
    const originalWarn = console.warn;
    const originalError = console.error;

    const sendToPython = (level, args) => {
      // 死锁保护
      if (isSendingRef.current) return;

      if (window.pywebview && window.pywebview.api) {
        try {
          isSendingRef.current = true;
          const message = args.map(arg => 
            typeof arg === 'object' ? JSON.stringify(arg) : String(arg)
          ).join(' ');
          
          window.pywebview.api.sendLog(level, message).catch(() => {});
        } catch (e) {
        } finally {
          isSendingRef.current = false;
        }
      }
    };

    const pushLog = (level, args, source = 'UI') => {
      const message = args.map(arg => {
        try {
          return typeof arg === 'object' ? JSON.stringify(arg) : String(arg);
        } catch (e) {
          return '[Object Circular]';
        }
      }).join(' ');

      setLogs(prev => {
        const newLogs = [...prev, { 
          id: Date.now() + Math.random(), 
          level, 
          message, 
          source,
          time: new Date().toLocaleTimeString('en-US', { hour12: false }) 
        }];
        return newLogs.slice(-200);
      });
    };

    // 劫持逻辑
    console.log = (...args) => { originalLog(...args); pushLog('info', args, 'UI'); sendToPython('info', args); };
    console.warn = (...args) => { originalWarn(...args); pushLog('warn', args, 'UI'); sendToPython('warn', args); };
    console.error = (...args) => { originalError(...args); pushLog('error', args, 'UI'); sendToPython('error', args); };

    window.addLog = (level, message, source = 'PYTHON') => pushLog(level, [message], source);

    return () => {
      console.log = originalLog;
      console.warn = originalWarn;
      console.error = originalError;
      delete window.addLog;
    };
  }, []);

  useEffect(() => {//轮询性能数据
    if (!isOpen) return; // 关闭时不轮询
    const fetchData = async () => {
      let cpu = 0, ram = 0, diskR = 0, diskW = 0, netD = 0, netU = 0;

      if (window.pywebview) {
        try {
          const data = await call('retrive_performance_data');
          if (Array.isArray(data) && data.length >= 6) {
             [cpu, ram, diskR, diskW, netD, netU] = data;
          }
        } catch (e) {
          console.error("Monitor Error:", e);
        }
      }
      setMonitor(prev => ({
        cpu: { val: cpu, hist: [...prev.cpu.hist.slice(1), cpu] },
        ram: { val: ram, hist: [...prev.ram.hist.slice(1), ram] },
        diskR: { val: diskR, hist: [...prev.diskR.hist.slice(1), diskR] },
        diskW: { val: diskW, hist: [...prev.diskW.hist.slice(1), diskW] },
        netD: { val: netD, hist: [...prev.netD.hist.slice(1), netD] },
        netU: { val: netU, hist: [...prev.netU.hist.slice(1), netU] },
      }));
    };
    const timer = setInterval(fetchData, 1000);
    return () => clearInterval(timer);
  }, [isOpen, call]);
    
  // 自动滚动
  useEffect(() => {
    if (isOpen && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, isOpen]);

  // --- 样式定义 (改为纯内联样式，不依赖 Tailwind) ---
  const styles = {
    floatingBtn: {
      position: 'fixed', bottom: '20px', right: '20px',
      backgroundColor: '#0f172a', color: 'white', padding: '12px',
      borderRadius: '50%', border: '1px solid #334155', cursor: 'pointer',
      boxShadow: '0 4px 6px rgba(0,0,0,0.1)', zIndex: 9999,
      display: 'flex', alignItems: 'center', justifyContent: 'center'
    },
    panel: {
      position: 'fixed', bottom: 0, left: 0, right: 0, height: '340px',
      backgroundColor: '#1e1e1e', borderTop: '1px solid #333', zIndex: 9999,
      display: 'flex', flexDirection: 'column', fontFamily: 'monospace', fontSize: '12px',
      boxShadow: '0 -4px 6px rgba(0,0,0,0.5)'
    },
    header: {
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '8px 16px', backgroundColor: '#2d2d2d', borderBottom: '1px solid #000', color: '#cbd5e1'
    },
    logArea: {
      flex: 1, overflowY: 'auto', padding: '8px', display: 'flex', flexDirection: 'column', gap: '4px'
    },
    logRow: (level) => ({
      display: 'flex', gap: '8px', padding: '4px 8px', borderRadius: '4px',
      backgroundColor: level === 'error' ? 'rgba(248, 113, 113, 0.1)' : 
                       level === 'warn' ? 'rgba(250, 204, 21, 0.1)' : 'transparent',
      color: level === 'error' ? '#f87171' : 
             level === 'warn' ? '#facc15' : '#e2e8f0',
      borderLeft: level === 'error' ? '2px solid #f87171' : 'none',
      alignItems: 'flex-start' // 顶部对齐，防止多行日志导致时间戳错位
    }),
    badge: (source) => ({
      padding: '2px 4px', borderRadius: '4px', fontSize: '10px', fontWeight: 'bold',
      backgroundColor: source === 'PYTHON' ? 'rgba(59, 130, 246, 0.2)' : 'rgba(168, 85, 247, 0.2)', // Blue vs Purple
      color: source === 'PYTHON' ? '#60a5fa' : '#c084fc',
      border: `1px solid ${source === 'PYTHON' ? 'rgba(59, 130, 246, 0.3)' : 'rgba(168, 85, 247, 0.3)'}`,
      minWidth: '24px', textAlign: 'center'
    })
  };

  const getSourceBadge = (source) => (
    <span style={styles.badge(source)}>{source === 'PYTHON' ? 'PY' : 'UI'}</span>
  );

  if (!isOpen) {
    return (
      <button style={styles.floatingBtn} onClick={() => setIsOpen(true)}>
        <Terminal size={24} />
      </button>
    );
  }

// ... existing return ...
  return (
    <div style={styles.panel}>
      
      {/* 1. Header 移到最上层 */}
      <div style={styles.header}>
        <div style={{display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'bold'}}>
          <Terminal size={16} />
          <span>DEBUG CONSOLE</span>
          <span style={{background: '#475569', padding: '2px 6px', borderRadius: '4px', fontSize: '10px'}}>{logs.length}</span>
        </div>
        <div style={{display: 'flex', gap: '12px'}}>
          <button onClick={() => setLogs([])} style={{background:'none', border:'none', color:'inherit', cursor:'pointer'}} title="Clear"><Trash2 size={16} /></button>
          <button onClick={() => setIsOpen(false)} style={{background:'none', border:'none', color:'inherit', cursor:'pointer'}} title="Minimize"><ChevronDown size={16} /></button>
        </div>
      </div>

      {/* 2. 新增 flex-row 容器包裹下方内容 */}
      <div style={{flex: 1, display: 'flex', minHeight: 0}}> 
        
        {/* 日志区域 (移除原来的 Header 和外层 div，只保留 LogArea) */}
        <div style={{
            flex: 1, 
            display: 'flex', 
            flexDirection: 'column', 
            minWidth: 0, 
            borderRight: '1px solid #333'
        }}>
          <div style={styles.logArea}>
             {/* ... logs map logic 保持不变 ... */}
             {logs.length === 0 && <div style={{color: '#64748b', fontStyle: 'italic', padding: '8px'}}>System Ready. Waiting for logs...</div>}
             {logs.map((log) => (
               <div key={log.id} style={styles.logRow(log.level)}>
                 <span style={{color: '#64748b', flexShrink: 0}}>[{log.time}]</span>
                 {getSourceBadge(log.source)}
                 <span style={{fontWeight: 'bold', textTransform: 'uppercase', flexShrink: 0, minWidth: '40px'}}>{log.level}</span>
                 <span style={{wordBreak: 'break-all', whiteSpace: 'pre-wrap', flex: 1}}>{log.message}</span>
               </div>
             ))}
             <div ref={bottomRef} /> 
          </div>
        </div>

        {/* 监控图表 (更新数据绑定和单位格式化) */}
        <div style={{
            width: 'fit-content', padding: '4px', backgroundColor: '#1e1e1e',
            display: 'flex', flexDirection: 'column', gap: '8px'
        }}>
            <div style={{
                display: 'grid', 
                gridTemplateColumns: 'repeat(3, 130px)', 
                gridTemplateRows: 'repeat(2, 1fr)',
                gap: '8px', height: '100%'
            }}>
              <MiniGraph fixedMax={100} label="CPU" value={`${monitor.cpu.val.toFixed(1)}%`} history={monitor.cpu.hist} color="text-blue-400" icon={Cpu} />
              <MiniGraph label="Disk (R)" value={formatUnit(monitor.diskR.val, 'MB/s')} history={monitor.diskR.hist} color="text-emerald-400" icon={HardDrive} />
              <MiniGraph label="Net (↓)" value={formatUnit(monitor.netD.val, 'KB/s')} history={monitor.netD.hist} color="text-orange-400" icon={Wifi} />
              
              <MiniGraph fixedMax={100} label="RAM" value={`${monitor.ram.val.toFixed(1)}%`} history={monitor.ram.hist} color="text-purple-400" icon={Activity} />
              <MiniGraph label="Disk (W)" value={formatUnit(monitor.diskW.val, 'MB/s')} history={monitor.diskW.hist} color="text-emerald-400" icon={HardDrive} />
              <MiniGraph label="Net (↑)" value={formatUnit(monitor.netU.val, 'KB/s')} history={monitor.netU.hist} color="text-orange-400" icon={Wifi} />
            </div>
        </div>

      </div> 
    </div>
  );
};

export default ConsolePanel;