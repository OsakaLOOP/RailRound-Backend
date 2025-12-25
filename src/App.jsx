import { useState } from 'react'
import ConsolePanel from './consoleComponent'
import WorkerScheduler from './WorkerScheduler'
import './App.css'

function App() {
  const [activeTab, setActiveTab] = useState('webapp'); // 'webapp' or 'workers'
  const [count, setCount] = useState(0)

  const testLog = () => {
    console.log("Normal Click Log", { count });
    console.warn("This is a warning test");
    console.error("Simulated error message");
  }

  return (
    <div className="app-container">
      {/* Navigation Tabs */}
      <div className="tab-bar">
        <button
          onClick={() => setActiveTab('webapp')}
          className={`tab-button ${activeTab === 'webapp' ? 'active' : ''}`}
        >
          网页端展示
        </button>
        <button
          onClick={() => setActiveTab('workers')}
          className={`tab-button ${activeTab === 'workers' ? 'active' : ''}`}
        >
          后端 Worker 管理
        </button>
      </div>

      {/* Content Area */}
      <div className="content-area">

        {/* Web App View */}
        {activeTab === 'webapp' && (
          <div className="tab-content">
            {/*
            <div style={{ padding: '20px' }}>
              <h1>Debug App</h1>
              <p>Click the button below to test the console</p>

              <button
                onClick={() => { setCount(c => c + 1); testLog(); }}
                style={{ padding: '10px 20px', fontSize: '16px', cursor: 'pointer', marginBottom: '20px' }}
              >
                Generate Log (Count: {count})
              </button>
            </div>
            */}
            <div style={{ width: '100%', height: '100%' }}>
              <iframe
                src="https://railround.s3xyseia.xyz/"
                style={{ width: '100%', height: '100%', border: 'none' }}
                title="RailRound App"
              />
            </div>
          </div>
        )}

        {/* Worker Scheduling View */}
        {activeTab === 'workers' && (
          <div className="tab-content no-scroll">
            <WorkerScheduler />
          </div>
        )}

        {/* Global Console Panel - Always visible */}
        <ConsolePanel />

      </div>
    </div>
  )
}

export default App
