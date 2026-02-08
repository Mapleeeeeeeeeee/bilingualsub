import { FileType } from '../constants';
import type { JobCreateRequest, JobCreateResponse, JobStatusResponse, SSEHandlers } from '../types';
import { ApiError } from './errors';

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = import.meta.env.VITE_API_URL || '') {
    this.baseUrl = baseUrl;
  }

  async createJob(request: JobCreateRequest): Promise<JobCreateResponse> {
    const response = await fetch(`${this.baseUrl}/api/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      throw await ApiError.fromResponse(response);
    }
    return response.json();
  }

  async getJobStatus(jobId: string): Promise<JobStatusResponse> {
    const response = await fetch(`${this.baseUrl}/api/jobs/${jobId}`);
    if (!response.ok) {
      throw await ApiError.fromResponse(response);
    }
    return response.json();
  }

  connectSSE(jobId: string, handlers: SSEHandlers): EventSource {
    const es = new EventSource(`${this.baseUrl}/api/jobs/${jobId}/events`);

    es.addEventListener('progress', event => {
      const data = JSON.parse(event.data);
      handlers.onProgress(data);
    });

    es.addEventListener('complete', event => {
      const data = JSON.parse(event.data);
      handlers.onComplete(data);
      es.close();
    });

    es.addEventListener('error', event => {
      // Check if this is a server-sent error event with data
      if (event instanceof MessageEvent && event.data) {
        const data = JSON.parse(event.data);
        handlers.onError(data);
      } else {
        handlers.onError({
          code: 'connection_error',
          message: 'SSE connection lost',
        });
      }
      es.close();
    });

    return es;
  }

  async fetchSrtContent(jobId: string): Promise<string> {
    const url = this.getDownloadUrl(jobId, FileType.SRT);
    const response = await fetch(url);
    if (!response.ok) {
      throw await ApiError.fromResponse(response);
    }
    return response.text();
  }

  getDownloadUrl(jobId: string, fileType: FileType): string {
    return `${this.baseUrl}/api/jobs/${jobId}/download/${fileType}`;
  }
}

export const apiClient = new ApiClient();
