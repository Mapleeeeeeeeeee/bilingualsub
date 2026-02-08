import { useTranslation } from 'react-i18next';

export function LanguageSwitcher() {
  const { i18n } = useTranslation();

  const toggleLanguage = () => {
    const next = i18n.language === 'zh-TW' ? 'en' : 'zh-TW';
    i18n.changeLanguage(next);
  };

  return (
    <button
      onClick={toggleLanguage}
      className="px-3 py-1.5 text-sm rounded-md border border-gray-300 hover:bg-gray-100 transition-colors"
    >
      {i18n.language === 'zh-TW' ? 'EN' : '中文'}
    </button>
  );
}
