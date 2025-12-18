import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import TitleBar from './titleBar.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <TitleBar />
    <App />
  </StrictMode>,
)
