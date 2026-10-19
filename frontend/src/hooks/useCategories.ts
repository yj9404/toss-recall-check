import { useEffect, useState } from 'react'
import { fetchCategories } from '../api/client'
import type { Category } from '../api/types'
import { getCachedCategories, setCachedCategories } from '../lib/homeCache'

/** 카테고리 탭용. 한 번 받으면 앱이 켜져 있는 동안 재사용하고, 실패하면 탭을 숨긴다(목록은 그대로 동작). */
export function useCategories(): Category[] {
  const [categories, setCategories] = useState<Category[]>(() => getCachedCategories() ?? [])

  useEffect(() => {
    if (getCachedCategories()) return
    const ctrl = new AbortController()
    fetchCategories(ctrl.signal).then(
      (data) => {
        setCachedCategories(data)
        setCategories(data)
      },
      () => {},
    )
    return () => ctrl.abort()
  }, [])

  return categories
}
