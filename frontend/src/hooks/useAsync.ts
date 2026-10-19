import { useCallback, useEffect, useState } from 'react'

type State<T> = { status: 'loading' } | { status: 'error'; error: unknown } | { status: 'ok'; data: T }

/** 한 번 불러오는 GET용 훅. 입력(key)이 바뀌면 다시 불러오고, `reload`로 재시도한다. */
export function useAsync<T>(load: (signal: AbortSignal) => Promise<T>, key: string) {
  const [state, setState] = useState<State<T>>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const ctrl = new AbortController()
    setState({ status: 'loading' })
    load(ctrl.signal).then(
      (data) => setState({ status: 'ok', data }),
      (error) => {
        if (!ctrl.signal.aborted) setState({ status: 'error', error })
      },
    )
    return () => ctrl.abort()
    // load는 key가 같으면 같은 요청을 뜻한다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt])

  const reload = useCallback(() => setAttempt((n) => n + 1), [])
  return { state, reload }
}
