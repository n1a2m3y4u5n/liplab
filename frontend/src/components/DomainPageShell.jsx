const ACCENTS = {
  learn: { eyebrow: 'text-sky-700', panel: 'from-sky-50 to-white', mark: 'bg-sky-500' },
  review: { eyebrow: 'text-amber-800', panel: 'from-amber-50 to-white', mark: 'bg-amber-500' },
  analysis: { eyebrow: 'text-violet-700', panel: 'from-violet-50 to-white', mark: 'bg-violet-500' },
}

export default function DomainPageShell({ domain, title, description, children, actions, exitTo = '/dashboard' }) {
  const navigate = useNavigate()
  const accent = ACCENTS[domain] || ACCENTS.learn

  return (
    <div className="min-h-screen bg-[#f7f8fa] text-slate-950">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-[1180px] px-4 py-4 sm:px-6">
          <div className="flex items-center justify-between gap-4">
            <button type="button" onClick={() => navigate('/dashboard')} className="flex items-center gap-2 text-left">
              <span aria-hidden="true" className="relative grid h-9 w-9 place-items-center rounded-xl bg-sky-50">
                <span className="absolute h-3.5 w-6 rounded-full border-[3px] border-sky-400" />
                <span className="absolute h-6 w-3.5 rounded-full border-[3px] border-sky-400" />
              </span>
              <span className="text-lg font-black tracking-[-0.04em]">LIPLAB</span>
            </button>
            <button type="button" onClick={() => navigate(exitTo)} className="text-sm font-bold text-slate-500 hover:text-slate-900">✕ 나가기</button>
          </div>
          <nav className="mt-4 flex gap-1 rounded-2xl bg-slate-50 p-1" aria-label="콘텐츠 영역">
            {DOMAINS.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => navigate(item.to)}
                aria-current={domain === item.id ? 'page' : undefined}
                className={`flex-1 rounded-xl px-4 py-2.5 text-sm font-black transition ${domain === item.id ? item.active : item.idle}`}
              >
                {item.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-[1180px] px-4 py-7 sm:px-6 sm:py-10">
        <section className={`relative overflow-hidden rounded-[28px] border border-slate-200 bg-gradient-to-br ${accent.panel} px-5 py-7 sm:px-8 sm:py-9`}>
          <span aria-hidden="true" className={`absolute left-0 top-0 h-full w-1.5 ${accent.mark}`} />
          <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
            <div>
              <p className={`text-xs font-black tracking-[0.14em] ${accent.eyebrow}`}>{domain === 'learn' ? 'LEARN' : domain === 'review' ? 'REVIEW' : 'ANALYSIS'}</p>
              <h1 className="mt-2 text-3xl font-black tracking-[-0.04em] sm:text-4xl">{title}</h1>
              <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-600 sm:text-base">{description}</p>
            </div>
            {actions && <div className="shrink-0">{actions}</div>}
          </div>
        </section>
        <div className="mt-6">{children}</div>
      </main>
    </div>
  )
}
