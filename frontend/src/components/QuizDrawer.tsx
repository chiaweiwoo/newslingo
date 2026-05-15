/**
 * Translation Quiz
 *
 * Shows a Chinese headline from the past 3 days.
 * User types an English translation, then gets scored using
 * @huggingface/transformers sentence similarity (Xenova/all-MiniLM-L6-v2).
 *
 * The model (~23 MB) is loaded lazily on first submit and cached by the browser.
 */

import React, { useEffect, useRef, useState } from 'react';
import {
  Box, Center, Divider, Drawer, DrawerBody, DrawerCloseButton,
  DrawerContent, DrawerHeader, DrawerOverlay, Flex, Spinner,
  Text, Textarea, VStack, HStack,
} from '@chakra-ui/react';
import { useQuery } from '@tanstack/react-query';
import { createClient } from '@supabase/supabase-js';
import { computeScore, warmUpModel } from '../hooks/useSemanticScore';

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);

// ── Types ─────────────────────────────────────────────────────────────────────

interface Headline {
  id:           string;
  title_zh:     string;
  title_en:     string;
  category:     string;
  published_at: string;
  channel:      string;
  thumbnail_url?: string;
}

// ── Score helpers ─────────────────────────────────────────────────────────────

function scoreBand(score: number): { label: string; color: string; emoji: string } {
  if (score >= 85) return { label: 'Excellent',       color: '#2e7d32', emoji: '🎯' };
  if (score >= 65) return { label: 'Good',            color: '#1565c0', emoji: '👍' };
  if (score >= 45) return { label: 'Partially right', color: '#e65100', emoji: '🤔' };
  return              { label: 'Keep practising',  color: '#b71c1c', emoji: '📚' };
}

function regionIcon(category: string): string {
  if (category === 'Singapore') return '🇸🇬';
  if (category === 'Malaysia')  return '🇲🇾';
  return '🌍';
}

function channelLabel(channel: string): string {
  if (channel === 'zaobao') return '联合早报';
  if (channel === 'astro')  return 'Astro 本地圈';
  return channel;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-MY', {
    day: 'numeric', month: 'short',
  });
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  isOpen:  boolean;
  onClose: () => void;
}

export default function QuizDrawer({ isOpen, onClose }: Props) {
  const [seenIds, setSeenIds]   = useState<Set<string>>(new Set());
  const [current, setCurrent]   = useState<Headline | null>(null);
  const [userInput, setUserInput] = useState('');
  const [score, setScore]       = useState<number | null>(null);
  const [phase, setPhase]       = useState<'input' | 'scoring' | 'result'>('input');
  const textareaRef             = useRef<HTMLTextAreaElement>(null);

  // ── Fetch headline pool (past 3 days) ──────────────────────────────────────
  const cutoff = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString();

  const { data: pool = [], isLoading: poolLoading } = useQuery({
    queryKey: ['quiz-pool'],
    queryFn: async (): Promise<Headline[]> => {
      const { data } = await supabase
        .from('headlines')
        .select('id, title_zh, title_en, category, published_at, channel, thumbnail_url')
        .gte('published_at', cutoff)
        .not('title_en', 'is', null)
        .not('title_zh', 'is', null)
        .order('published_at', { ascending: false })
        .limit(100);
      return (data as Headline[]) ?? [];
    },
    enabled: isOpen,
    staleTime: 5 * 60 * 1000,
  });

  // ── Pick first headline once pool loads ───────────────────────────────────
  useEffect(() => {
    if (pool.length > 0 && !current) {
      pickNext(pool, new Set());
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pool]);

  // ── Warm up model when drawer opens ──────────────────────────────────────
  useEffect(() => {
    if (isOpen) warmUpModel();
  }, [isOpen]);

  // ── Reset on close ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!isOpen) {
      setSeenIds(new Set());
      setCurrent(null);
      setUserInput('');
      setScore(null);
      setPhase('input');
    }
  }, [isOpen]);

  function pickNext(src: Headline[], seen: Set<string>) {
    const unseen = src.filter(h => !seen.has(h.id));
    const pool2  = unseen.length > 0 ? unseen : src; // wrap around when exhausted
    const next   = pool2[Math.floor(Math.random() * pool2.length)];
    setCurrent(next);
    setUserInput('');
    setScore(null);
    setPhase('input');
    setTimeout(() => textareaRef.current?.focus(), 100);
  }

  function handleNext() {
    if (!current) return;
    const newSeen = new Set(seenIds).add(current.id);
    setSeenIds(newSeen);
    pickNext(pool, newSeen);
  }

  async function handleSubmit() {
    if (!userInput.trim() || !current || phase !== 'input') return;
    setPhase('scoring');
    try {
      const s = await computeScore(userInput.trim(), current.title_en);
      setScore(s);
      setPhase('result');
    } catch {
      setScore(0);
      setPhase('result');
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (phase === 'input')  handleSubmit();
      if (phase === 'result') handleNext();
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  const band = score !== null ? scoreBand(score) : null;

  return (
    <Drawer isOpen={isOpen} placement="bottom" onClose={onClose}>
      <DrawerOverlay />
      <DrawerContent
        maxH="85vh"
        style={{ maxWidth: '600px', marginLeft: 'auto', marginRight: 'auto' }}
        borderTopRadius="lg"
        bg="brand.paper"
      >
        <DrawerCloseButton color="brand.muted" mt={1} />

        <DrawerHeader borderBottom="1px solid" borderColor="brand.rule" pb={3} pt={4}>
          <Text
            fontSize="md" fontWeight="700" color="brand.ink"
            fontFamily="'Noto Serif SC', 'Georgia', serif"
          >
            Translation Quiz
          </Text>
          <Text fontSize="xs" color="brand.muted" fontWeight="400" mt={0.5}>
            Translate the headline — scored by AI semantic similarity.
          </Text>
        </DrawerHeader>

        <DrawerBody py={4} overflowY="auto">
          {poolLoading ? (
            <Center py={10}><Spinner color="brand.red" size="md" /></Center>
          ) : !current ? (
            <Center py={10}>
              <VStack spacing={2}>
                <Text fontSize="xl">📭</Text>
                <Text fontSize="sm" color="brand.ink" fontWeight="600">No headlines yet</Text>
                <Text fontSize="xs" color="brand.muted" textAlign="center" maxW="240px">
                  Headlines from the past 3 days will appear here after the next job run.
                </Text>
              </VStack>
            </Center>
          ) : (
            <VStack spacing={4} align="stretch">

              {/* Headline card */}
              <Box
                bg="brand.card"
                border="1px solid"
                borderColor="brand.rule"
                borderRadius="md"
                overflow="hidden"
              >
                {current.thumbnail_url && (
                  <Box
                    as="img"
                    src={current.thumbnail_url}
                    alt=""
                    w="100%"
                    h="140px"
                    objectFit="cover"
                    display="block"
                  />
                )}
                <Box p={4}>
                  {/* Source + date */}
                  <HStack spacing={1.5} mb={2}>
                    <Text fontSize="2xs" color="brand.red" fontWeight="700">
                      {channelLabel(current.channel)}
                    </Text>
                    <Text fontSize="2xs" color="brand.muted">·</Text>
                    <Text fontSize="2xs" color="brand.muted">
                      {regionIcon(current.category)} {current.category}
                    </Text>
                    <Text fontSize="2xs" color="brand.muted">·</Text>
                    <Text fontSize="2xs" color="brand.muted">
                      {formatDate(current.published_at)}
                    </Text>
                  </HStack>

                  {/* Chinese headline */}
                  <Text
                    fontSize="lg"
                    fontWeight="700"
                    color="brand.ink"
                    lineHeight="1.5"
                    fontFamily="'Noto Serif SC', 'Georgia', serif"
                  >
                    {current.title_zh}
                  </Text>
                </Box>
              </Box>

              {/* Input area */}
              <Box>
                <Text fontSize="2xs" fontWeight="700" color="brand.muted"
                  textTransform="uppercase" letterSpacing="wider" mb={1.5}>
                  Your English translation
                </Text>
                <Textarea
                  ref={textareaRef}
                  value={userInput}
                  onChange={e => setUserInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Type your translation here…"
                  size="sm"
                  rows={3}
                  resize="none"
                  isDisabled={phase !== 'input'}
                  bg="brand.card"
                  borderColor="brand.rule"
                  color="brand.ink"
                  _placeholder={{ color: 'brand.muted' }}
                  _focus={{ borderColor: 'brand.red', boxShadow: 'none' }}
                  fontSize="sm"
                  fontFamily="inherit"
                />
              </Box>

              {/* Submit / scoring / result */}
              {phase === 'input' && (
                <Box
                  as="button"
                  onClick={handleSubmit}
                  isDisabled={!userInput.trim()}
                  bg={userInput.trim() ? 'brand.red' : 'brand.rule'}
                  color={userInput.trim() ? 'white' : 'brand.muted'}
                  px={4} py={2.5}
                  borderRadius="sm"
                  fontSize="xs"
                  fontWeight="700"
                  letterSpacing="wide"
                  textTransform="uppercase"
                  cursor={userInput.trim() ? 'pointer' : 'default'}
                  transition="all 0.15s"
                  textAlign="center"
                  _hover={userInput.trim() ? { opacity: 0.88 } : {}}
                >
                  Submit  ↵
                </Box>
              )}

              {phase === 'scoring' && (
                <Center py={3}>
                  <HStack spacing={2}>
                    <Spinner size="sm" color="brand.red" />
                    <Text fontSize="xs" color="brand.muted">
                      Scoring with AI…
                    </Text>
                  </HStack>
                </Center>
              )}

              {phase === 'result' && band && score !== null && (
                <VStack spacing={3} align="stretch">
                  {/* Score display */}
                  <Box
                    bg="brand.card"
                    border="1px solid"
                    borderColor="brand.rule"
                    borderRadius="md"
                    p={4}
                  >
                    <Flex align="center" justify="space-between" mb={3}>
                      <HStack spacing={2}>
                        <Text fontSize="xl">{band.emoji}</Text>
                        <Box>
                          <Text fontSize="sm" fontWeight="700" color={band.color}>
                            {band.label}
                          </Text>
                          <Text fontSize="2xs" color="brand.muted">
                            Similarity score: {score}/100
                          </Text>
                        </Box>
                      </HStack>
                      {/* Score bar */}
                      <Box w="72px">
                        <Box h="6px" bg="brand.rule" borderRadius="full" overflow="hidden">
                          <Box
                            h="100%"
                            w={`${score}%`}
                            bg={band.color}
                            borderRadius="full"
                            transition="width 0.4s ease"
                          />
                        </Box>
                      </Box>
                    </Flex>

                    <Divider borderColor="brand.rule" mb={3} />

                    {/* Side-by-side comparison */}
                    <VStack spacing={2} align="stretch">
                      <Box>
                        <Text fontSize="2xs" fontWeight="700" color="brand.muted"
                          textTransform="uppercase" letterSpacing="wider" mb={0.5}>
                          Your answer
                        </Text>
                        <Text fontSize="xs" color="brand.ink" lineHeight="1.6">
                          {userInput.trim()}
                        </Text>
                      </Box>
                      <Box>
                        <Text fontSize="2xs" fontWeight="700" color="brand.red"
                          textTransform="uppercase" letterSpacing="wider" mb={0.5}>
                          Original translation
                        </Text>
                        <Text fontSize="xs" color="brand.ink" lineHeight="1.6">
                          {current.title_en}
                        </Text>
                      </Box>
                    </VStack>
                  </Box>

                  {/* Next button */}
                  <Box
                    as="button"
                    onClick={handleNext}
                    bg="brand.red"
                    color="white"
                    px={4} py={2.5}
                    borderRadius="sm"
                    fontSize="xs"
                    fontWeight="700"
                    letterSpacing="wide"
                    textTransform="uppercase"
                    cursor="pointer"
                    transition="opacity 0.15s"
                    textAlign="center"
                    _hover={{ opacity: 0.88 }}
                  >
                    Next headline  ↵
                  </Box>
                </VStack>
              )}

              <Text fontSize="2xs" color="brand.muted" textAlign="center" pt={1}>
                {pool.filter(h => !seenIds.has(h.id)).length} headlines remaining
                {pool.length > 0 && ` · ${pool.length} in pool`}
              </Text>
            </VStack>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}
