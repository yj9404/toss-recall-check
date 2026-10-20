/**
 * container 안에서 type을 적지 않은 버튼을 type="button"으로 바꾼다.
 *
 * type이 없는 <button>은 submit이라, 폼 안에 두면 키보드 검색(Enter)의 암시적 제출이
 * 그 버튼을 누른다. TDS SearchField의 "검색어 삭제" 버튼이 그래서 검색어를 지우고 제출됐다.
 */
export function disarmUntypedButtons(container: ParentNode) {
  container.querySelectorAll('button:not([type])').forEach((button) => {
    button.setAttribute('type', 'button')
  })
}
