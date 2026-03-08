export type Tier = 'bronze' | 'silver' | 'gold' | 'platinum' | 'diamond'

export type Goal = 
  | 'faang'
  | 'mid-tech'
  | 'startup'
  | 'quant'
  | 'general'

export type QualityRating = 'clean' | 'hints' | 'solution' | 'struggled'

export interface Subtopic {
  id: string
  name: string
  score: number
  tier: Tier
  targetTier: Tier
  problemsSolved: number
}

export interface Topic {
  id: string
  name: string
  score: number
  tier: Tier
  subtopics: Subtopic[]
}

export interface Problem {
  id: string
  title: string
  url: string
  topic: string
  subtopic: string
  elo: number
  importance: number
  currentMastery: number
}

export interface UserProfile {
  leetcodeConnected: boolean
  resume?: string
  goal: Goal | null
  overallScore: number
  overallTier: Tier
  totalProblemsSolved: number
  topics: Topic[]
}

export const TIER_THRESHOLDS: Record<Tier, { min: number; max: number }> = {
  bronze: { min: 0, max: 19 },
  silver: { min: 20, max: 39 },
  gold: { min: 40, max: 59 },
  platinum: { min: 60, max: 79 },
  diamond: { min: 80, max: 100 }
}

export const GOAL_LABELS: Record<Goal, string> = {
  faang: 'SWE at Big Tech (FAANG)',
  'mid-tech': 'SWE at Mid-Level Tech',
  startup: 'SWE at Startup',
  quant: 'Quant / Trading Firm',
  general: 'General DSA Improvement'
}

export const GOAL_TARGET_TIERS: Record<Goal, Tier> = {
  faang: 'diamond',
  'mid-tech': 'platinum',
  startup: 'gold',
  quant: 'diamond',
  general: 'gold'
}

export function getTierFromScore(score: number): Tier {
  if (score >= 80) return 'diamond'
  if (score >= 60) return 'platinum'
  if (score >= 40) return 'gold'
  if (score >= 20) return 'silver'
  return 'bronze'
}

export function getTierColor(tier: Tier): string {
  const colors: Record<Tier, string> = {
    bronze: 'text-tier-bronze',
    silver: 'text-tier-silver',
    gold: 'text-tier-gold',
    platinum: 'text-tier-platinum',
    diamond: 'text-tier-diamond'
  }
  return colors[tier]
}

export function getTierBgColor(tier: Tier): string {
  const colors: Record<Tier, string> = {
    bronze: 'bg-tier-bronze/20',
    silver: 'bg-tier-silver/20',
    gold: 'bg-tier-gold/20',
    platinum: 'bg-tier-platinum/20',
    diamond: 'bg-tier-diamond/20'
  }
  return colors[tier]
}

export function getTierBorderColor(tier: Tier): string {
  const colors: Record<Tier, string> = {
    bronze: 'border-tier-bronze/50',
    silver: 'border-tier-silver/50',
    gold: 'border-tier-gold/50',
    platinum: 'border-tier-platinum/50',
    diamond: 'border-tier-diamond/50'
  }
  return colors[tier]
}
