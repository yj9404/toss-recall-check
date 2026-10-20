import { Device, PermissionError } from '@apps-in-toss/web-framework'

export type PhotoSource = 'camera' | 'album'

export type PhotoResult = { status: 'ok'; dataUri: string } | { status: 'denied' } | { status: 'cancelled' }

const MAX_WIDTH = 1600

type PermissionChecked = {
  getPermission: () => Promise<string>
  openPermissionDialog: () => Promise<string>
}

// 버튼을 누른 시점에만 호출한다. 앱 진입 시에는 권한을 묻지 않는다.
async function ensurePermission(fn: PermissionChecked): Promise<boolean> {
  if ((await fn.getPermission()) === 'allowed') return true
  return (await fn.openPermissionDialog()) === 'allowed'
}

/**
 * 카메라로 찍거나 앨범에서 한 장 골라 data URI로 돌려준다.
 * base64: true로 받는다. 기본값(false)의 dataUri는 기기 안 파일 경로일 수 있어 웹뷰 캔버스로 못 읽을 수 있다.
 */
export async function pickPhoto(source: PhotoSource): Promise<PhotoResult> {
  const fn = source === 'camera' ? Device.openCamera : Device.getPhotos
  try {
    if (!(await ensurePermission(fn))) return { status: 'denied' }
  } catch {
    // 토스 앱 밖이거나 권한 API를 못 쓰는 환경. 직접 입력으로 안내한다.
    return { status: 'denied' }
  }
  try {
    const image =
      source === 'camera'
        ? await Device.openCamera({ base64: true, maxWidth: MAX_WIDTH })
        : (await Device.getPhotos({ base64: true, maxCount: 1, maxWidth: MAX_WIDTH }))[0]
    return image?.dataUri ? { status: 'ok', dataUri: image.dataUri } : { status: 'cancelled' }
  } catch (e) {
    // 촬영·선택 취소는 따로 안내하지 않는다
    return e instanceof PermissionError ? { status: 'denied' } : { status: 'cancelled' }
  }
}
