import { Mark } from "@/components/mark"

export function Wordmark({ size = 22 }: { size?: number }) {
  return (
    <span className="flex items-center gap-2.5">
      <Mark size={size * 1.15} className="text-ink" />
      <span className="font-light tracking-[-0.03em] text-ink" style={{ fontSize: size }}>
        CANON
      </span>
    </span>
  )
}
