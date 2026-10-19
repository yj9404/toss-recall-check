import { Result } from '@toss/tds-mobile'

interface Props {
  title: string
  description?: string
  actionLabel: string
  onAction: () => void
}

export function ErrorView({ title, description, actionLabel, onAction }: Props) {
  return (
    <Result
      title={title}
      description={description}
      button={
        <Result.Button size="medium" onClick={onAction}>
          {actionLabel}
        </Result.Button>
      }
    />
  )
}

export function LoadFailedView({ onRetry }: { onRetry: () => void }) {
  return (
    <ErrorView
      title="정보를 불러오지 못했어요"
      description="네트워크 상태를 확인하고 다시 시도해 주세요."
      actionLabel="다시 시도"
      onAction={onRetry}
    />
  )
}
