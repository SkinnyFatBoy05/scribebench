import type { JobStatus } from './types'

export function splitTranscript(transcript: string) {
  return transcript.split('\n').map((raw, index) => {
    const separator = raw.indexOf(':')
    if (separator < 0) return { number: index + 1, speaker: 'Ambiguous', text: raw.trim() }
    return {
      number: index + 1,
      speaker: raw.slice(0, separator).trim(),
      text: raw.slice(separator + 1).trim(),
    }
  }).filter((line) => line.text.trim().length > 0)
}

export function humanStatus(status: JobStatus) {
  return status.replace('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function shortId(id: string) {
  return id.slice(0, 8).toUpperCase()
}

export function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
}
