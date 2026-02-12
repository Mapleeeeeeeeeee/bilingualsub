import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DownloadLinks } from './DownloadLinks';

// Mock apiClient
vi.mock('../api/client', () => ({
  apiClient: {
    getDownloadUrl: (jobId: string, fileType: string) => `/api/jobs/${jobId}/download/${fileType}`,
  },
}));

// Mock triggerDownload
vi.mock('../utils/download', () => ({
  triggerDownload: vi.fn(),
}));

describe('DownloadLinks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders all 3 download options by default', () => {
    render(<DownloadLinks jobId="test-123" />);
    expect(screen.getByText('download.srt')).toBeInTheDocument();
    expect(screen.getByText('download.ass')).toBeInTheDocument();
    expect(screen.getByText('download.video')).toBeInTheDocument();
  });

  it('hides video option when showVideo is false', () => {
    render(<DownloadLinks jobId="test-123" showVideo={false} />);
    expect(screen.getByText('download.srt')).toBeInTheDocument();
    expect(screen.getByText('download.ass')).toBeInTheDocument();
    expect(screen.queryByText('download.video')).not.toBeInTheDocument();
  });

  it('shows all options when showVideo is true', () => {
    render(<DownloadLinks jobId="test-123" showVideo={true} />);
    expect(screen.getByText('download.srt')).toBeInTheDocument();
    expect(screen.getByText('download.ass')).toBeInTheDocument();
    expect(screen.getByText('download.video')).toBeInTheDocument();
  });

  it('shows disclaimer dialog on link click and triggers download on confirm', async () => {
    const { triggerDownload } = await import('../utils/download');
    const user = userEvent.setup();

    render(<DownloadLinks jobId="test-123" />);

    // Click a download link
    await user.click(screen.getByText('download.srt'));

    // Disclaimer dialog should appear
    expect(screen.getByText('disclaimer.title')).toBeInTheDocument();

    // Click confirm
    await user.click(screen.getByText('disclaimer.confirm'));

    // triggerDownload should have been called
    expect(triggerDownload).toHaveBeenCalledWith('/api/jobs/test-123/download/srt');
  });

  it('hides disclaimer dialog on cancel without downloading', async () => {
    const { triggerDownload } = await import('../utils/download');
    const user = userEvent.setup();

    render(<DownloadLinks jobId="test-123" />);

    // Click a download link
    await user.click(screen.getByText('download.srt'));

    // Disclaimer should be visible
    expect(screen.getByText('disclaimer.title')).toBeInTheDocument();

    // Click cancel
    await user.click(screen.getByText('disclaimer.cancel'));

    // Dialog should close, no download triggered
    expect(screen.queryByText('disclaimer.title')).not.toBeInTheDocument();
    expect(triggerDownload).not.toHaveBeenCalled();
  });

  it('sets correct href on download links', () => {
    render(<DownloadLinks jobId="abc-456" />);
    const srtLink = screen.getByText('download.srt').closest('a');
    expect(srtLink).toHaveAttribute('href', '/api/jobs/abc-456/download/srt');
  });
});
