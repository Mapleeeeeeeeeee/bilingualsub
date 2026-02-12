import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

// Mock i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-TW', changeLanguage: vi.fn() },
  }),
}));
