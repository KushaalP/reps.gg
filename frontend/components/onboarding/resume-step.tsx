'use client'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { FileText, Loader2 } from 'lucide-react'

interface ResumeStepProps {
  resume: string
  setResume: (resume: string) => void
  onNext: () => void
  onSkip: () => void
  isEnriching?: boolean
  error?: string | null
}

export function ResumeStep({ resume, setResume, onNext, onSkip, isEnriching, error }: ResumeStepProps) {
  return (
    <div className="space-y-6">
      <div className="text-center mb-6">
        <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
          <FileText className="h-6 w-6 text-primary" />
        </div>
        <h2 className="text-xl font-semibold text-foreground mb-2">Add Your Resume</h2>
        <p className="text-sm text-muted-foreground">
          Optional: Paste your resume to enrich your initial mastery profile
        </p>
      </div>

      <div className="space-y-2">
        <label htmlFor="resume" className="text-sm font-medium text-foreground">
          Resume Content
        </label>
        <Textarea
          id="resume"
          placeholder="Paste your resume text here (optional)..."
          value={resume}
          onChange={(e) => setResume(e.target.value)}
          className="min-h-[200px] bg-secondary border-border text-sm resize-none"
          disabled={isEnriching}
        />
        <p className="text-xs text-muted-foreground">
          We&apos;ll analyze your coursework, projects, and experience to give you a head start on relevant topics
        </p>
        {error && (
          <p className="text-sm text-[#ef4444] font-medium">{error}</p>
        )}
      </div>

      <div className="flex gap-3">
        <Button
          variant="outline"
          onClick={onSkip}
          className="flex-1"
          size="lg"
          disabled={isEnriching}
        >
          Skip
        </Button>
        <Button
          onClick={onNext}
          className="flex-1"
          size="lg"
          disabled={isEnriching}
        >
          {isEnriching ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Analyzing Resume...
            </>
          ) : (
            'Next'
          )}
        </Button>
      </div>
    </div>
  )
}
