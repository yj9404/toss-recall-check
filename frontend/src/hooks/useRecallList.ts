import { useCallback, useEffect, useReducer, useRef } from 'react'
import { fetchRecalls } from '../api/client'
import type { RecallSummary } from '../api/types'
import { appendPage } from '../lib/pagination'

interface State {
  items: RecallSummary[]
  total: number
  status: 'loading' | 'loadingMore' | 'idle' | 'error'
  /** 처음 불러오다 실패했는지 (true면 전체 오류 화면, false면 더 보기 실패) */
  failedFirst: boolean
}

type Action =
  | { type: 'reset' }
  | { type: 'more' }
  | { type: 'loaded'; items: RecallSummary[]; total: number; first: boolean }
  | { type: 'failed'; first: boolean }

const initial: State = { items: [], total: 0, status: 'loading', failedFirst: false }

export interface RestoredList {
  items: RecallSummary[]
  total: number
}

const init = (restored?: RestoredList): State =>
  restored ? { items: restored.items, total: restored.total, status: 'idle', failedFirst: false } : initial

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'reset':
      return initial
    case 'more':
      return { ...state, status: 'loadingMore' }
    case 'loaded':
      return {
        items: action.first ? action.items : appendPage(state.items, action.items),
        total: action.total,
        status: 'idle',
        failedFirst: false,
      }
    case 'failed':
      return { ...state, status: 'error', failedFirst: action.first }
  }
}

/**
 * 카테고리·검색어가 바뀌면 처음부터 다시 불러오고, loadMore로 20건씩 이어 붙인다.
 * `restored`가 있으면 그 목록으로 시작하고, 조건이 바뀌기 전까지는 다시 불러오지 않는다.
 */
export function useRecallList(
  category: string,
  q: string,
  onFirstLoaded?: (total: number) => void,
  restored?: RestoredList,
) {
  const [state, dispatch] = useReducer(reducer, restored, init)
  const key = `${category}
${q}`
  const restoredKey = useRef<string | null>(restored ? key : null)
  // 조건이 바뀌면 진행 중인 요청(더 보기 포함)을 모두 버린다
  const ctrlRef = useRef(new AbortController())

  const fetchPage = useCallback(
    (offset: number) => {
      const { signal } = ctrlRef.current
      const first = offset === 0
      fetchRecalls({ category, q, offset }, signal).then(
        (page) => {
          if (signal.aborted) return
          dispatch({ type: 'loaded', items: page.items, total: page.total, first })
          if (first) onFirstLoaded?.(page.total)
        },
        () => {
          if (!signal.aborted) dispatch({ type: 'failed', first })
        },
      )
    },
    // onFirstLoaded는 호출 시점의 최신 값이면 충분하다
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [category, q],
  )

  const loadFirst = useCallback(() => {
    ctrlRef.current.abort()
    ctrlRef.current = new AbortController()
    dispatch({ type: 'reset' })
    fetchPage(0)
  }, [fetchPage])

  useEffect(() => {
    if (restoredKey.current === key) return
    restoredKey.current = null
    loadFirst()
    return () => ctrlRef.current.abort()
  }, [key, loadFirst])

  const loadMore = useCallback(() => {
    if (state.status === 'loadingMore') return
    dispatch({ type: 'more' })
    fetchPage(state.items.length)
  }, [fetchPage, state.items.length, state.status])

  const retry = state.failedFirst ? loadFirst : loadMore

  // reload: 같은 조건으로 처음부터 다시 불러온다 (같은 검색어로 다시 검색할 때)
  return { ...state, hasMore: state.items.length < state.total, loadMore, retry, reload: loadFirst }
}
