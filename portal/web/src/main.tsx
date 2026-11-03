import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/plus-jakarta-sans/400.css'
import '@fontsource/plus-jakarta-sans/500.css'
import '@fontsource/plus-jakarta-sans/600.css'
import '@fontsource/plus-jakarta-sans/700.css'
import './ds.css'
import './app.css'
import App from './App'
import Acesso from './Acesso'
import { ToastProvider } from './ui'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ToastProvider><Acesso><App /></Acesso></ToastProvider>
  </StrictMode>,
)
