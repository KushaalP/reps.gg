'use client'

import { TierBadge } from '@/components/tier-badge'
import type { Tier } from '@/lib/types'
import { Trophy, Hash, Target } from 'lucide-react'

interface StatsHeaderProps {
  overallScore: number
  overallTier: Tier
  totalProblemsSolved: number
  targetScore?: number
}

export function StatsHeader({ overallScore, overallTier, totalProblemsSolved, targetScore }: StatsHeaderProps) {
  const progress = targetScore ? Math.min(100, Math.round((overallScore / targetScore) * 100)) : 0

  return (
    <div className="bg-card border border-border rounded-xl p-6">
      <div className="flex flex-wrap items-center justify-between gap-6">
        <div className="flex items-center gap-4">
          <div className="h-14 w-14 rounded-xl bg-primary/10 flex items-center justify-center">
            <Trophy className="h-7 w-7 text-primary" />
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Overall Mastery</p>
            <p className="text-2xl font-bold text-foreground">
              {overallScore}
              {targetScore != null && (
                <span className="text-base font-normal text-muted-foreground"> / {targetScore}</span>
              )}
            </p>
          </div>
        </div>

        {targetScore != null && (
          <div className="flex items-center gap-4">
            <div className="h-14 w-14 rounded-xl bg-secondary flex items-center justify-center">
              <Target className="h-7 w-7 text-muted-foreground" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Target Progress</p>
              <p className="text-2xl font-bold text-foreground">{progress}%</p>
            </div>
          </div>
        )}

        <div className="flex items-center gap-4">
          <div className="h-14 w-14 rounded-xl bg-secondary flex items-center justify-center">
            <TierBadge tier={overallTier} size="lg" showLabel={false} />
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Current Tier</p>
            <TierBadge tier={overallTier} size="lg" />
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="h-14 w-14 rounded-xl bg-secondary flex items-center justify-center">
            <Hash className="h-7 w-7 text-muted-foreground" />
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Problems Solved</p>
            <p className="text-2xl font-bold text-foreground">{totalProblemsSolved}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
