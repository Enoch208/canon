export function MaskedHeading({
  text,
  className = "",
  delay = 0,
}: {
  text: string
  className?: string
  delay?: number
}) {
  return (
    <h1 className={`flex flex-wrap justify-center gap-x-[0.26em] gap-y-[0.08em] ${className}`}>
      {text.split(" ").map((word, index) => (
        <span key={`${word}-${index}`} className="inline-flex overflow-hidden pb-[0.08em]">
          <span
            className="mask-word"
            style={{ animationDelay: `${delay + index * 55}ms` }}
          >
            {word}
          </span>
        </span>
      ))}
    </h1>
  )
}
