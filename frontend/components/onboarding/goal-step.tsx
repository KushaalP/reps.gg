'use client'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { Goal } from '@/lib/types'
import { GOAL_LABELS } from '@/lib/types'
import { Target, Building2, Rocket, TrendingUp, Code, Sparkles } from 'lucide-react'

interface EnrichBump {
  subtopic: string
  bump: number
  reason: string
}

interface GoalStepProps {
  selectedGoal: Goal | null
  setSelectedGoal: (goal: Goal) => void
  onStart: () => void
  enrichResult?: { bumps: EnrichBump[] } | null
}

const goalIcons: Record<Goal, React.ReactNode> = {
  faang: <Building2 className="h-5 w-5" />,
  'mid-tech': <Code className="h-5 w-5" />,
  startup: <Rocket className="h-5 w-5" />,
  quant: <TrendingUp className="h-5 w-5" />,
  general: <Target className="h-5 w-5" />
}

const goalDescriptions: Record<Goal, string> = {
  faang: 'Target Diamond tier across all topics',
  'mid-tech': 'Target Platinum tier across most topics',
  startup: 'Target Gold tier with focus on practical skills',
  quant: 'Diamond tier focus on math-heavy problems',
  general: 'Balanced improvement across all areas'
}

export function GoalStep({ selectedGoal, setSelectedGoal, onStart, enrichResult }: GoalStepProps) {
  const goals = Object.keys(GOAL_LABELS) as Goal[]

  return (
    <div className="space-y-6">
      {/* Resume enrichment results */}
      {enrichResult?.bumps && enrichResult.bumps.length > 0 && (
        <div className="rounded-lg border border-[#22c55e]/30 bg-[#22c55e]/5 p-4 space-y-2">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-[#22c55e]" />
            <span className="text-sm font-medium text-foreground">Resume Analysis Applied</span>
          </div>
          <div className="space-y-1">
            {enrichResult.bumps.map((b) => (
              <div key={b.subtopic} className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">{b.subtopic}</span>
                <span className="font-mono text-[#22c55e] font-medium">+{b.bump}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="text-center mb-6">
        <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
          <Target className="h-6 w-6 text-primary" />
        </div>
        <h2 className="text-xl font-semibold text-foreground mb-2">Set Your Goal</h2>
        <p className="text-sm text-muted-foreground">
          Choose your target to get personalized practice plans
        </p>
      </div>

      <div className="grid gap-3">
        {goals.map((goal) => (
          <button
            key={goal}
            onClick={() => setSelectedGoal(goal)}
            className={cn(
              'flex items-start gap-4 p-4 rounded-lg border text-left transition-all',
              selectedGoal === goal
                ? 'border-primary bg-primary/5 ring-1 ring-primary'
                : 'border-border bg-secondary/30 hover:bg-secondary/50 hover:border-muted-foreground/30'
            )}
          >
            <div className={cn(
              'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
              selectedGoal === goal ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
            )}>
              {goalIcons[goal]}
            </div>
            <div className="flex-1 min-w-0">
              <p className={cn(
                'font-medium',
                selectedGoal === goal ? 'text-foreground' : 'text-foreground/80'
              )}>
                {GOAL_LABELS[goal]}
              </p>
              <p className="text-sm text-muted-foreground mt-0.5">
                {goalDescriptions[goal]}
              </p>
            </div>
          </button>
        ))}
      </div>

      <Button 
        onClick={onStart}
        disabled={!selectedGoal}
        className="w-full"
        size="lg"
      >
        Start
      </Button>
    </div>
  )
}
