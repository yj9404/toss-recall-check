// @vitest-environment jsdom
import { ThemeProvider } from '@toss/tds-mobile'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BarcodePage } from './BarcodePage'

const fetchBarcode = vi.fn()
vi.mock('../api/client', () => ({
  fetchBarcode: (...args: unknown[]) => fetchBarcode(...args),
  imageUrl: () => null,
}))

const { click, openCamera, getPhotos } = vi.hoisted(() => {
  const withPermission = () => Object.assign(vi.fn(), { getPermission: vi.fn(), openPermissionDialog: vi.fn() })
  return { click: vi.fn(), openCamera: withPermission(), getPhotos: withPermission() }
})
vi.mock('@apps-in-toss/web-framework', () => {
  class PermissionError extends Error {}
  return {
    Analytics: { screen: () => {}, click: (params: unknown) => click(params) },
    Device: { openCamera, getPhotos },
    PermissionError,
  }
})

// 판독 모듈은 동적 import로만 불러와야 한다. 팩토리가 처음 실행되는 시점으로 확인한다.
// 모듈은 한 번 불리면 캐시되고, clearAllMocks에 지워지지 않게 mock이 아닌 숫자로 센다.
const { decode, scanModule } = vi.hoisted(() => ({ decode: vi.fn(), scanModule: { loads: 0 } }))
vi.mock('../lib/barcodeScan', () => {
  scanModule.loads++
  return { decodeEan13FromDataUri: (...args: unknown[]) => decode(...args) }
})

const CODE = '8801234567893'
const DENIED = '권한이 없어 사진을 쓸 수 없어요. 번호를 직접 입력해 주세요.'
const FAILED = '바코드를 읽지 못했어요. 밝은 곳에서 바코드가 화면을 채우게 다시 찍거나 번호를 직접 입력해 주세요.'

beforeEach(() => {
  vi.clearAllMocks()
  fetchBarcode.mockResolvedValue({ found: false, items: [] })
  for (const fn of [openCamera, getPhotos]) {
    fn.getPermission.mockResolvedValue('allowed')
    fn.openPermissionDialog.mockResolvedValue('allowed')
  }
  openCamera.mockResolvedValue({ id: '1', dataUri: 'AAAA' })
  getPhotos.mockResolvedValue([{ id: '1', dataUri: 'BBBB' }])
})
afterEach(cleanup)

function renderPage() {
  render(
    <ThemeProvider>
      <MemoryRouter>
        <BarcodePage />
      </MemoryRouter>
    </ThemeProvider>,
  )
  return screen.getByPlaceholderText('13자리 숫자를 입력해요') as HTMLInputElement
}

const logged = () => click.mock.calls.map(([p]) => p as Record<string, unknown>)

describe('바코드 사진 판독', () => {
  // 모듈 캐시 때문에 이 테스트가 파일에서 처음이어야 한다
  it('판독 모듈은 화면 진입이 아니라 사진을 받은 뒤에 불러온다', async () => {
    decode.mockResolvedValue(null)
    renderPage()
    expect(scanModule.loads).toBe(0)
    expect(openCamera.getPermission).not.toHaveBeenCalled()
    expect(getPhotos.getPermission).not.toHaveBeenCalled()
    expect(openCamera.openPermissionDialog).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: '카메라로 찍기' }))
    await waitFor(() => expect(decode).toHaveBeenCalled())
    expect(scanModule.loads).toBe(1)
  })

  it('카메라 판독에 성공하면 번호를 채우고 바로 조회한다', async () => {
    decode.mockResolvedValue(CODE)
    const input = renderPage()
    fireEvent.click(screen.getByRole('button', { name: '카메라로 찍기' }))

    await waitFor(() => expect(fetchBarcode).toHaveBeenCalledWith(CODE, expect.anything()))
    expect(input.value).toBe(CODE)
    expect(openCamera).toHaveBeenCalledWith({ base64: true, maxWidth: 1600 })
    expect(decode).toHaveBeenCalledWith('AAAA')
    expect(await screen.findByText('회수·판매중지 목록에서 찾지 못했어요')).toBeTruthy()

    expect(logged()).toContainEqual({ log_name: 'barcode_scan_click', source: 'camera' })
    expect(logged()).toContainEqual({ log_name: 'barcode_scan_result', success: true })
    // 바코드 번호는 어떤 로그에도 남기지 않는다
    expect(JSON.stringify(logged())).not.toContain(CODE)
  })

  it('앨범은 한 장만 받고, 판독에 실패하면 안내하고 조회하지 않는다', async () => {
    decode.mockResolvedValue(null)
    const input = renderPage()
    fireEvent.click(screen.getByRole('button', { name: '앨범에서 고르기' }))

    expect(await screen.findByText(FAILED)).toBeTruthy()
    expect(getPhotos).toHaveBeenCalledWith({ base64: true, maxCount: 1, maxWidth: 1600 })
    expect(fetchBarcode).not.toHaveBeenCalled()
    expect(input.value).toBe('')
    expect(logged()).toContainEqual({ log_name: 'barcode_scan_click', source: 'album' })
    expect(logged()).toContainEqual({ log_name: 'barcode_scan_result', success: false })
  })

  it('다시 찍어 판독에 실패하면 이전 번호와 결과를 지운다', async () => {
    decode.mockResolvedValueOnce(CODE).mockResolvedValueOnce(null)
    const input = renderPage()
    const camera = screen.getByRole('button', { name: '카메라로 찍기' })
    fireEvent.click(camera)
    expect(await screen.findByText('회수·판매중지 목록에서 찾지 못했어요')).toBeTruthy()
    expect(input.value).toBe(CODE)

    fireEvent.click(camera)
    expect(await screen.findByText(FAILED)).toBeTruthy()
    expect(input.value).toBe('')
    expect(screen.queryByText('회수·판매중지 목록에서 찾지 못했어요')).toBeNull()
    expect(fetchBarcode).toHaveBeenCalledTimes(1)
  })

  it('촬영을 취소하면 입력해 둔 번호는 그대로 둔다', async () => {
    openCamera.mockRejectedValue(new Error('cancelled'))
    const input = renderPage()
    fireEvent.change(input, { target: { value: CODE } })
    fireEvent.click(screen.getByRole('button', { name: '카메라로 찍기' }))
    await waitFor(() => expect(openCamera).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByRole('button', { name: '카메라로 찍기' })).toHaveProperty('disabled', false))
    expect(input.value).toBe(CODE)
  })

  it('판독 모듈을 불러오지 못해도 실패 안내를 보여준다', async () => {
    decode.mockRejectedValue(new Error('image load failed'))
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: '카메라로 찍기' }))
    expect(await screen.findByText(FAILED)).toBeTruthy()
  })

  it('판독하는 동안 로딩을 보여준다', async () => {
    let finish: (v: string | null) => void = () => {}
    decode.mockReturnValue(new Promise((r) => (finish = r)))
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: '카메라로 찍기' }))

    expect(await screen.findByText('사진에서 바코드를 찾고 있어요')).toBeTruthy()
    finish(null)
    expect(await screen.findByText(FAILED)).toBeTruthy()
    expect(screen.queryByText('사진에서 바코드를 찾고 있어요')).toBeNull()
  })

  it('권한을 거부하면 안내만 하고 직접 입력은 그대로 쓸 수 있다', async () => {
    openCamera.getPermission.mockResolvedValue('denied')
    openCamera.openPermissionDialog.mockResolvedValue('denied')
    const input = renderPage()
    fireEvent.click(screen.getByRole('button', { name: '카메라로 찍기' }))

    expect(await screen.findByText(DENIED)).toBeTruthy()
    expect(openCamera.openPermissionDialog).toHaveBeenCalledTimes(1)
    expect(openCamera).not.toHaveBeenCalled()
    expect(decode).not.toHaveBeenCalled()

    fireEvent.change(input, { target: { value: CODE } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(fetchBarcode).toHaveBeenCalledWith(CODE, expect.anything()))
    expect(screen.queryByText(DENIED)).toBeNull()
  })

  it('촬영 중 권한 오류가 나도 권한 안내로 처리한다', async () => {
    const { PermissionError } = await import('@apps-in-toss/web-framework')
    getPhotos.mockRejectedValue(new PermissionError({ methodName: 'fetchAlbumPhotos', message: 'denied' }))
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: '앨범에서 고르기' }))
    expect(await screen.findByText(DENIED)).toBeTruthy()
  })

  it('촬영을 취소하면 아무 안내 없이 원래대로 돌아간다', async () => {
    getPhotos.mockResolvedValue([])
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: '앨범에서 고르기' }))
    await waitFor(() => expect(getPhotos).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByRole('button', { name: '앨범에서 고르기' })).toHaveProperty('disabled', false))
    expect(screen.queryByText(FAILED)).toBeNull()
    expect(screen.queryByText(DENIED)).toBeNull()
    expect(decode).not.toHaveBeenCalled()
  })
})
