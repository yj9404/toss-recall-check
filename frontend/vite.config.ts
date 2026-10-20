import { defineConfig } from 'vitest/config'
import { loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

import aitDevtools from "@apps-in-toss/devtools/unplugin";

// 운영 번들에 백엔드 주소가 빠지면 API가 미니앱 호스트의 상대 경로로 나가 403이 난다.
// 빌드할 때(build, build:live) 주소가 없거나 https가 아니면 번들을 만들지 않는다.
function assertApiBaseUrl(mode: string) {
  const url = loadEnv(mode, '.', 'VITE_').VITE_API_BASE_URL?.trim() ?? ''
  if (!/^https:\/\/[^/\s]+/.test(url)) {
    throw new Error(
      `VITE_API_BASE_URL이 ${url ? `https 주소가 아니에요(${url})` : '비어 있어요'}. ` +
        `.env${mode === 'live' ? '.live' : ''} 등에 VITE_API_BASE_URL=https://<백엔드 주소>를 넣고 다시 빌드해 주세요.`,
    )
  }
}

export default defineConfig(({ command, mode }) => {
  if (command === 'build') assertApiBaseUrl(mode)
  return {
    plugins: [aitDevtools.vite(), react()],
    test: {
      include: ['src/**/*.test.{ts,tsx}'],
    },
  }
})
