import { useState } from 'react'
import ConsolePanel from './consoleComponent'
import WorkerScheduler from './WorkerScheduler'
import './App.css'

function App() {
  const [activeTab, setActiveTab] = useState('webapp'); // 'webapp' or 'workers'
  const [count, setCount] = useState(0)

  const testLog = () => {
    console.log("普通点击日志", { count });
    console.warn("这是一个警告测试");
    console.error("模拟报错信息");
  }

  return (
    <div className="app-container">
      {/* Navigation Tabs */}
      <div className="tab-bar">
        <button
          onClick={() => setActiveTab('webapp')}
          className={`tab-button ${activeTab === 'webapp' ? 'active' : ''}`}
        >
          Web App
        </button>
        <button
          onClick={() => setActiveTab('workers')}
          className={`tab-button ${activeTab === 'workers' ? 'active' : ''}`}
        >
          Backend Worker Scheduling
        </button>
      </div>

      {/* Content Area */}
      <div className="content-area">

        {/* Web App View */}
        {activeTab === 'webapp' && (
          <div className="tab-content">
            <div style={{ padding: '20px' }}>
              <h1>Debug App</h1>
              <p>点击下方按钮测试控制台</p>

              <button
                onClick={() => { setCount(c => c + 1); testLog(); }}
                style={{ padding: '10px 20px', fontSize: '16px', cursor: 'pointer', marginBottom: '20px' }}
              >
                产生日志 (Count: {count})
              </button>

              {/* 挂载 Console 组件 */}
              <ConsolePanel />
            </div>
          </div>
        )}

        {/* Worker Scheduling View */}
        {activeTab === 'workers' && (
          <div className="tab-content no-scroll">
            <WorkerScheduler />
          </div>
        )}

      </div>
    </div>
  )
}

export default App
