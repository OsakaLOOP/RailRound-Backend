import { useState } from 'react'
import ConsolePanel from './consoleComponent' // 确保路径名字对

function App() {
  const [count, setCount] = useState(0)

  const testLog = () => {
    console.log("普通点击日志", { count });
    console.warn("这是一个警告测试");
    console.error("模拟报错信息");
  }

  return (
    <div style={{ width: '100vw', height: '100vh', backgroundColor: '#333', color: 'white', padding: '20px' }}>
      <h1>Debug App</h1>
      <p>点击下方按钮测试控制台</p>
      
      <button 
        onClick={() => { setCount(c => c + 1); testLog(); }}
        style={{ padding: '10px 20px', fontSize: '16px', cursor: 'pointer' }}
      >
        产生日志 (Count: {count})
      </button>

      {/* 挂载 Console 组件 */}
      <ConsolePanel />
    </div>
  )
}

export default App