'use client'

import { cn } from '@/lib/utils'
import type { Tier } from '@/lib/types'

interface TierBadgeProps {
  tier: Tier
  size?: 'sm' | 'md' | 'lg'
  showLabel?: boolean
}

const tierConfig: Record<Tier, { label: string; color: string; bgColor: string; borderColor: string }> = {
  bronze: {
    label: 'Bronze',
    color: 'text-[#CD7F32]',
    bgColor: 'bg-[#CD7F32]/15',
    borderColor: 'border-[#CD7F32]/40'
  },
  silver: {
    label: 'Silver',
    color: 'text-[#C0C0C0]',
    bgColor: 'bg-[#C0C0C0]/15',
    borderColor: 'border-[#C0C0C0]/40'
  },
  gold: {
    label: 'Gold',
    color: 'text-[#FFD700]',
    bgColor: 'bg-[#FFD700]/15',
    borderColor: 'border-[#FFD700]/40'
  },
  platinum: {
    label: 'Platinum',
    color: 'text-[#2DD4BF]',
    bgColor: 'bg-[#2DD4BF]/15',
    borderColor: 'border-[#2DD4BF]/40'
  },
  diamond: {
    label: 'Diamond',
    color: 'text-[#3B82F6]',
    bgColor: 'bg-[#3B82F6]/15',
    borderColor: 'border-[#3B82F6]/40'
  }
}

const sizeClasses = {
  sm: 'text-xs px-2 py-0.5',
  md: 'text-sm px-2.5 py-1',
  lg: 'text-base px-3 py-1.5'
}

export function TierBadge({ tier, size = 'md', showLabel = true }: TierBadgeProps) {
  const config = tierConfig[tier]
  
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 font-semibold rounded-full border',
        config.color,
        config.bgColor,
        config.borderColor,
        sizeClasses[size]
      )}
    >
      <TierIcon tier={tier} size={size} />
      {showLabel && config.label}
    </span>
  )
}

function TierIcon({ tier, size }: { tier: Tier; size: 'sm' | 'md' | 'lg' }) {
  const iconSize = size === 'sm' ? 12 : size === 'md' ? 14 : 16
  const config = tierConfig[tier]
  
  return (
    <svg
      width={iconSize}
      height={iconSize}
      viewBox="0 0 24 24"
      fill="currentColor"
      className={config.color}
    >
      {tier === 'diamond' ? (
        <path d="M12 2L2 9l10 13 10-13L12 2zm0 3.84L18.34 9 12 17.65 5.66 9 12 5.84z" />
      ) : (
        <path d="M12 2L15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2z" />
      )}
    </svg>
  )
}
