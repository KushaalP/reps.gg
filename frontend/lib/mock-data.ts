// Placeholder — all real data comes from API endpoints.
// This file exists only so imports don't break during development.

import type { Topic, Problem, UserProfile, Tier } from './types'

export const mockTopics: Topic[] = []
export const mockProblems: Problem[] = []

export const mockUserProfile: UserProfile = {
  leetcodeConnected: false,
  resume: '',
  goal: null,
  overallScore: 0,
  overallTier: 'bronze',
  totalProblemsSolved: 0,
  topics: []
}

export function getGapAnalysis(
  topics: Topic[],
  targetScore: number
): { subtopic: string; topic: string; gap: number; currentTier: Tier }[] {
  const gaps: { subtopic: string; topic: string; gap: number; currentTier: Tier }[] = []
  for (const topic of topics) {
    for (const subtopic of topic.subtopics) {
      const gap = targetScore - subtopic.score
      if (gap > 0) {
        gaps.push({
          subtopic: subtopic.name,
          topic: topic.name,
          gap,
          currentTier: subtopic.tier,
        })
      }
    }
  }
  return gaps.sort((a, b) => b.gap - a.gap)
}
