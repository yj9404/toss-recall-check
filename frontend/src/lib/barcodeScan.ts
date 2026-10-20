// 바코드 화면에서만 동적 import한다. 첫 화면 번들에 ZXing이 섞이지 않게 이 파일을 정적으로 import하지 않는다.
// 이미지는 기기 안에서만 다루고 서버로 보내지 않는다.
// @zxing/library는 index에서 가져오면 전체가 번들되므로 필요한 모듈만 경로로 가져온다.
import BinaryBitmap from '@zxing/library/esm/core/BinaryBitmap'
import RGBLuminanceSource from '@zxing/library/esm/core/RGBLuminanceSource'
import BitArray from '@zxing/library/esm/core/common/BitArray'
import HybridBinarizer from '@zxing/library/esm/core/common/HybridBinarizer'
import EAN13Reader from '@zxing/library/esm/core/oned/EAN13Reader'
import { isValidBarcode } from './barcode'

// 1D 판독은 한 줄만 보고도 체크섬이 맞는 엉뚱한 번호를 낼 수 있다(흐리고 기울고 잡음 많은 사진).
// 틀린 번호로 조회하면 "목록에 없음"으로 잘못 안내할 수 있어, 서로 다른 줄에서 같은 번호가 이만큼 나와야 인정한다.
const MIN_AGREEING_ROWS = 2

function decodeOnce(gray: Uint8ClampedArray, width: number, height: number): string | null {
  const bitmap = new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(gray, width, height)))
  const reader = new EAN13Reader()
  const votes = new Map<string, number>()
  const rowStep = Math.max(1, height >> 8)
  let row = new BitArray(width)
  for (let y = rowStep >> 1; y < height; y += rowStep) {
    try {
      row = bitmap.getBlackRow(y, row)
    } catch {
      continue
    }
    // 두 번째 시도는 뒤집힌(180도) 바코드용이다
    for (let attempt = 0; attempt < 2; attempt++) {
      if (attempt === 1) row.reverse()
      let text: string
      try {
        text = reader.decodeRow(y, row).getText()
      } catch {
        // NotFoundException·ChecksumException 등은 이 줄에서 못 읽은 것으로 본다
        continue
      }
      if (!isValidBarcode(text)) continue
      const count = (votes.get(text) ?? 0) + 1
      if (count >= MIN_AGREEING_ROWS) return text
      votes.set(text, count)
      break
    }
  }
  return null
}

/** 시계 방향 90도 회전. 세로로 찍힌 바코드도 읽기 위해 쓴다 */
export function rotate90(gray: Uint8ClampedArray, width: number, height: number): Uint8ClampedArray {
  const out = new Uint8ClampedArray(gray.length)
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) out[x * height + (height - 1 - y)] = gray[y * width + x]
  }
  return out
}

/** 회색조 픽셀(한 칸 1바이트)에서 EAN-13을 찾는다. 못 찾으면 null */
export function decodeEan13FromGray(gray: Uint8ClampedArray, width: number, height: number): string | null {
  return decodeOnce(gray, width, height) ?? decodeOnce(rotate90(gray, width, height), height, width)
}

/** RGBA 픽셀을 회색조로 바꾼다 */
export function toGray(rgba: Uint8ClampedArray): Uint8ClampedArray {
  const gray = new Uint8ClampedArray(rgba.length / 4)
  for (let i = 0; i < gray.length; i++) {
    const p = i * 4
    gray[i] = (rgba[p] * 299 + rgba[p + 1] * 587 + rgba[p + 2] * 114) / 1000
  }
  return gray
}

/** base64 옵션으로 받은 값은 접두사 없는 base64일 수 있어 data URI로 맞춘다 */
export function toDataUri(value: string): string {
  return value.startsWith('data:') ? value : `data:image/jpeg;base64,${value}`
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('image load failed'))
    img.src = src
  })
}

/** Device.openCamera / getPhotos가 준 dataUri를 읽어 EAN-13 13자리를 돌려준다. 못 읽으면 null */
export async function decodeEan13FromDataUri(dataUri: string): Promise<string | null> {
  const img = await loadImage(toDataUri(dataUri))
  const canvas = document.createElement('canvas')
  canvas.width = img.naturalWidth
  canvas.height = img.naturalHeight
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx || !canvas.width || !canvas.height) return null
  ctx.drawImage(img, 0, 0)
  const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height)
  return decodeEan13FromGray(toGray(data), canvas.width, canvas.height)
}
