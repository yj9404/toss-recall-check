import { readFileSync } from 'node:fs'
import { PNG } from 'pngjs'
import { describe, expect, it } from 'vitest'
import { decodeEan13FromGray, rotate90, toDataUri, toGray } from './barcodeScan'

// 살짝 기울고 흐릿하며 잡음이 섞인 EAN-13(8801234567893) 사진
function loadFixture(name = 'ean13-sample.png') {
  const png = PNG.sync.read(readFileSync(new URL(`./__fixtures__/${name}`, import.meta.url)))
  return { gray: toGray(new Uint8ClampedArray(png.data)), width: png.width, height: png.height }
}

describe('EAN-13 판독', () => {
  it('샘플 사진에서 13자리를 읽는다', () => {
    const { gray, width, height } = loadFixture()
    expect(decodeEan13FromGray(gray, width, height)).toBe('8801234567893')
  })

  it('세로로 찍힌 사진도 읽는다', () => {
    const { gray, width, height } = loadFixture()
    expect(decodeEan13FromGray(rotate90(gray, width, height), height, width)).toBe('8801234567893')
  })

  it('바코드가 없으면 null을 돌려준다', () => {
    const width = 320
    const height = 200
    const gray = new Uint8ClampedArray(width * height)
    for (let i = 0; i < gray.length; i++) gray[i] = (i * 7919) % 256
    expect(decodeEan13FromGray(gray, width, height)).toBeNull()
    expect(decodeEan13FromGray(new Uint8ClampedArray(width * height).fill(255), width, height)).toBeNull()
  })

  it('한 줄만 우연히 맞는 번호는 인정하지 않는다', () => {
    // 더 흐리고 잡음이 많은 같은 바코드. ZXing 기본 판독은 체크섬이 맞는 엉뚱한 번호(0861744567293)를 냈다.
    const { gray, width, height } = loadFixture('ean13-misread.png')
    expect(decodeEan13FromGray(gray, width, height)).toBeNull()
  })

  it('접두사 없는 base64도 data URI로 맞춘다', () => {
    expect(toDataUri('AAAA')).toBe('data:image/jpeg;base64,AAAA')
    expect(toDataUri('data:image/png;base64,AAAA')).toBe('data:image/png;base64,AAAA')
  })
})
