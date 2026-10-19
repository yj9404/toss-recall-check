import { useLayoutEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { BarcodePage } from './pages/BarcodePage'
import { HomePage } from './pages/HomePage'
import { RecallDetailPage } from './pages/RecallDetailPage'

// 홈의 스크롤은 홈이 스스로 복원한다. 그 밖의 화면은 항상 맨 위에서 시작한다.
function ScrollToTopOutsideHome() {
  const { pathname } = useLocation()
  useLayoutEffect(() => {
    if (pathname !== '/') window.scrollTo(0, 0)
  }, [pathname])
  return null
}

export default function App() {
  return (
    <>
      <ScrollToTopOutsideHome />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/recall/:id" element={<RecallDetailPage />} />
        <Route path="/barcode" element={<BarcodePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  )
}
