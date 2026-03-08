'use client'

import { useState } from 'react'
import { cn } from '@/lib/utils'
import { TierBadge } from '@/components/tier-badge'
import type { Topic, Tier } from '@/lib/types'
import { ChevronDown, AlertTriangle } from 'lucide-react'

interface TopicCardProps {
  topic: Topic
}

function getTierOrder(tier: Tier): number {
  const order: Record<Tier, number> = {
    bronze: 0,
    silver: 1,
    gold: 2,
    platinum: 3,
    diamond: 4
  }
  return order[tier]
}

export function TopicCard({ topic }: TopicCardProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden transition-all hover:border-muted-foreground/30">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full p-5 flex items-center justify-between text-left"
      >
        <div className="flex items-center gap-4">
          <div className="flex flex-col">
            <h3 className="font-semibold text-foreground">{topic.name}</h3>
            <p className="text-sm text-muted-foreground">
              {topic.subtopics.length} subtopics
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-lg font-bold text-foreground">{topic.score}</p>
            <p className="text-xs text-muted-foreground">score</p>
          </div>
          <TierBadge tier={topic.tier} size="sm" />
          <ChevronDown
            className={cn(
              'h-5 w-5 text-muted-foreground transition-transform',
              isExpanded && 'rotate-180'
            )}
          />
        </div>
      </button>

      {isExpanded && (
        <div className="border-t border-border">
          {topic.subtopics.map((subtopic, index) => {
            const hasGap = getTierOrder(subtopic.tier) < getTierOrder(subtopic.targetTier)
            
            return (
              <div
                key={subtopic.id}
                className={cn(
                  'flex items-center justify-between px-5 py-3',
                  index < topic.subtopics.length - 1 && 'border-b border-border/50'
                )}
              >
                <div className="flex items-center gap-3">
                  {hasGap && (
                    <AlertTriangle className="h-4 w-4 text-[#FFD700]" />
                  )}
                  <span className="text-sm text-foreground">{subtopic.name}</span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-sm font-medium text-foreground">{subtopic.score}</span>
                  <TierBadge tier={subtopic.tier} size="sm" showLabel={false} />
                  {hasGap && (
                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <span>Target:</span>
                      <TierBadge tier={subtopic.targetTier} size="sm" showLabel={false} />
                    </div>
                  )}
                  <span className="text-xs text-muted-foreground min-w-[60px] text-right">
                    {subtopic.problemsSolved} solved
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
