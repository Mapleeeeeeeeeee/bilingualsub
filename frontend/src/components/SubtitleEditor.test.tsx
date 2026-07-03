import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { SubtitleEditor } from './SubtitleEditor';

const apiMocks = vi.hoisted(() => ({
  fetchSrtContent: vi.fn(),
  partialRetranslate: vi.fn(),
  addGlossaryEntry: vi.fn(),
}));

const i18nMocks = vi.hoisted(() => ({
  t: (key: string) => key,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: i18nMocks.t,
    i18n: { language: 'zh-TW', changeLanguage: vi.fn() },
  }),
}));

vi.mock('@/api/client', () => ({
  apiClient: {
    fetchSrtContent: apiMocks.fetchSrtContent,
    partialRetranslate: apiMocks.partialRetranslate,
    getDownloadUrl: (jobId: string, fileType: string) => `/api/jobs/${jobId}/download/${fileType}`,
    addGlossaryEntry: apiMocks.addGlossaryEntry,
  },
}));

const srtContent = `1
00:00:01,000 --> 00:00:02,000
Old translation
old source

2
00:00:03,000 --> 00:00:04,000
Untouched translation
untouched source`;

function mockTextTrack() {
  const cues: TextTrackCue[] = [];
  return {
    cues,
    mode: 'hidden',
    addCue: vi.fn((cue: TextTrackCue) => cues.push(cue)),
    removeCue: vi.fn((cue: TextTrackCue) => {
      const index = cues.indexOf(cue);
      if (index >= 0) cues.splice(index, 1);
    }),
  };
}

describe('SubtitleEditor partial retranslate preview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.fetchSrtContent.mockResolvedValue(srtContent);
    HTMLMediaElement.prototype.addTextTrack = vi.fn(() => mockTextTrack() as unknown as TextTrack);
    HTMLMediaElement.prototype.play = vi.fn();
    globalThis.VTTCue = vi.fn(function VTTCue(startTime, endTime, text) {
      return { startTime, endTime, text };
    }) as unknown as typeof VTTCue;
  });

  it('previews and applies corrected source text with translated text', async () => {
    apiMocks.partialRetranslate.mockResolvedValue({
      results: [{ index: 1, original: 'correct source', translated: 'New translation' }],
    });

    render(<SubtitleEditor jobId="job-1" onBurn={vi.fn()} isBurning={false} />);

    await screen.findByDisplayValue('Old translation');
    const retranslateButton = screen.getByRole('button', { name: 'editor.retranslate' });
    fireEvent.click(screen.getAllByTitle('editor.selectForRetranslate')[0]);
    await waitFor(() => expect(retranslateButton).toBeEnabled());
    fireEvent.click(retranslateButton);

    await screen.findByText('correct source');
    expect(screen.getAllByText('old source')).toHaveLength(2);
    expect(screen.getByText('New translation')).toBeInTheDocument();

    fireEvent.click(screen.getByText('editor.retranslatePreviewApply'));

    await waitFor(() => {
      expect(screen.getByDisplayValue('New translation')).toBeInTheDocument();
    });
    expect(screen.getByText('correct source')).toBeInTheDocument();
    expect(screen.queryByText('old source')).not.toBeInTheDocument();
  });

  it('keeps the current source text for legacy retranslate results without original', async () => {
    apiMocks.partialRetranslate.mockResolvedValue({
      results: [{ index: 1, translated: 'Legacy new translation' }],
    });

    render(<SubtitleEditor jobId="job-1" onBurn={vi.fn()} isBurning={false} />);

    await screen.findByDisplayValue('Old translation');
    const retranslateButton = screen.getByRole('button', { name: 'editor.retranslate' });
    fireEvent.click(screen.getAllByTitle('editor.selectForRetranslate')[0]);
    await waitFor(() => expect(retranslateButton).toBeEnabled());
    fireEvent.click(retranslateButton);
    await screen.findByText('Legacy new translation');

    expect(screen.getAllByText('old source')).toHaveLength(1);

    fireEvent.click(screen.getByText('editor.retranslatePreviewApply'));

    await waitFor(() => {
      expect(screen.getByDisplayValue('Legacy new translation')).toBeInTheDocument();
    });
    expect(screen.getByText('old source')).toBeInTheDocument();
  });
});
