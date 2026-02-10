export const JobStatus = {
  PENDING: 'pending',
  DOWNLOADING: 'downloading',
  TRANSCRIBING: 'transcribing',
  TRANSLATING: 'translating',
  MERGING: 'merging',
  BURNING: 'burning',
  COMPLETED: 'completed',
  FAILED: 'failed',
} as const;
export type JobStatus = (typeof JobStatus)[keyof typeof JobStatus];

export const FileType = {
  SRT: 'srt',
  ASS: 'ass',
  VIDEO: 'video',
  AUDIO: 'audio',
  SOURCE_VIDEO: 'source_video',
} as const;
export type FileType = (typeof FileType)[keyof typeof FileType];

export const SSEEvent = {
  PROGRESS: 'progress',
  COMPLETE: 'complete',
  ERROR: 'error',
  PING: 'ping',
} as const;
export type SSEEvent = (typeof SSEEvent)[keyof typeof SSEEvent];

export const PIPELINE_STEPS = [
  JobStatus.DOWNLOADING,
  JobStatus.TRANSCRIBING,
  JobStatus.TRANSLATING,
  JobStatus.MERGING,
] as const;
