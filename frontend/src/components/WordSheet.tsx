import React from 'react';
import {
  Box, Divider, HStack, Spinner, Text, VStack,
} from '@chakra-ui/react';
import { Definition } from '../hooks/useWordDefinition';

interface Props {
  word:       string;
  definition: Definition | null;
  loading:    boolean;
  onSpeak:    (id: string, text: string) => void;
  onDismiss:  () => void;
}

function IconSpeaker() {
  return (
    <svg width="13" height="13" viewBox="0 0 13 13" fill="currentColor" aria-hidden>
      <path d="M1.5 4.5h2.25L7 1.5v10l-3.25-3H1.5v-4z" />
      <path d="M9 3.5a4 4 0 0 1 0 6" stroke="currentColor" strokeWidth="1.2"
        strokeLinecap="round" fill="none" />
    </svg>
  );
}

export default function WordSheet({ word, definition, loading, onSpeak, onDismiss }: Props) {
  return (
    <>
      {/* Backdrop */}
      <Box
        position="fixed" inset={0} zIndex={90}
        onClick={onDismiss}
      />

      {/* Sheet */}
      <Box
        position="fixed" bottom={0} left={0} right={0} zIndex={91}
        bg="white"
        borderTop="3px solid" borderColor="brand.red"
        borderTopRadius="lg"
        px={4} pt={4} pb={8}
        maxW="600px" mx="auto"
        boxShadow="0 -4px 24px rgba(0,0,0,0.10)"
      >
        {loading ? (
          <HStack justify="center" py={4}>
            <Spinner size="sm" color="brand.red" />
            <Text fontSize="xs" color="brand.muted">Looking up "{word}"…</Text>
          </HStack>
        ) : !definition ? (
          <VStack spacing={1} py={3} align="flex-start">
            <Text fontSize="sm" fontWeight="700" color="brand.ink">{word}</Text>
            <Text fontSize="xs" color="brand.muted">No definition found.</Text>
          </VStack>
        ) : (
          <VStack spacing={3} align="stretch">

            {/* Word + phonetic + speak */}
            <HStack justify="space-between" align="flex-start">
              <VStack spacing={0} align="flex-start">
                <Text
                  fontSize="md" fontWeight="700" color="brand.ink"
                  fontFamily="'Inter', sans-serif"
                >
                  {definition.word}
                </Text>
                {definition.phonetic && (
                  <Text fontSize="xs" color="brand.muted" fontStyle="italic">
                    {definition.phonetic}
                  </Text>
                )}
              </VStack>
              <Box
                as="button"
                onClick={() => onSpeak(`word-${definition.word}`, definition.word)}
                color="brand.muted"
                _hover={{ color: 'brand.ink' }}
                transition="color 0.15s"
                mt="2px"
                aria-label="Pronounce"
              >
                <IconSpeaker />
              </Box>
            </HStack>

            <Divider borderColor="brand.rule" />

            {/* Part of speech + definition */}
            <VStack spacing={1.5} align="flex-start">
              {definition.partOfSpeech && (
                <Text fontSize="2xs" fontWeight="700" color="brand.red"
                  textTransform="uppercase" letterSpacing="wider">
                  {definition.partOfSpeech}
                </Text>
              )}
              <Text fontSize="sm" color="brand.ink" lineHeight="1.6">
                {definition.definition}
              </Text>
              {definition.example && (
                <Text fontSize="xs" color="brand.muted" lineHeight="1.6" fontStyle="italic">
                  "{definition.example}"
                </Text>
              )}
            </VStack>

          </VStack>
        )}
      </Box>
    </>
  );
}
