import { Button, TextField, Top } from '@toss/tds-mobile'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchBarcode } from '../api/client'
import type { BarcodeResult } from '../api/types'
import { LoadFailedView } from '../components/ErrorView'
import { ListSkeleton } from '../components/ListSkeleton'
import { RecallCard } from '../components/RecallCard'
import { showScanInterstitial } from '../lib/ads'
import { BARCODE_LENGTH, isValidBarcode, sanitizeBarcode } from '../lib/barcode'
import { logClick, logScreen } from '../lib/analytics'
import { pickPhoto, type PhotoSource } from '../lib/barcodePhoto'

type Result =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'done'; data: BarcodeResult }

type Scan =
  | { status: 'idle' }
  | { status: 'picking' | 'decoding'; source: PhotoSource }
  | { status: 'denied' }
  | { status: 'failed' }

const SCAN_MESSAGE = {
  denied: '권한이 없어 사진을 쓸 수 없어요. 번호를 직접 입력해 주세요.',
  failed: '바코드를 읽지 못했어요. 밝은 곳에서 바코드가 화면을 채우게 다시 찍거나 번호를 직접 입력해 주세요.',
} as const

export function BarcodePage() {
  const navigate = useNavigate()
  const [barcode, setBarcode] = useState('')
  const [result, setResult] = useState<Result>({ status: 'idle' })
  const [scan, setScan] = useState<Scan>({ status: 'idle' })
  const scanBusy = scan.status === 'picking' || scan.status === 'decoding'
  const ctrlRef = useRef<AbortController | null>(null)

  useEffect(() => {
    logScreen('barcode_screen')
    return () => ctrlRef.current?.abort()
  }, [])

  const valid = isValidBarcode(barcode)

  async function check(value = barcode) {
    if (!isValidBarcode(value)) return
    ctrlRef.current?.abort()
    const ctrl = (ctrlRef.current = new AbortController())
    setResult({ status: 'loading' })
    try {
      const data = await fetchBarcode(value, ctrl.signal)
      if (ctrl.signal.aborted) return
      logClick('barcode_check_click', { found: data.found })
      setResult({ status: 'done', data })
    } catch {
      if (!ctrl.signal.aborted) setResult({ status: 'error' })
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    if (result.status !== 'loading') check()
  }

  // 사진은 기기 안에서만 판독한다. 이미지는 서버로 보내지 않고, 읽은 번호는 직접 입력과 같은 조회에만 쓴다(로그에 남기지 않음).
  async function scanPhoto(source: PhotoSource) {
    if (scanBusy) return
    logClick('barcode_scan_click', { source })
    setScan({ status: 'picking', source })
    // 사진 스캔에만 전면광고를 붙인다(직접 입력에는 없음). 광고가 닫히거나 건너뛰면 바로 촬영·선택으로 넘어간다.
    // false면 이미 다른 광고가 떠 있는 중복 호출이라 먼저 시작한 쪽에 맡긴다.
    if (!(await showScanInterstitial())) return
    const photo = await pickPhoto(source)
    if (photo.status !== 'ok') {
      setScan({ status: photo.status === 'denied' ? 'denied' : 'idle' })
      return
    }
    // 새 사진을 받았으면 이전 번호·결과를 지운다. 판독에 실패했을 때 남은 번호가 이번 사진 것으로 보이지 않게 한다.
    // 촬영·선택을 취소했을 때는 위에서 이미 돌아가므로 기존 번호가 그대로 남는다.
    ctrlRef.current?.abort()
    setBarcode('')
    setResult({ status: 'idle' })
    setScan({ status: 'decoding', source })
    let code: string | null = null
    try {
      const { decodeEan13FromDataUri } = await import('../lib/barcodeScan')
      code = await decodeEan13FromDataUri(photo.dataUri)
    } catch {
      code = null
    }
    logClick('barcode_scan_result', { success: code !== null })
    if (!code) {
      setScan({ status: 'failed' })
      return
    }
    setScan({ status: 'idle' })
    setBarcode(code)
    check(code)
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

      <form className="barcode-form" onSubmit={submit}>
        <div className="barcode-scan">
          {(['camera', 'album'] as const).map((source) => (
            <Button
              key={source}
              type="button"
              variant="weak"
              size="large"
              display="full"
              loading={scanBusy && scan.source === source}
              disabled={scanBusy}
              onClick={() => scanPhoto(source)}
            >
              {source === 'camera' ? '카메라로 찍기' : '앨범에서 고르기'}
            </Button>
          ))}
        </div>
        {scan.status === 'decoding' && (
          <p className="barcode-scan__message" role="status">
            사진에서 바코드를 찾고 있어요
          </p>
        )}
        {(scan.status === 'denied' || scan.status === 'failed') && (
          <p className="barcode-scan__message" role="alert">
            {SCAN_MESSAGE[scan.status]}
          </p>
        )}
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
            if (!scanBusy) setScan({ status: 'idle' })
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
