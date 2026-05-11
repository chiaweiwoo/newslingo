import { useState } from 'react';

export interface Definition {
  word:      string;
  phonetic:  string | null;
  partOfSpeech: string | null;
  definition: string;
  example:   string | null;
}

const cache = new Map<string, Definition | null>();

const SKIP_WORDS = new Set([
  'a','an','the','and','or','but','in','on','at','to','for',
  'of','with','by','from','as','is','it','its','was','are',
  'be','been','has','had','have','not','this','that','his',
  'her','their','our','your','my','we','he','she','they',
  'i','up','out','into','over','after','before','about',
  'will','would','could','should','may','might','than','then',
]);

export function useWordDefinition() {
  const [definition, setDefinition] = useState<Definition | null>(null);
  const [loading, setLoading]       = useState(false);
  const [activeWord, setActiveWord] = useState<string | null>(null);

  const lookup = async (raw: string) => {
    // Strip punctuation
    const word = raw.replace(/[^a-zA-Z'-]/g, '').toLowerCase();

    // Dismiss if tapping same word or skippable
    if (word === activeWord) { setActiveWord(null); setDefinition(null); return; }
    if (!word || word.length < 2 || SKIP_WORDS.has(word)) return;

    setActiveWord(word);
    setDefinition(null);

    // Return cached result immediately
    if (cache.has(word)) {
      setDefinition(cache.get(word) ?? null);
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(
        `https://api.dictionaryapi.dev/api/v2/entries/en/${encodeURIComponent(word)}`
      );
      if (!res.ok) { cache.set(word, null); setDefinition(null); return; }

      const data = await res.json();
      const entry   = data[0];
      const meaning = entry?.meanings?.[0];
      const def     = meaning?.definitions?.[0];

      const result: Definition = {
        word:         entry?.word ?? word,
        phonetic:     entry?.phonetic ?? entry?.phonetics?.find((p: any) => p.text)?.text ?? null,
        partOfSpeech: meaning?.partOfSpeech ?? null,
        definition:   def?.definition ?? '',
        example:      def?.example ?? null,
      };

      cache.set(word, result);
      setDefinition(result);
    } catch {
      cache.set(word, null);
      setDefinition(null);
    } finally {
      setLoading(false);
    }
  };

  const dismiss = () => { setActiveWord(null); setDefinition(null); };

  return { definition, loading, activeWord, lookup, dismiss };
}
