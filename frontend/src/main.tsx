/**
 * Application entry point.
 *
 * Mounts the root App component into the DOM element with id='root'
 * using React 18's createRoot API with StrictMode enabled for
 * development-time double-render detection.
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
