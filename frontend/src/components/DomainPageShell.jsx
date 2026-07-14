const ACCENTS = {
  learn: { eyebrow: 'text-sky-700', panel: 'from-sky-50 to-white', mark: 'bg-sky-500' },
  review: { eyebrow: 'text-amber-800', panel: 'from-amber-50 to-white', mark: 'bg-amber-500' },
  analysis: { eyebrow: 'text-violet-700', panel: 'from-violet-50 to-white', mark: 'bg-violet-500' },
}

export default function DomainPageShell({ domain, title, description, children, actions }) {
  const accent = ACCENTS[domain] || ACCENTS.learn

  return (
    <div className="min-h-screen bg-[#f7f8fa] text-slate-950">

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
