import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import SessionTimer from './components/SessionTimer'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    <SessionTimer />
  </StrictMode>,
)
