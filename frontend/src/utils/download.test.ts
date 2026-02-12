import { triggerDownload } from './download';

describe('triggerDownload', () => {
  it('creates an anchor element and clicks it', () => {
    const clickSpy = vi.fn();
    vi.spyOn(document, 'createElement').mockReturnValue({
      href: '',
      download: '',
      click: clickSpy,
    } as unknown as HTMLAnchorElement);

    triggerDownload('https://example.com/file.srt');

    const el = document.createElement('a') as unknown as { href: string; download: string };
    expect(el.href).toBe('https://example.com/file.srt');
    expect(el.download).toBe('');
    expect(clickSpy).toHaveBeenCalled();

    vi.restoreAllMocks();
  });

  it('sets download attribute when filename is provided', () => {
    const mockAnchor = { href: '', download: '', click: vi.fn() };
    vi.spyOn(document, 'createElement').mockReturnValue(mockAnchor as unknown as HTMLAnchorElement);

    triggerDownload('https://example.com/file.srt', 'my-file.srt');

    expect(mockAnchor.download).toBe('my-file.srt');
    expect(mockAnchor.click).toHaveBeenCalled();

    vi.restoreAllMocks();
  });
});
