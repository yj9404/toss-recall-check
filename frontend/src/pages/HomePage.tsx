import { Button, SearchField, Tab, Top } from '@toss/tds-mobile'
import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { BannerAd } from '../components/BannerAd'
import { Disclaimer } from '../components/Disclaimer'
import { LoadFailedView } from '../components/ErrorView'
import { ListSkeleton } from '../components/ListSkeleton'
import { RecallCard } from '../components/RecallCard'
import { useCategories } from '../hooks/useCategories'
import { useRecallList } from '../hooks/useRecallList'
import { homeAdGroupId } from '../lib/ads'
import { logClick, logScreen } from '../lib/analytics'
import { OVERSEAS, orderCategories } from '../lib/categories'
import { disarmUntypedButtons } from '../lib/forms'
import { getHomeSnapshot, isOverseasNoticeSeen, markOverseasNoticeSeen, saveHomeSnapshot } from '../lib/homeCache'

const AD_AFTER = 5

export function HomePage() {
  const navigate = useNavigate()
  // 상세에서 뒤로 왔다면 검색어·카테고리·목록·스크롤 위치를 그대로 되살린다
  const [restored] = useState(getHomeSnapshot)
  const [input, setInput] = useState(restored?.input ?? '')
  const [query, setQuery] = useState(restored?.query ?? '')
  const [category, setCategory] = useState(restored?.category ?? '')
  // 검색 버튼으로 시작된 조회만 결과 수를 기록한다
  const logSearchRef = useRef<{ category: string; length: number } | null>(null)
  const searchFieldRef = useRef<HTMLDivElement>(null)

  const categories = useCategories()
  const tabs = useMemo(() => orderCategories(categories), [categories])
  const list = useRecallList(
    category,
    query,
    (total) => {
      const pending = logSearchRef.current
      if (!pending) return
      logSearchRef.current = null
      logClick('search_submit_click', {
        category: pending.category || 'all',
        query_length: pending.length,
        result_count: total,
      })
    },
    restored ?? undefined,
  )

  useEffect(() => logScreen('home_screen'), [])

  // 키보드 검색(Enter)이 SearchField의 삭제 버튼이 아니라 "검색" 버튼으로 제출되게 한다
  useLayoutEffect(() => {
    if (searchFieldRef.current) disarmUntypedButtons(searchFieldRef.current)
  }, [])

  useLayoutEffect(() => {
    if (restored) window.scrollTo(0, restored.scrollY)
    // 마운트 시 한 번만 복원한다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 다른 화면으로 나가기 직전에 호출한다. 스크롤은 화면이 바뀌기 전에 읽어야 정확하다.
  function rememberHome() {
    saveHomeSnapshot({
      input,
      query,
      category,
      items: list.items,
      total: list.total,
      scrollY: window.scrollY,
    })
  }
  const selectedTab = tabs.findIndex((c) => c.code === category) + 1

  function submit(e: FormEvent) {
    e.preventDefault()
    const next = input.trim()
    logSearchRef.current = { category, length: next.length }
    // 결과가 보이도록 키보드를 닫는다
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
    if (next === query) list.reload()
    else setQuery(next)
  }

  function selectTab(index: number) {
    const code = index === 0 ? '' : tabs[index - 1].code
    if (code === category) return
    logClick('category_tab_click', { category: code || 'all' })
    logSearchRef.current = null
    if (category === OVERSEAS) markOverseasNoticeSeen()
    setCategory(code)
  }

  const adSlot = homeAdGroupId()
  const adIndex = Math.min(AD_AFTER, list.items.length) - 1

  return (
    <main className="page">
      <Top title={<Top.TitleParagraph size={22}>회수·판매중지 제품을 확인해요</Top.TitleParagraph>} />

      <form className="search" onSubmit={submit}>
        <div className="search__field" ref={searchFieldRef}>
          <SearchField
            placeholder="제품명이나 업체명을 입력해요"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onDeleteClick={() => setInput('')}
            enterKeyHint="search"
          />
        </div>
        <Button type="submit" size="medium" className="search__submit">
          검색
        </Button>
      </form>

      <div className="section">
        <Button display="full" variant="weak" size="large" onClick={() => {
            rememberHome()
            navigate('/barcode')
          }}>
          바코드 번호로 확인하기
        </Button>
      </div>

      {tabs.length > 0 && (
        // fluid: 탭이 많으면 가로 스크롤되고, 선택한 탭이 화면 밖이면 TDS가 탭 줄만 스크롤해 보이게 한다
        <Tab fluid size="small" onChange={selectTab} ariaLabel="카테고리">
          {[{ code: '', label: '전체' }, ...tabs].map((c, i) => (
            <Tab.Item key={c.code} selected={selectedTab === i}>
              {c.label}
            </Tab.Item>
          ))}
        </Tab>
      )}

      {category === OVERSEAS && !isOverseasNoticeSeen() && (
        <p className="tab-notice">해외 기관이 발표한 리콜이에요. 국내에서 팔리지 않는 제품도 있어요.</p>
      )}

      {list.status === 'loading' ? (
        <ListSkeleton />
      ) : list.status === 'error' && list.failedFirst ? (
        <LoadFailedView onRetry={list.retry} />
      ) : list.items.length === 0 ? (
        <div className="empty">
          <strong>검색 결과가 없어요</strong>
          <p>회수 목록에 없다고 안전하다는 뜻은 아니에요.</p>
        </div>
      ) : (
        <>
          <ul className="recall-list">
            {list.items.map((item, i) => (
              <Fragment key={item.id}>
                <li>
                  <RecallCard
                    item={item}
                    onClick={() => {
                      logClick('recall_item_click', {
                        id: item.id,
                        category: item.category,
                        position: i + 1,
                      })
                      rememberHome()
                      navigate(`/recall/${encodeURIComponent(item.id)}`)
                    }}
                  />
                </li>
                {i === adIndex && (
                  <li>
                    <BannerAd adGroupId={adSlot} />
                  </li>
                )}
              </Fragment>
            ))}
          </ul>
          {list.status === 'error' && (
            <p className="inline-error">더 불러오지 못했어요. 아래 버튼으로 다시 시도해 주세요.</p>
          )}
          {list.hasMore && (
            <div className="section">
              <Button
                display="full"
                variant="weak"
                size="large"
                loading={list.status === 'loadingMore'}
                onClick={list.loadMore}
              >
                더 보기
              </Button>
            </div>
          )}
        </>
      )}

      <Disclaimer />
    </main>
  )
}
