import { CheckIcon } from '../icons'
import type { JobStatus } from '../types'

const steps = ['Transcribed', 'Draft ready', 'Under review', 'Completed']

export function JobProgress({ status }: { status: JobStatus }) {
  const active = status === 'approved' ? 4 : status === 'under_review' ? 3 : ['draft_ready'].includes(status) ? 2 : 1
  return (
    <div className="job-progress" aria-label="Job progress">
      {steps.map((step, index) => (
        <div key={step} className={index < active ? 'complete' : index === active ? 'current' : ''}>
          <span>{index < active ? <CheckIcon /> : index + 1}</span>
          <p>{step}</p>
        </div>
      ))}
    </div>
  )
}

