import type { SrtEntry } from '../types';

/**
 * Parse raw SRT content into structured entries.
 * Malformed blocks are silently skipped.
 */
export function parseSrt(raw: string): SrtEntry[] {
  const entries: SrtEntry[] = [];
  const blocks = raw.trim().split(/\n\s*\n/);

  for (const block of blocks) {
    const lines = block.trim().split('\n');
    if (lines.length < 3) continue;

    const index = parseInt(lines[0], 10);
    if (isNaN(index)) continue;

    const timingMatch = lines[1].match(
      /^(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})$/
    );
    if (!timingMatch) continue;

    const textLines = lines.slice(2).join('\n');
    const firstNewline = textLines.indexOf('\n');

    let translated: string;
    let original: string;
    if (firstNewline === -1) {
      translated = textLines;
      original = '';
    } else {
      translated = textLines.substring(0, firstNewline);
      original = textLines.substring(firstNewline + 1);
    }

    entries.push({
      index,
      startTime: timingMatch[1],
      endTime: timingMatch[2],
      translated,
      original,
    });
  }

  return entries;
}

/**
 * Serialize SRT entries back to standard SRT format.
 */
export function serializeSrt(entries: SrtEntry[]): string {
  return entries
    .map(entry => {
      const text = entry.original ? `${entry.translated}\n${entry.original}` : entry.translated;
      return `${entry.index}\n${entry.startTime} --> ${entry.endTime}\n${text}`;
    })
    .join('\n\n');
}

export function srtTimeToSeconds(srtTime: string): number {
  const [hms, ms] = srtTime.split(',');
  const [h, m, s] = hms.split(':').map(Number);
  return h * 3600 + m * 60 + s + Number(ms) / 1000;
}
