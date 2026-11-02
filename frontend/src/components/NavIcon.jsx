/** 기존 탭 그림을 currentColor 인라인 SVG로 그린다. */
const shapes = {
  today: <><path d="M15 21V13C15 12.45 14.55 12 14 12H10C9.45 12 9 12.45 9 13V21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
<path d="M3.709 8.472C3.26 8.85 3 9.41 3 10V19C3 20.1 3.895 21 5 21H19C20.1 21 21 20.1 21 19V10C21 9.41 20.741 8.852 20.291 8.472L13.291 2.472C12.546 1.842 11.454 1.842 10.709 2.472L3.709 8.472Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></>,
  learn: <><path d="M17.596 12.768C18.377 13.549 19.644 13.549 20.425 12.768C21.206 11.987 21.206 10.72 20.425 9.939L18.657 8.172C19.438 8.953 20.705 8.953 21.485 8.172C22.267 7.391 22.267 6.124 21.485 5.343L18.657 2.515C17.876 1.734 16.609 1.734 15.828 2.515C15.047 3.296 15.047 4.562 15.828 5.343L14.061 3.575C13.28 2.795 12.013 2.795 11.232 3.575C10.451 4.357 10.451 5.623 11.232 6.404L17.596 12.768Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
<path d="M2.5 21.5L3.9 20.1" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
<path d="M20.1 3.9L21.5 2.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
<path d="M5.343 21.485C6.124 22.267 7.391 22.267 8.172 21.485C8.953 20.705 8.953 19.438 8.172 18.657L9.939 20.425C10.72 21.206 11.987 21.206 12.768 20.425C13.549 19.644 13.549 18.377 12.768 17.596L6.404 11.232C5.623 10.452 4.356 10.452 3.575 11.232C2.794 12.014 2.794 13.28 3.575 14.061L5.343 15.828C4.563 15.048 3.296 15.048 2.515 15.829C1.734 16.61 1.734 17.876 2.515 18.657L5.343 21.485Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
<path d="M9.6 14.4L14.4 9.6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></>,
  records: <><path d="M3 3V19C3 20.105 3.895 21 5 21H21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
<path d="M18 17V9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
<path d="M13 17V5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
<path d="M8 17V14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></>,
  me: <><circle cx="12" cy="7" r="3" stroke="currentColor" strokeWidth="2"/>
<path d="M19 21V19C19 16.791 17.209 15 15 15H9C6.791 15 5 16.791 5 19V21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></>,
}
export default function NavIcon({ name, className = '' }) {
  return <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" className={className}>{shapes[name]}</svg>
}
