import type { FileType, JobStatus } from './constants';

export interface JobCreateRequest {
  youtube_url: string;
  source_lang?: string;
  target_lang?: string;
  start_time?: number; // seconds
  end_time?: number; // seconds
}

export interface JobCreateResponse {
  job_id: string;
}

export interface ErrorDetail {
  code: string;
  message: string;
  detail?: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  progress: number;
  current_step: string | null;
  error: ErrorDetail | null;
  output_files: Partial<Record<FileType, string>>;
}

export interface SSEProgressData {
  status: JobStatus;
  progress: number;
  current_step: string | null;
  message: string | null;
}

export interface SSEHandlers {
  onProgress: (data: SSEProgressData) => void;
  onComplete: (data: SSEProgressData) => void;
  onDownloadComplete?: (data: SSEProgressData) => void;
  onError: (data: { code: string; message: string; detail?: string }) => void;
}

export interface JobUploadRequest {
  file: File;
  source_lang?: string;
  target_lang?: string;
  start_time?: number;
  end_time?: number;
}

export interface SrtEntry {
  index: number;
  startTime: string; // "HH:MM:SS,mmm"
  endTime: string;
  translated: string; // first line: editable
  original: string; // second line: read-only
}
