'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ChevronDown, ExternalLink, Loader2, Link2 } from 'lucide-react'

interface ConnectStepProps {
  credentials: { session: string; csrfToken: string }
  setCredentials: (creds: { session: string; csrfToken: string }) => void
  onConnect: () => void
  isConnecting: boolean
}

export function ConnectStep({ credentials, setCredentials, onConnect, isConnecting }: ConnectStepProps) {
  const [isHelpOpen, setIsHelpOpen] = useState(false)
  
  const isValid = credentials.session.length > 0 && credentials.csrfToken.length > 0

  return (
    <div className="space-y-6">
      <div className="text-center mb-6">
        <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
          <Link2 className="h-6 w-6 text-primary" />
        </div>
        <h2 className="text-xl font-semibold text-foreground mb-2">Connect LeetCode</h2>
        <p className="text-sm text-muted-foreground">
          Link your LeetCode account to sync your progress
        </p>
      </div>

      <div className="space-y-4">
        <div className="space-y-2">
          <label htmlFor="session" className="text-sm font-medium text-foreground">
            LEETCODE_SESSION
          </label>
          <Input
            id="session"
            type="password"
            placeholder="Paste your LEETCODE_SESSION cookie"
            value={credentials.session}
            onChange={(e) => setCredentials({ ...credentials, session: e.target.value })}
            className="bg-secondary border-border font-mono text-sm"
          />
        </div>

        <div className="space-y-2">
          <label htmlFor="csrf" className="text-sm font-medium text-foreground">
            csrftoken
          </label>
          <Input
            id="csrf"
            type="password"
            placeholder="Paste your csrftoken cookie"
            value={credentials.csrfToken}
            onChange={(e) => setCredentials({ ...credentials, csrfToken: e.target.value })}
            className="bg-secondary border-border font-mono text-sm"
          />
        </div>
      </div>

      <Collapsible open={isHelpOpen} onOpenChange={setIsHelpOpen}>
        <CollapsibleTrigger asChild>
          <button className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
            <ChevronDown className={`h-4 w-4 transition-transform ${isHelpOpen ? 'rotate-180' : ''}`} />
            How to get these cookies
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent className="mt-3">
          <div className="bg-secondary/50 rounded-lg p-4 text-sm text-muted-foreground space-y-2">
            <p className="flex items-center gap-2">
              <span className="text-primary font-semibold">1.</span>
              Open{' '}
              <a 
                href="https://leetcode.com" 
                target="_blank" 
                rel="noopener noreferrer"
                className="text-primary hover:underline inline-flex items-center gap-1"
              >
                leetcode.com <ExternalLink className="h-3 w-3" />
              </a>
              {' '}and log in
            </p>
            <p className="flex items-center gap-2">
              <span className="text-primary font-semibold">2.</span>
              Open DevTools (F12 or right-click → Inspect)
            </p>
            <p className="flex items-center gap-2">
              <span className="text-primary font-semibold">3.</span>
              Go to Application → Cookies → leetcode.com
            </p>
            <p className="flex items-center gap-2">
              <span className="text-primary font-semibold">4.</span>
              Copy LEETCODE_SESSION and csrftoken values
            </p>
          </div>
        </CollapsibleContent>
      </Collapsible>

      <Button 
        onClick={onConnect} 
        disabled={!isValid || isConnecting}
        className="w-full"
        size="lg"
      >
        {isConnecting ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
            Connecting...
          </>
        ) : (
          'Connect'
        )}
      </Button>
    </div>
  )
}
