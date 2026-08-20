const STRATA = [
  { y: 0, opacity: 1 },
  { y: 15, opacity: 0.72 },
  { y: 30, opacity: 0.5 },
  { y: 45, opacity: 0.32 },
  { y: 60, opacity: 0.18 },
]

const SHEAR = 7
const HALF = 30
const GAP = 4
const HEIGHT = 11

export function Mark({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      viewBox="0 0 72 84"
      width={size}
      height={size}
      className={className}
      role="img"
      aria-label="Canon"
    >
      {STRATA.map((layer) => {
        const top = layer.y + 6
        const bottom = top + HEIGHT
        const left = `M ${36 - GAP} ${top} L ${36 - GAP - HALF + SHEAR} ${top} L ${36 - GAP - HALF} ${bottom} L ${36 - GAP} ${bottom} Z`
        const right = `M ${36 + GAP} ${top} L ${36 + GAP + HALF - SHEAR} ${top} L ${36 + GAP + HALF} ${bottom} L ${36 + GAP} ${bottom} Z`
        return (
          <g key={layer.y} opacity={layer.opacity}>
            <path d={left} fill="currentColor" />
            <path d={right} fill="currentColor" />
          </g>
        )
      })}
      <rect x="34.6" y="0" width="2.8" height="84" rx="1.4" className="fill-accent" />
    </svg>
  )
}
