import { useTranslation } from 'react-i18next';

interface LanguageSwitcherProps {
  className?: string;
}

export function LanguageSwitcher({ className = '' }: LanguageSwitcherProps) {
  const { i18n } = useTranslation();

  const toggleLanguage = () => {
    const next = i18n.language === 'zh-TW' ? 'en' : 'zh-TW';
    i18n.changeLanguage(next);
  };

  return (
    <button
      onClick={toggleLanguage}
      className={`text-lg font-serif text-black hover:opacity-60 transition-opacity ${className}`}
    >
      {i18n.language === 'zh-TW' ? 'EN' : '中文'}
    </button>
  );
}
