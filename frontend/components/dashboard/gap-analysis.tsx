'use client'

import { TierBadge } from '@/components/tier-badge'
import type { Tier } from '@/lib/types'
import { AlertTriangle, ArrowRight } from 'lucide-react'

interface GapItem {
  subtopic: string
  topic: string
  gap: number
  currentTier: Tier
}

interface GapAnalysisProps {
  gaps: GapItem[]
}

export function GapAnalysis({ gaps }: GapAnalysisProps) {
  const topGaps = gaps.slice(0, 5)

  if (topGaps.length === 0) {
    return (
      <div className="bg-card border border-border rounded-xl p-6">
        <h2 className="text-lg font-semibold text-foreground mb-4">Gap Analysis</h2>
        <p className="text-muted-foreground text-sm">
          No gaps detected. You are meeting all your target tiers!
        </p>
      </div>
    )
  }

  return (
    <div className="bg-card border border-border rounded-xl p-6">
      <div className="flex items-center gap-2 mb-4">
        <AlertTriangle className="h-5 w-5 text-[#FFD700]" />
        <h2 className="text-lg font-semibold text-foreground">Gap Analysis</h2>
      </div>
      <p className="text-sm text-muted-foreground mb-4">
        Subtopics furthest below your target mastery
      </p>
      <div className="space-y-3">
        {topGaps.map((gap, index) => (
          <div
            key={`${gap.topic}-${gap.subtopic}`}
            className="flex items-center justify-between p-3 bg-secondary/30 rounded-lg"
          >
            <div className="flex items-center gap-3">
              <span className="text-xs font-bold text-muted-foreground w-5">
                {index + 1}.
              </span>
              <div>
                <p className="text-sm font-medium text-foreground">{gap.subtopic}</p>
                <p className="text-xs text-muted-foreground">{gap.topic}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <TierBadge tier={gap.currentTier} size="sm" />
              <span className="text-xs font-mono text-[#FFD700] bg-[#FFD700]/10 px-2 py-1 rounded">
                -{Math.round(gap.gap)} pts
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
