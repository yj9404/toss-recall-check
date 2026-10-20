// @vitest-environment jsdom
import { SearchField } from '@toss/tds-mobile'
import { cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { disarmUntypedButtons } from './forms'

afterEach(cleanup)

// 폼의 기본 버튼: 키보드 검색(Enter)의 암시적 제출이 누르는 첫 submit 버튼
const defaultButton = (form: HTMLFormElement) =>
  [...form.querySelectorAll('button')].find((b) => b.type === 'submit')

describe('disarmUntypedButtons', () => {
  it('type을 적지 않은 버튼만 type="button"으로 바꾼다', () => {
    document.body.innerHTML = `
      <form>
        <button id="untyped"></button>
        <button id="reset" type="reset"></button>
        <button id="submit" type="submit"></button>
      </form>`
    disarmUntypedButtons(document.body)
    expect(document.getElementById('untyped')?.getAttribute('type')).toBe('button')
    expect(document.getElementById('reset')?.getAttribute('type')).toBe('reset')
    expect(document.getElementById('submit')?.getAttribute('type')).toBe('submit')
  })

  it('TDS SearchField의 삭제 버튼이 폼의 기본 버튼이 되지 않게 한다', () => {
    const { container } = render(
      <form>
        <div className="field">
          <SearchField value="완구" onChange={() => {}} />
        </div>
        <button type="submit">검색</button>
      </form>,
    )
    const form = container.querySelector('form')!
    // TDS 삭제 버튼은 type이 없어 검색 버튼보다 앞선 기본 버튼이다 (이 전제가 바뀌면 이 처리가 필요 없다)
    expect(defaultButton(form)?.getAttribute('aria-label')).toBe('검색어 삭제')

    disarmUntypedButtons(container.querySelector('.field')!)
    expect(defaultButton(form)?.textContent).toBe('검색')
  })
})
