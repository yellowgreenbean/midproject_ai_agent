// 선 아이콘 모음 (24px 격자, 색은 currentColor 를 따른다)
const PATHS = {
  home: 'M3 10.5 12 3l9 7.5M5.5 9v11.5h13V9',
  wallet: 'M3 7.5A2.5 2.5 0 0 1 5.5 5h13A2.5 2.5 0 0 1 21 7.5v9a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 16.5zM3 9.5h18M16 14.5h1.5',
  list: 'M9 6h12M9 12h12M9 18h12M4 6h.01M4 12h.01M4 18h.01',
  send: 'M21.5 2.5 10.5 13.5M21.5 2.5 15 21.5l-4.5-8-8-4.5z',
  card: 'M2.5 7A2 2 0 0 1 4.5 5h15a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-15a2 2 0 0 1-2-2zM2.5 10h19M6 15h3',
  layers: 'M12 2.5 21.5 7.5 12 12.5 2.5 7.5zM2.5 12 12 17l9.5-5M2.5 16.5 12 21.5l9.5-5',
  bell: 'M6 9a6 6 0 0 1 12 0c0 6.5 2.5 8 2.5 8h-17S6 15.5 6 9M10.3 20.5a2 2 0 0 0 3.4 0',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M12 7v5l3 2',
  settings:
    'M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7M19.4 13.5l1.6 1.3-2 3.4-2-.7a7.5 7.5 0 0 1-2.2 1.3l-.3 2.2h-4l-.3-2.2a7.5 7.5 0 0 1-2.2-1.3l-2 .7-2-3.4 1.6-1.3a7.6 7.6 0 0 1 0-3l-1.6-1.3 2-3.4 2 .7a7.5 7.5 0 0 1 2.2-1.3l.3-2.2h4l.3 2.2a7.5 7.5 0 0 1 2.2 1.3l2-.7 2 3.4-1.6 1.3a7.6 7.6 0 0 1 0 3',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14M21 21l-4.5-4.5',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8M4.5 20.5a7.5 7.5 0 0 1 15 0',
  chevron: 'm9 6 6 6-6 6',
  bolt: 'M13 2.5 4.5 13.5H11l-1 8 8.5-11H12z',
  chat: 'M20.5 11.5a8.5 8.5 0 0 1-12.4 7.6L3.5 20.5l1.4-4.4A8.5 8.5 0 1 1 20.5 11.5M12 8l.9 2.1 2.1.9-2.1.9L12 14l-.9-2.1L9 11l2.1-.9z',
  coins: 'M12 9c4 0 7-1.3 7-3s-3-3-7-3-7 1.3-7 3 3 3 7 3M5 6v6c0 1.7 3 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3 3 7 3s7-1.3 7-3v-6',
  safe: 'M4 4.5h16v14H4zM6 18.5V21M18 18.5V21M14.5 11.5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0M17 9v5',
  plus: 'M12 5v14M5 12h14',
  arrowIn: 'M12 4v15M6 13l6 6 6-6',
  star:'M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z',
} as const

export type IconName = keyof typeof PATHS

export default function Icon({ name, size = 22 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  )
}
