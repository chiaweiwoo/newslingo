import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

interface SpeechContextValue {
  playingId: string | null;
  speak:     (id: string, text: string) => void;
}

const SpeechContext = createContext<SpeechContextValue>({
  playingId: null,
  speak:     () => {},
});

export function SpeechProvider({ children }: { children: React.ReactNode }) {
  const [playingId, setPlayingId] = useState<string | null>(null);

  // Ref so the speak callback stays stable (no playingId dep)
  const playingIdRef = useRef<string | null>(null);

  const speak = useCallback((id: string, text: string) => {
    if (!window.speechSynthesis) return;

    // Tap same card → stop
    if (playingIdRef.current === id) {
      window.speechSynthesis.cancel();
      playingIdRef.current = null;
      setPlayingId(null);
      return;
    }

    // Stop whatever is currently playing
    window.speechSynthesis.cancel();

    const utter = new SpeechSynthesisUtterance(text);
    utter.lang  = 'en-US';
    utter.rate  = 0.9;   // slightly slower — easier to follow when learning
    utter.pitch = 1;

    const done = () => {
      playingIdRef.current = null;
      setPlayingId(null);
    };
    utter.onend   = done;
    utter.onerror = done;

    playingIdRef.current = id;
    setPlayingId(id);
    window.speechSynthesis.speak(utter);
  }, []);

  // Cancel on unmount
  useEffect(() => () => { window.speechSynthesis?.cancel(); }, []);

  return (
    <SpeechContext.Provider value={{ playingId, speak }}>
      {children}
    </SpeechContext.Provider>
  );
}

export function useSpeech() {
  return useContext(SpeechContext);
}
