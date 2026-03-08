'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Stepper } from '@/components/stepper'
import { ConnectStep } from '@/components/onboarding/connect-step'
import { ResumeStep } from '@/components/onboarding/resume-step'
import { GoalStep } from '@/components/onboarding/goal-step'
import type { Goal } from '@/lib/types'

const STEPS = ['Connect', 'Resume', 'Goal']

export default function OnboardingPage() {
  const router = useRouter()
  const [currentStep, setCurrentStep] = useState(0)
  const [isConnecting, setIsConnecting] = useState(false)
  const [credentials, setCredentials] = useState({ session: '', csrfToken: '' })
  const [resume, setResume] = useState('')
  const [selectedGoal, setSelectedGoal] = useState<Goal | null>(null)

  const handleConnect = async () => {
    setIsConnecting(true)
    try {
      const res = await fetch('/api/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials),
      })
      if (!res.ok) throw new Error('Connection failed')
      setCurrentStep(1)
    } catch (err) {
      console.error('Connect failed:', err)
    } finally {
      setIsConnecting(false)
    }
  }

  const handleDemoConnect = async () => {
    setIsConnecting(true)
    try {
      const res = await fetch('/api/connect-demo', { method: 'POST' })
      if (!res.ok) throw new Error('Demo connect failed')
      setCurrentStep(1)
    } catch (err) {
      console.error('Demo connect failed:', err)
    } finally {
      setIsConnecting(false)
    }
  }

  const [isEnriching, setIsEnriching] = useState(false)
  const [enrichResult, setEnrichResult] = useState<{ bumps: { subtopic: string; bump: number; reason: string }[] } | null>(null)
  const [resumeError, setResumeError] = useState<string | null>(null)

  const handleResumeNext = async () => {
    if (!resume.trim()) {
      setCurrentStep(2)
      return
    }
    setResumeError(null)
    setIsEnriching(true)
    try {
      const res = await fetch('http://localhost:8000/api/enrich-resume', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resume }),
      })
      if (res.ok) {
        const data = await res.json()
        if (data.error === 'not_a_resume') {
          setResumeError(data.message)
          setIsEnriching(false)
          return
        }
        setEnrichResult(data)
      }
    } catch (err) {
      console.error('Resume enrichment failed:', err)
    }
    setIsEnriching(false)
    setCurrentStep(2)
  }

  const handleResumeSkip = () => {
    setResume('')
    setCurrentStep(2)
  }

  const handleStart = async () => {
    if (selectedGoal) {
      await fetch('/api/goal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal: selectedGoal }),
      })
      router.push('/dashboard')
    }
  }

  return (
    <main className="min-h-screen bg-background flex flex-col">
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-12">
        <div className="w-full max-w-xl">
          {/* Header */}
          <div className="text-center mb-10">
            <h1 className="text-3xl font-bold text-foreground mb-2">
              reps.gg
            </h1>
            <p className="text-muted-foreground">
              Adaptive DSA learning through spaced repetition and pattern mastery
            </p>
          </div>

          {/* Stepper */}
          <div className="mb-10">
            <Stepper steps={STEPS} currentStep={currentStep} />
          </div>

          {/* Step Content */}
          <div className="bg-card border border-border rounded-xl p-8">
            {currentStep === 0 && (
              <ConnectStep
                credentials={credentials}
                setCredentials={setCredentials}
                onConnect={handleConnect}
                onDemoConnect={handleDemoConnect}
                isConnecting={isConnecting}
              />
            )}
            {currentStep === 1 && (
              <ResumeStep
                resume={resume}
                setResume={setResume}
                onNext={handleResumeNext}
                onSkip={handleResumeSkip}
                isEnriching={isEnriching}
                error={resumeError}
              />
            )}
            {currentStep === 2 && (
              <GoalStep
                selectedGoal={selectedGoal}
                setSelectedGoal={setSelectedGoal}
                onStart={handleStart}
                enrichResult={enrichResult}
              />
            )}
          </div>
        </div>
      </div>
    </main>
  )
}
