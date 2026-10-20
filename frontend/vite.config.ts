import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

import aitDevtools from "@apps-in-toss/devtools/unplugin";

export default defineConfig({
  plugins: [aitDevtools.vite(), react()],
  test: {
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
