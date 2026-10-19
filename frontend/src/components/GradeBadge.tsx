import { Badge } from '@toss/tds-mobile'

// 위해도 순서를 색으로도 보여 준다. 회수 대상이라 '안전'으로 읽힐 수 있는 green·blue는 쓰지 않는다.
const COLOR = { 1: 'red', 2: 'yellow', 3: 'elephant' } as const

export function GradeBadge({ grade, size }: { grade: 1 | 2 | 3; size: 'small' | 'medium' }) {
  return (
    <Badge size={size} variant="weak" color={COLOR[grade]}>
      회수 {grade}등급
    </Badge>
  )
}
