import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Pencil, Trash2, Check, X } from 'lucide-react';
import type { GlossaryEntry } from '@/types';
import { apiClient } from '@/api/client';

export function GlossaryPanel() {
  const { t } = useTranslation();
  const [entries, setEntries] = useState<GlossaryEntry[]>([]);
  const [isAdding, setIsAdding] = useState(false);
  const [editingSource, setEditingSource] = useState<string | null>(null);
  const [newSource, setNewSource] = useState('');
  const [newTarget, setNewTarget] = useState('');
  const [editTarget, setEditTarget] = useState('');
  const [error, setError] = useState<string | null>(null);

  const loadEntries = useCallback(async () => {
    try {
      const data = await apiClient.getGlossary();
      setEntries(data);
    } catch {
      setError('Failed to load glossary');
    }
  }, []);

  useEffect(() => {
    loadEntries();
  }, [loadEntries]);

  const handleAdd = async () => {
    if (!newSource.trim()) return;
    try {
      setError(null);
      const newEntry = await apiClient.addGlossaryEntry(
        newSource.trim(),
        newTarget.trim() || newSource.trim()
      );
      setEntries(prev =>
        [...prev, newEntry].sort((a, b) =>
          a.source.toLowerCase().localeCompare(b.source.toLowerCase())
        )
      );
      setNewSource('');
      setNewTarget('');
      setIsAdding(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add term');
    }
  };

  const handleStartEdit = (entry: GlossaryEntry) => {
    setEditingSource(entry.source);
    setEditTarget(entry.target);
    setIsAdding(false);
  };

  const handleUpdate = async (source: string) => {
    try {
      setError(null);
      await apiClient.updateGlossaryEntry(source, editTarget.trim());
      setEntries(prev =>
        prev.map(e => (e.source === source ? { ...e, target: editTarget.trim() } : e))
      );
      setEditingSource(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update term');
    }
  };

  const handleCancelEdit = () => {
    setEditingSource(null);
    setEditTarget('');
  };

  const handleDelete = async (source: string) => {
    try {
      setError(null);
      await apiClient.deleteGlossaryEntry(source);
      setEntries(prev => prev.filter(e => e.source !== source));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete term');
    }
  };

  const handleCancelAdd = () => {
    setIsAdding(false);
    setNewSource('');
    setNewTarget('');
    setError(null);
  };

  return (
    <div className="border border-gray-200 rounded-2xl overflow-hidden">
      {/* Panel header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 bg-gray-50">
        <p className="text-xs uppercase tracking-widest text-gray-500 font-semibold">
          {t('glossary.title')}
        </p>
        <button
          onClick={() => {
            setIsAdding(true);
            setEditingSource(null);
            setError(null);
          }}
          className="flex items-center gap-1.5 text-xs uppercase tracking-widest text-gray-500 hover:text-black transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          {t('glossary.add')}
        </button>
      </div>

      {/* Error message */}
      {error && (
        <div className="px-5 py-2 bg-red-50 border-b border-red-100">
          <p className="text-xs text-red-500">{error}</p>
        </div>
      )}

      {/* Add new entry form */}
      {isAdding && (
        <div className="px-5 py-4 border-b border-gray-100 bg-blue-50/30">
          <div className="flex flex-col sm:flex-row gap-2">
            <input
              type="text"
              value={newSource}
              onChange={e => setNewSource(e.target.value)}
              placeholder={t('glossary.sourcePlaceholder')}
              className="flex-1 text-sm border border-gray-300 rounded px-3 py-2 focus:outline-none focus:border-black"
              autoFocus
              onKeyDown={e => {
                if (e.key === 'Enter') handleAdd();
                if (e.key === 'Escape') handleCancelAdd();
              }}
            />
            <span className="hidden sm:flex items-center text-gray-400">→</span>
            <input
              type="text"
              value={newTarget}
              onChange={e => setNewTarget(e.target.value)}
              placeholder={t('glossary.targetPlaceholder')}
              className="flex-1 text-sm border border-gray-300 rounded px-3 py-2 focus:outline-none focus:border-black"
              onKeyDown={e => {
                if (e.key === 'Enter') handleAdd();
                if (e.key === 'Escape') handleCancelAdd();
              }}
            />
            <div className="flex gap-2">
              <button
                onClick={handleAdd}
                disabled={!newSource.trim()}
                className="flex items-center gap-1 text-xs border border-black px-3 py-2 rounded hover:bg-black hover:text-white disabled:opacity-30 transition-colors"
              >
                <Check className="h-3.5 w-3.5" />
                {t('glossary.save')}
              </button>
              <button
                onClick={handleCancelAdd}
                className="flex items-center gap-1 text-xs text-gray-500 hover:text-black px-2 py-2 transition-colors"
              >
                <X className="h-3.5 w-3.5" />
                {t('glossary.cancel')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Entries list */}
      <div className="divide-y divide-gray-100">
        {entries.length === 0 && !isAdding ? (
          <p className="text-sm text-gray-400 text-center py-8 px-5">{t('glossary.empty')}</p>
        ) : (
          entries.map(entry => (
            <div
              key={entry.source}
              className="flex items-center gap-3 px-5 py-3 hover:bg-gray-50 group transition-colors"
            >
              {editingSource === entry.source ? (
                /* Inline edit row */
                <>
                  <span className="flex-1 text-sm font-mono text-gray-700">{entry.source}</span>
                  <span className="text-gray-400 text-xs">→</span>
                  <input
                    type="text"
                    value={editTarget}
                    onChange={e => setEditTarget(e.target.value)}
                    className="flex-1 text-sm border border-gray-300 rounded px-2 py-1 focus:outline-none focus:border-black"
                    autoFocus
                    onKeyDown={e => {
                      if (e.key === 'Enter') handleUpdate(entry.source);
                      if (e.key === 'Escape') handleCancelEdit();
                    }}
                  />
                  <div className="flex gap-1 shrink-0">
                    <button
                      onClick={() => handleUpdate(entry.source)}
                      className="p-1.5 text-gray-500 hover:text-black transition-colors"
                      title={t('glossary.save')}
                    >
                      <Check className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={handleCancelEdit}
                      className="p-1.5 text-gray-400 hover:text-black transition-colors"
                      title={t('glossary.cancel')}
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </>
              ) : (
                /* Display row */
                <>
                  <span className="flex-1 text-sm font-mono text-gray-700">{entry.source}</span>
                  <span className="text-gray-400 text-xs">→</span>
                  <span className="flex-1 text-sm text-gray-600">{entry.target}</span>
                  <div className="flex gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() => handleStartEdit(entry)}
                      className="p-1.5 text-gray-400 hover:text-black transition-colors"
                      title={t('glossary.edit')}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => {
                        if (window.confirm(t('glossary.confirmDelete'))) {
                          handleDelete(entry.source);
                        }
                      }}
                      className="p-1.5 text-gray-400 hover:text-red-500 transition-colors"
                      title={t('glossary.delete')}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
