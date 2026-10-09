import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// La API del motor corre aparte: cd motor && uv run uvicorn motor.api:app --reload
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
