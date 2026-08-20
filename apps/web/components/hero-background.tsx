const BARS = 28

export function HeroBackground() {
  return (
    <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden" aria-hidden>
      <div className="absolute inset-x-0 top-0 flex h-[62vh] items-end justify-center gap-[2px] opacity-[0.55]">
        {Array.from({ length: BARS }, (_, index) => {
          const distance = Math.abs(index - (BARS - 1) / 2) / ((BARS - 1) / 2)
          const height = 26 + Math.round((1 - distance ** 1.7) * 68)
          return (
            <span
              key={index}
              className="strata-bar w-[2.4%] max-w-[46px] rounded-t-[2px]"
              style={{
                height: `${height}%`,
                opacity: 0.1 + (1 - distance) * 0.5,
                animationDelay: `${index * 45}ms`,
              }}
            />
          )
        })}
      </div>
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_28%,transparent_18%,var(--color-canvas)_72%)]" />
      <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-b from-transparent to-canvas" />
    </div>
  )
}
