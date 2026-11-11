// 약관 자세히 보기 (docs/기획서.md Part 1 AUTH-F10 정상 흐름 5 · UI08) — 마이페이지 → 약관 및 동의 내역 → 자세히 보기
import AppShell from '../components/AppShell'
import Icon from '../components/Icon'
import TermsViewer from '../components/TermsViewer'
import './SettingsPages.css'

export default function TermsDetailPage({ id }: { id: string }) {
  return (
    <AppShell title="약관 보기" current="#/settings">
      <a className="set-back" href="#/settings/terms">
        <Icon name="chevron" size={16} />
        약관 및 동의 내역
      </a>
      <TermsViewer termsId={id} />
    </AppShell>
  )
}
