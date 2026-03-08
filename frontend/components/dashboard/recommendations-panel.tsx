'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { TierBadge } from '@/components/tier-badge'
import type { Problem, QualityRating, Tier } from '@/lib/types'
import { ExternalLink, Sparkles, Check, SkipForward, TrendingUp, ArrowRight } from 'lucide-react'

interface RecommendationsPanelProps {
  problems: Problem[]
  onNewProblems: (problems: Problem[]) => void
  onProfileUpdate: () => void
}

const qualityOptions: { value: QualityRating; label: string; color: string; bgColor: string }[] = [
  { value: 'clean', label: 'Solved Clean', color: 'text-[#22c55e]', bgColor: 'bg-[#22c55e]/10 hover:bg-[#22c55e]/20 border-[#22c55e]/30' },
  { value: 'hints', label: 'Used Hints', color: 'text-[#eab308]', bgColor: 'bg-[#eab308]/10 hover:bg-[#eab308]/20 border-[#eab308]/30' },
  { value: 'solution', label: 'Looked at Solution', color: 'text-[#f97316]', bgColor: 'bg-[#f97316]/10 hover:bg-[#f97316]/20 border-[#f97316]/30' },
  { value: 'struggled', label: 'Struggled', color: 'text-[#ef4444]', bgColor: 'bg-[#ef4444]/10 hover:bg-[#ef4444]/20 border-[#ef4444]/30' },
]

interface MasteryFeedback {
  primary: {
    subtopic: string
    topic: string
    oldScore: number
    newScore: number
    delta: number
    oldTier: Tier
    newTier: Tier
    tierChanged: boolean
  }
  secondary: {
    subtopic: string
    oldScore: number
    newScore: number
    delta: number
    newTier: string
  }[]
  overall: {
    oldScore: number
    newScore: number
    delta: number
  }
}

interface ProblemState {
  status: 'pending' | 'solved' | 'skipped'
  quality?: QualityRating
  showOptions?: boolean
  feedback?: MasteryFeedback
}

export function RecommendationsPanel({ problems, onNewProblems, onProfileUpdate }: RecommendationsPanelProps) {
  const [problemStates, setProblemStates] = useState<Record<string, ProblemState>>(
    Object.fromEntries(problems.map(p => [p.id, { status: 'pending' }]))
  )
  const [isGenerating, setIsGenerating] = useState(false)

  const handleSolvedClick = (problemId: string) => {
    setProblemStates(prev => ({
      ...prev,
      [problemId]: { ...prev[problemId], showOptions: !prev[problemId].showOptions }
    }))
  }

  const handleQualitySelect = async (problemId: string, quality: QualityRating) => {
    setProblemStates(prev => ({
      ...prev,
      [problemId]: { ...prev[problemId], status: 'solved', quality, showOptions: false }
    }))
    try {
      const res = await fetch('/api/solve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ problemId, quality }),
      })
      if (res.ok) {
        const data = await res.json()
        setProblemStates(prev => ({
          ...prev,
          [problemId]: { ...prev[problemId], feedback: data as MasteryFeedback }
        }))
        onProfileUpdate()
      }
    } catch (err) {
      console.error('Report solve failed:', err)
    }
  }

  const handleSkip = async (problemId: string) => {
    setProblemStates(prev => ({
      ...prev,
      [problemId]: { status: 'skipped', showOptions: false }
    }))
    try {
      await fetch('/api/skip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ problemId }),
      })
    } catch (err) {
      console.error('Report skip failed:', err)
    }
  }

  const handleGenerateMore = async () => {
    setIsGenerating(true)
    try {
      const res = await fetch('/api/recommend', { method: 'POST' })
      if (!res.ok) throw new Error('Failed to generate')
      const data = await res.json()
      if (data.problems?.length) {
        onNewProblems(data.problems)
        setProblemStates(
          Object.fromEntries(data.problems.map((p: Problem) => [p.id, { status: 'pending' }]))
        )
      }
    } catch (err) {
      console.error('Generate more failed:', err)
    } finally {
      setIsGenerating(false)
    }
  }

  const allDone = Object.values(problemStates).every(
    state => state.status === 'solved' || state.status === 'skipped'
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 mb-2">
        <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center">
          <Sparkles className="h-4 w-4 text-primary" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-foreground">Recommended Problems</h2>
          <p className="text-sm text-muted-foreground">
            {Object.values(problemStates).filter(s => s.status !== 'pending').length}/{problems.length} completed
          </p>
        </div>
      </div>

      <div className="space-y-3">
        {problems.map((problem, index) => {
          const state = problemStates[problem.id]
          if (!state) return null
          const isComplete = state.status !== 'pending'

          return (
            <div
              key={problem.id}
              className={cn(
                'rounded-xl border p-4 transition-all',
                isComplete
                  ? 'bg-secondary/20 border-border/50'
                  : 'bg-card border-border'
              )}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  <span className="text-sm font-bold text-muted-foreground w-6 pt-0.5">
                    {index + 1}.
                  </span>
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <a
                        href={problem.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-foreground font-medium hover:text-primary transition-colors inline-flex items-center gap-1.5"
                      >
                        {problem.title}
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {problem.topic} &gt; {problem.subtopic}
                    </p>
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span>Elo: <span className="text-foreground font-medium">{problem.elo}</span></span>
                      <span>Importance: <span className="text-foreground font-medium">{problem.importance}%</span></span>
                      <span>Your Mastery: <span className="text-foreground font-medium">{problem.currentMastery}</span></span>
                    </div>
                  </div>
                </div>

                {!isComplete && (
                  <div className="flex items-center gap-2 shrink-0">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleSolvedClick(problem.id)}
                      className={cn(
                        state.showOptions && 'ring-2 ring-primary'
                      )}
                    >
                      <Check className="h-4 w-4 mr-1" />
                      Solved
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleSkip(problem.id)}
                    >
                      <SkipForward className="h-4 w-4 mr-1" />
                      Skip
                    </Button>
                  </div>
                )}

                {state.status === 'solved' && state.quality && !state.feedback && (
                  <div className="flex items-center gap-2 shrink-0">
                    <span className={cn(
                      'text-xs font-medium px-2 py-1 rounded border',
                      qualityOptions.find(q => q.value === state.quality)?.color,
                      qualityOptions.find(q => q.value === state.quality)?.bgColor
                    )}>
                      {qualityOptions.find(q => q.value === state.quality)?.label}
                    </span>
                  </div>
                )}

                {state.status === 'skipped' && (
                  <span className="text-xs text-muted-foreground">Skipped</span>
                )}
              </div>

              {/* Quality Options */}
              {state.showOptions && (
                <div className="mt-4 pt-4 border-t border-border">
                  <p className="text-xs text-muted-foreground mb-3">How did it go?</p>
                  <div className="flex flex-wrap gap-2">
                    {qualityOptions.map((option) => (
                      <button
                        key={option.value}
                        onClick={() => handleQualitySelect(problem.id, option.value)}
                        className={cn(
                          'text-xs font-medium px-3 py-1.5 rounded-full border transition-colors',
                          option.color,
                          option.bgColor
                        )}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Mastery Feedback */}
              {state.feedback?.primary && (
                <div className="mt-3 pt-3 border-t border-border space-y-2">
                  <div className="flex items-center gap-2">
                    <TrendingUp className="h-3.5 w-3.5 text-primary" />
                    <span className="text-xs font-medium text-foreground">Mastery Update</span>
                    {state.quality && (
                      <span className={cn(
                        'text-xs font-medium px-1.5 py-0.5 rounded border',
                        qualityOptions.find(q => q.value === state.quality)?.color,
                        qualityOptions.find(q => q.value === state.quality)?.bgColor
                      )}>
                        {qualityOptions.find(q => q.value === state.quality)?.label}
                      </span>
                    )}
                  </div>

                  {/* Primary subtopic change */}
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-muted-foreground">{state.feedback.primary.subtopic}:</span>
                    <span className="text-foreground font-mono">{state.feedback.primary.oldScore}</span>
                    <ArrowRight className="h-3 w-3 text-muted-foreground" />
                    <span className="text-foreground font-mono font-bold">{state.feedback.primary.newScore}</span>
                    <span className={cn(
                      'font-mono font-bold',
                      state.feedback.primary.delta > 0 ? 'text-[#22c55e]' : state.feedback.primary.delta < 0 ? 'text-[#ef4444]' : 'text-muted-foreground'
                    )}>
                      ({state.feedback.primary.delta > 0 ? '+' : ''}{state.feedback.primary.delta})
                    </span>
                    {state.feedback.primary.tierChanged && (
                      <span className="flex items-center gap-1">
                        <TierBadge tier={state.feedback.primary.oldTier} size="sm" showLabel={false} />
                        <ArrowRight className="h-3 w-3 text-muted-foreground" />
                        <TierBadge tier={state.feedback.primary.newTier} size="sm" />
                      </span>
                    )}
                  </div>

                  {/* Secondary changes */}
                  {state.feedback.secondary.map((sec) => (
                    <div key={sec.subtopic} className="flex items-center gap-2 text-xs pl-2 opacity-70">
                      <span className="text-muted-foreground">{sec.subtopic}:</span>
                      <span className={cn(
                        'font-mono',
                        sec.delta > 0 ? 'text-[#22c55e]' : 'text-[#ef4444]'
                      )}>
                        {sec.delta > 0 ? '+' : ''}{sec.delta}
                      </span>
                    </div>
                  ))}

                  {/* Overall */}
                  {state.feedback.overall.delta !== 0 && (
                    <div className="flex items-center gap-2 text-xs pt-1 border-t border-border/50">
                      <span className="text-muted-foreground">Overall:</span>
                      <span className="text-foreground font-mono">{state.feedback.overall.oldScore}</span>
                      <ArrowRight className="h-3 w-3 text-muted-foreground" />
                      <span className="text-foreground font-mono font-bold">{state.feedback.overall.newScore}</span>
                      <span className={cn(
                        'font-mono font-bold',
                        state.feedback.overall.delta > 0 ? 'text-[#22c55e]' : 'text-[#ef4444]'
                      )}>
                        ({state.feedback.overall.delta > 0 ? '+' : ''}{state.feedback.overall.delta})
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Generate More — only when all done */}
      {allDone && (
        <div className="pt-4">
          <Button
            className="w-full"
            size="lg"
            onClick={handleGenerateMore}
            disabled={isGenerating}
          >
            <Sparkles className="h-4 w-4 mr-2" />
            {isGenerating ? 'Generating...' : 'Generate New Recommendations'}
          </Button>
        </div>
      )}
    </div>
  )
}
