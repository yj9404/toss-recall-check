export const BARCODE_LENGTH = 13

/** 숫자만 남기고 13자리까지만 받는다 */
export function sanitizeBarcode(input: string): string {
  return input.replace(/\D/g, '').slice(0, BARCODE_LENGTH)
}

export function isValidBarcode(value: string): boolean {
  return /^\d{13}$/.test(value)
}
