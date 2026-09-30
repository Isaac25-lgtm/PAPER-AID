import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router/dom'
import { Providers } from './app/providers'
import { router } from './app/router'
import './styles/globals.css'
import { reloadForUpdate } from './lib/stale-build'

// A page file from the previous version failed to load after a deploy: reload to the new version.
window.addEventListener('vite:preloadError', (event) => {
  if (reloadForUpdate()) event.preventDefault()
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Providers>
      <RouterProvider router={router} />
    </Providers>
  </StrictMode>,
)
