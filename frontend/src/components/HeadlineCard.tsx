import React from 'react';
import { Box, HStack, Image, Text, Link } from '@chakra-ui/react';
import { CHANNEL_META, DEFAULT_CHANNEL_COLOR } from '../config/sources';
import { useSpeech } from '../contexts/SpeechContext';
import { useWordDefinition } from '../hooks/useWordDefinition';
import WordSheet from './WordSheet';

// Noto Serif SC for Chinese editorial headlines — Bilingual Editorial Asia design
const ZH_SERIF = `'Noto Serif SC', 'Songti SC', 'STSong', 'SimSun', Georgia, serif`;

function IconSpeaker() {
  return (
    <svg width="13" height="13" viewBox="0 0 13 13" fill="currentColor" aria-hidden>
      <path d="M1.5 4.5h2.25L7 1.5v10l-3.25-3H1.5v-4z" />
      <path d="M9 3.5a4 4 0 0 1 0 6" stroke="currentColor" strokeWidth="1.2"
        strokeLinecap="round" fill="none" />
      <path d="M10.5 1.5a6.5 6.5 0 0 1 0 10" stroke="currentColor" strokeWidth="1.2"
        strokeLinecap="round" fill="none" />
    </svg>
  );
}

function IconStop() {
  return (
    <svg width="13" height="13" viewBox="0 0 13 13" fill="currentColor" aria-hidden>
      <rect x="2.5" y="2.5" width="8" height="8" rx="1.5" />
    </svg>
  );
}

export default function HeadlineCard({ headline }: { headline: any }) {
  const articleUrl = headline.source_url || `https://www.youtube.com/watch?v=${headline.id}`;
  const d = new Date(headline.published_at);
  const dateStr = d.toLocaleDateString('en-MY', { day: 'numeric', month: 'short' });
  const timeStr = d.toLocaleTimeString('en-MY', { hour: 'numeric', minute: '2-digit', hour12: true });

  const { playingId, speak }                          = useSpeech();
  const { definition, loading, activeWord, lookup, dismiss } = useWordDefinition();
  const isPlaying    = playingId === headline.id;
  const channelColor = CHANNEL_META[headline.channel]?.color ?? DEFAULT_CHANNEL_COLOR;

  // Split English title into tokens preserving whitespace between words
  const tokens = headline.title_en
    ? headline.title_en.split(/(\s+)/)
    : [];

  return (
    <>
      <HStack
        align="start"
        spacing={3}
        p={3}
        bg="white"
        borderRadius="sm"
        boxShadow="xs"
        _hover={{ boxShadow: 'sm' }}
        transition="box-shadow 0.15s"
      >
        {/* Thumbnail */}
        <Link href={articleUrl} isExternal flexShrink={0}>
          <Image
            src={headline.thumbnail_url}
            alt={headline.title_zh}
            borderRadius="sm"
            w="90px"
            h="51px"
            objectFit="cover"
            bg="brand.rule"
          />
        </Link>

        {/* Text block */}
        <Box flex={1} minW={0}>

          {/* Chinese headline — serif, dominant */}
          <Link href={articleUrl} isExternal _hover={{ textDecoration: 'none' }}>
            <Text
              fontFamily={ZH_SERIF}
              fontSize="sm"
              fontWeight="700"
              lineHeight="1.4"
              color="brand.ink"
              _hover={{ color: 'brand.red' }}
              transition="color 0.1s"
            >
              {headline.title_zh}
            </Text>
          </Link>

          {/* English translation — tappable words + speaker button */}
          {headline.title_en && (
            <HStack mt={1} spacing={1.5} align="flex-start">
              {/* Inline tappable word tokens */}
              <Box
                fontFamily="'Inter', sans-serif"
                fontSize="xs"
                fontWeight="400"
                color="#666666"
                lineHeight="1.5"
                flex={1}
              >
                {tokens.map((token: string, i: number) => {
                  // Whitespace tokens — render as-is
                  if (/^\s+$/.test(token)) return <span key={i}>{token}</span>;

                  const clean = token.replace(/[^a-zA-Z'-]/g, '').toLowerCase();
                  const isActive = clean === activeWord;

                  return (
                    <Box
                      key={i}
                      as="span"
                      cursor={clean.length >= 2 ? 'pointer' : 'text'}
                      onClick={() => clean.length >= 2 && lookup(token)}
                      borderBottom={isActive ? '1px solid' : 'none'}
                      borderColor="brand.red"
                      color={isActive ? 'brand.ink' : 'inherit'}
                      _hover={clean.length >= 2 ? { color: 'brand.ink' } : {}}
                      transition="color 0.1s"
                      userSelect="none"
                    >
                      {token}
                    </Box>
                  );
                })}
              </Box>

              {/* Read-aloud button */}
              <Box
                as="button"
                onClick={() => speak(headline.id, headline.title_en)}
                flexShrink={0}
                mt="2px"
                color={isPlaying ? 'brand.red' : 'brand.rule'}
                _hover={{ color: isPlaying ? '#c0392b' : 'brand.muted' }}
                transition="color 0.15s"
                aria-label={isPlaying ? 'Stop' : 'Read aloud'}
                title={isPlaying ? 'Stop' : 'Read aloud'}
                lineHeight="1"
              >
                {isPlaying ? <IconStop /> : <IconSpeaker />}
              </Box>
            </HStack>
          )}

          {/* Meta line — source · date · time */}
          <HStack mt={1.5} spacing={1} fontSize="2xs" color="brand.muted" letterSpacing="0.02em">
            <Text fontWeight="600" color={channelColor}>{headline.channel}</Text>
            <Text color="brand.rule">·</Text>
            <Text>{dateStr}</Text>
            <Text color="brand.rule">·</Text>
            <Text>{timeStr}</Text>
          </HStack>
        </Box>
      </HStack>

      {/* Word definition sheet — shown when a word is tapped */}
      {activeWord && (
        <WordSheet
          word={activeWord}
          definition={definition}
          loading={loading}
          onSpeak={speak}
          onDismiss={dismiss}
        />
      )}
    </>
  );
}
