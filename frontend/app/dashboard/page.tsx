'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { StatsHeader } from '@/components/dashboard/stats-header'
import { TopicCard } from '@/components/dashboard/topic-card'
import { GapAnalysis } from '@/components/dashboard/gap-analysis'
import { RecommendationsPanel } from '@/components/dashboard/recommendations-panel'
import { getGapAnalysis } from '@/lib/mock-data'
import type { UserProfile, Problem } from '@/lib/types'
import { Sparkles, Settings, LogOut, Loader2 } from 'lucide-react'

export default function DashboardPage() {
  const router = useRouter()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [problems, setProblems] = useState<Problem[]>([])
  const [hasRecommendations, setHasRecommendations] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  const refreshProfile = useCallback(async () => {
    try {
      const res = await fetch('/api/profile')
      if (!res.ok) return
      const data = await res.json()
      setProfile(data)
    } catch (err) {
      console.error('Refresh profile failed:', err)
    }
  }, [])

  useEffect(() => {
    async function loadProfile() {
      try {
        const res = await fetch('/api/profile')
        if (!res.ok) throw new Error('Failed to load profile')
        const data = await res.json()
        setProfile(data)
      } catch (err) {
        console.error('Load profile failed:', err)
      } finally {
        setIsLoading(false)
      }
    }
    loadProfile()
  }, [])

  const gaps = profile ? getGapAnalysis(profile.topics, profile.targetScore ?? 35) : []

  const handleGenerateRecommendations = async () => {
    setIsGenerating(true)
    try {
      const res = await fetch('/api/recommend', { method: 'POST' })
      if (!res.ok) throw new Error('Failed to generate recommendations')
      const data = await res.json()
      setProblems(data.problems)
      setHasRecommendations(true)
    } catch (err) {
      console.error('Generate recommendations failed:', err)
    } finally {
      setIsGenerating(false)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('reps-session')
    localStorage.removeItem('reps-goal')
    localStorage.removeItem('reps-resume')
    router.push('/')
  }

  if (isLoading) {
    return (
      <main className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </main>
    )
  }

  if (!profile) {
    return (
      <main className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-muted-foreground">Failed to load profile. Please reconnect.</p>
      </main>
    )
  }

  return (
    <main className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card/50 backdrop-blur-sm sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <h1 className="text-xl font-bold text-foreground">reps.gg</h1>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon">
              <Settings className="h-5 w-5" />
            </Button>
            <Button variant="ghost" size="icon" onClick={handleLogout}>
              <LogOut className="h-5 w-5" />
            </Button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Stats */}
        <div className="mb-8">
          <StatsHeader
            overallScore={profile.overallScore}
            overallTier={profile.overallTier}
            totalProblemsSolved={profile.totalProblemsSolved}
            targetScore={profile.targetScore}
          />
        </div>

        <div className="grid lg:grid-cols-3 gap-8">
          {/* Left column: Topics + Recommendations */}
          <div className="lg:col-span-2 space-y-8">
            {/* Recommendations (persistent, shown above topics once generated) */}
            {hasRecommendations ? (
              <RecommendationsPanel
                problems={problems}
                onNewProblems={(newProblems) => setProblems(newProblems)}
                onProfileUpdate={refreshProfile}
              />
            ) : (
              <div className="bg-card border border-border rounded-xl p-8 text-center">
                <Sparkles className="h-8 w-8 text-primary mx-auto mb-4" />
                <h2 className="text-lg font-semibold text-foreground mb-2">Ready to practice?</h2>
                <p className="text-sm text-muted-foreground mb-6">
                  Generate personalized problem recommendations based on your mastery profile.
                </p>
                <Button
                  onClick={handleGenerateRecommendations}
                  disabled={isGenerating}
                  size="lg"
                >
                  <Sparkles className="h-4 w-4 mr-2" />
                  {isGenerating ? 'Generating...' : 'Generate Recommendations'}
                </Button>
              </div>
            )}

            {/* Topic Mastery */}
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-foreground">Topic Mastery</h2>
              <div className="grid gap-4">
                {profile.topics.map((topic) => (
                  <TopicCard key={topic.id} topic={topic} />
                ))}
              </div>
            </div>
          </div>

          {/* Right column: Gap Analysis */}
          <div className="space-y-6">
            <GapAnalysis gaps={gaps} />
          </div>
        </div>
      </div>
    </main>
  )
}
