import { Button, TextField, Top } from '@toss/tds-mobile'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchBarcode } from '../api/client'
import type { BarcodeResult } from '../api/types'
import { LoadFailedView } from '../components/ErrorView'
import { ListSkeleton } from '../components/ListSkeleton'
import { RecallCard } from '../components/RecallCard'
import { BARCODE_LENGTH, isValidBarcode, sanitizeBarcode } from '../lib/barcode'
import { logClick, logScreen } from '../lib/analytics'

type Result =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'done'; data: BarcodeResult }

export function BarcodePage() {
  const navigate = useNavigate()
  const [barcode, setBarcode] = useState('')
  const [result, setResult] = useState<Result>({ status: 'idle' })
  const ctrlRef = useRef<AbortController | null>(null)

  useEffect(() => {
    logScreen('barcode_screen')
    return () => ctrlRef.current?.abort()
  }, [])

  const valid = isValidBarcode(barcode)

  async function check(e?: FormEvent) {
    e?.preventDefault()
    if (!valid || result.status === 'loading') return
    ctrlRef.current?.abort()
    const ctrl = (ctrlRef.current = new AbortController())
    setResult({ status: 'loading' })
    try {
      const data = await fetchBarcode(barcode, ctrl.signal)
      if (ctrl.signal.aborted) return
      logClick('barcode_check_click', { found: data.found })
      setResult({ status: 'done', data })
    } catch {
      if (!ctrl.signal.aborted) setResult({ status: 'error' })
    }
  }

  return (
    <main className="page">
      <Top
        title={<Top.TitleParagraph size={22}>바코드 번호로 확인해요</Top.TitleParagraph>}
        subtitleBottom={
          <Top.SubtitleParagraph size={15}>
            제품 뒷면 바코드 아래의 숫자 {BARCODE_LENGTH}자리를 입력해 주세요.
          </Top.SubtitleParagraph>
        }
      />

      <form className="barcode-form" onSubmit={check}>
        <TextField
          variant="box"
          label="바코드 번호"
          placeholder="13자리 숫자를 입력해요"
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete="off"
          value={barcode}
          onChange={(e) => {
            setBarcode(sanitizeBarcode(e.target.value))
            setResult({ status: 'idle' })
          }}
          help={
            valid ? undefined : `${BARCODE_LENGTH}자리 숫자를 입력해 주세요. (${barcode.length}/${BARCODE_LENGTH})`
          }
        />
        <Button type="submit" display="full" size="large" disabled={!valid} loading={result.status === 'loading'}>
          확인하기
        </Button>
      </form>

      {result.status === 'loading' && <ListSkeleton />}
      {result.status === 'error' && <LoadFailedView onRetry={() => check()} />}
      {result.status === 'done' &&
        (result.data.found ? (
          <section className="barcode-result">
            <strong>이 제품이 회수·판매중지 목록에 있어요</strong>
            <ul className="recall-list">
              {result.data.items.map((item) => (
                <li key={item.id}>
                  <RecallCard item={item} onClick={() => navigate(`/recall/${encodeURIComponent(item.id)}`)} />
                </li>
              ))}
            </ul>
          </section>
        ) : (
          <section className="barcode-result">
            <strong>회수·판매중지 목록에서 찾지 못했어요</strong>
            <p>목록에 없다고 안전하다는 뜻은 아니에요. 제품 포장과 출처 기관에서 한 번 더 확인해 주세요.</p>
          </section>
        ))}
    </main>
  )
}
