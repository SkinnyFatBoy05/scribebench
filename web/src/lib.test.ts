import { describe, expect, it } from 'vitest'
import { humanStatus, splitTranscript } from './lib'

describe('workspace helpers', () => {
  it('numbers transcript turns and preserves ambiguous lines', () => {
    expect(splitTranscript('Clinician: Hello\nUnlabelled text')).toEqual([
      { number: 1, speaker: 'Clinician', text: 'Hello' },
      { number: 2, speaker: 'Ambiguous', text: 'Unlabelled text' },
    ])
  })

  it('formats job state for reviewers', () => {
    expect(humanStatus('under_review')).toBe('Under Review')
  })
})

