import hugeicons from "@iconify-json/hugeicons/icons.json"
import { Icon as IconifyIcon } from "@iconify/react/offline"

const ICONS = hugeicons.icons as Record<string, { body: string }>

export function Icon({
  name,
  size = 24,
  className,
}: {
  name: string
  size?: number
  className?: string
}) {
  const data = ICONS[name]
  if (!data) {
    throw new Error(`unknown hugeicons icon: ${name}`)
  }
  return (
    <IconifyIcon
      icon={{ body: data.body, width: hugeicons.width, height: hugeicons.height }}
      width={size}
      height={size}
      className={className}
    />
  )
}
