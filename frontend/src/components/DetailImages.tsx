import { useState } from 'react'

/**
 * 첫 장을 너비 100%로 보여주고, 2장 이상이면 가로로 넘겨 본다.
 * 원본 서버가 이미지를 못 주면 그 이미지를 빼고, 모두 실패하면 영역째 그리지 않는다.
 */
export function DetailImages({ srcs, alt }: { srcs: string[]; alt: string }) {
  const [failed, setFailed] = useState<ReadonlySet<string>>(() => new Set())
  const visible = [...new Set(srcs)].filter((src) => !failed.has(src))
  if (visible.length === 0) return null

  return (
    <div className="detail-images">
      {visible.map((src) => (
        <img
          key={src}
          src={src}
          alt={alt}
          loading="lazy"
          onError={() => setFailed((prev) => new Set(prev).add(src))}
        />
      ))}
    </div>
  )
}
