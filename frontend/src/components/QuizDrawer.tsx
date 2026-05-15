/**
 * Translation Quiz
 *
 * Shows a random Chinese headline. User types an English translation and
 * gets scored via @huggingface/transformers sentence similarity (in-browser).
 *
 * Layout: flex column inside the drawer.
 *   – Top scrollable zone: headline card + result
 *   – Bottom sticky zone: textarea + submit/next button
 * This keeps the input visible when the keyboard opens on mobile.
 */

import React, { useEffect, useRef, useState } from 'react';
import {
  Box, Center, Divider, Drawer, DrawerBody, DrawerCloseButton,
  DrawerContent, DrawerHeader, DrawerOverlay, Flex,
  Spinner, Text, Textarea, VStack, HStack,
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
  id:            string;
  title_zh:      string;
  title_en:      string;
  category:      string;
  published_at:  string;
  channel:       string;
  thumbnail_url?: string;
}

type Phase = 'input' | 'scoring' | 'result';

// ── Helpers ───────────────────────────────────────────────────────────────────

function scoreBand(score: number) {
  if (score >= 85) return { label: 'Excellent',        color: '#2e7d32', emoji: '🎯' };
  if (score >= 65) return { label: 'Good',             color: '#1565c0', emoji: '👍' };
  if (score >= 45) return { label: 'Partially right',  color: '#e65100', emoji: '🤔' };
  return              { label: 'Keep practising',   color: '#b71c1c', emoji: '📚' };
}

function regionIcon(cat: string) {
  if (cat === 'Singapore') return '🇸🇬';
  if (cat === 'Malaysia')  return '🇲🇾';
  return '🌍';
}

function channelLabel(ch: string) {
  return ch === 'zaobao' ? '联合早报' : ch === 'astro' ? 'Astro 本地圈' : ch;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-MY', { day: 'numeric', month: 'short' });
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props { isOpen: boolean; onClose: () => void; }

export default function QuizDrawer({ isOpen, onClose }: Props) {
  const [seenIds, setSeenIds]     = useState<Set<string>>(new Set());
  const [current, setCurrent]     = useState<Headline | null>(null);
  const [userInput, setUserInput] = useState('');
  const [score, setScore]         = useState<number | null>(null);
  const [phase, setPhase]         = useState<Phase>('input');
  const textareaRef               = useRef<HTMLTextAreaElement>(null);
  const scrollZoneRef             = useRef<HTMLDivElement>(null);

  // Cutoff: past 3 days
  const [cutoff] = useState(
    () => new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString()
  );

  // ── Fetch pool ──────────────────────────────────────────────────────────────
  const { data: pool = [], isLoading: poolLoading } = useQuery({
    queryKey: ['quiz-pool', cutoff],
    queryFn: async (): Promise<Headline[]> => {
      const { data } = await supabase
        .from('headlines')
        .select('id, title_zh, title_en, category, published_at, channel, thumbnail_url')
        .gte('published_at', cutoff)
        .not('title_en', 'is', null)
        .not('title_zh', 'is', null)
        .order('published_at', { ascending: false })
        .limit(200);
      return (data as Headline[]) ?? [];
    },
    enabled: isOpen,
    staleTime: 5 * 60 * 1000,
  });

  // ── Pick first headline when pool loads OR drawer reopens ──────────────────
  useEffect(() => {
    if (isOpen && pool.length > 0 && !current) {
      pickNext(pool, seenIds);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, pool]);

  // ── Warm up model when drawer opens ────────────────────────────────────────
  useEffect(() => {
    if (isOpen) warmUpModel();
  }, [isOpen]);

  // ── Reset state on close ───────────────────────────────────────────────────
  useEffect(() => {
    if (!isOpen) {
      setSeenIds(new Set());
      setCurrent(null);
      setUserInput('');
      setScore(null);
      setPhase('input');
    }
  }, [isOpen]);

  // ── Pick next ──────────────────────────────────────────────────────────────
  function pickNext(src: Headline[], seen: Set<string>) {
    const unseen = src.filter(h => !seen.has(h.id));
    const candidates = unseen.length > 0 ? unseen : src; // wrap silently
    const next = candidates[Math.floor(Math.random() * candidates.length)];
    setCurrent(next);
    setUserInput('');
    setScore(null);
    setPhase('input');
    // Scroll content back to top and focus textarea
    setTimeout(() => {
      scrollZoneRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
      textareaRef.current?.focus();
    }, 80);
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
    } catch {
      setScore(0);
    }
    setPhase('result');
    // Scroll result into view
    setTimeout(() => {
      scrollZoneRef.current?.scrollTo({
        top: scrollZoneRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }, 150);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (phase === 'input')  handleSubmit();
      if (phase === 'result') handleNext();
    }
  }

  const band = score !== null ? scoreBand(score) : null;

  // ── Empty / loading states ─────────────────────────────────────────────────

  const bodyContent = poolLoading ? (
    <Center flex={1}><Spinner color="brand.red" size="md" /></Center>
  ) : !current ? (
    <Center flex={1}>
      <VStack spacing={2}>
        <Text fontSize="xl">📭</Text>
        <Text fontSize="sm" color="brand.ink" fontWeight="600">No recent headlines</Text>
        <Text fontSize="xs" color="brand.muted" textAlign="center" maxW="220px" lineHeight="1.6">
          Headlines from the past 3 days will appear here after the next job run at 09:00 SGT.
        </Text>
      </VStack>
    </Center>
  ) : null;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <Drawer isOpen={isOpen} placement="bottom" onClose={onClose}>
      <DrawerOverlay />
      <DrawerContent
        maxH="88dvh"
        style={{ maxWidth: '600px', marginLeft: 'auto', marginRight: 'auto' }}
        borderTopRadius="xl"
        bg="brand.paper"
        display="flex"
        flexDirection="column"
        overflow="hidden"
      >
        <DrawerCloseButton color="brand.muted" top={3} right={4} zIndex={1} />

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <DrawerHeader
          px={4} pt={4} pb={3}
          borderBottom="1px solid"
          borderColor="brand.rule"
          flexShrink={0}
        >
          <Text
            fontSize="md" fontWeight="700" color="brand.ink"
            fontFamily="'Noto Serif SC', 'Georgia', serif"
            pr={8}
          >
            Translation Quiz
          </Text>
          <Text fontSize="xs" color="brand.muted" fontWeight="400" mt={0.5} lineHeight="1.5">
            Read the Chinese headline · type your best English translation.
          </Text>
        </DrawerHeader>

        {/* ── Body: scrollable zone + sticky input ───────────────────────── */}
        <DrawerBody p={0} display="flex" flexDirection="column" overflow="hidden">

          {bodyContent ? (
            <Flex flex={1} direction="column" justify="center">{bodyContent}</Flex>
          ) : current ? (
            <>
              {/* Scrollable content */}
              <Box
                ref={scrollZoneRef}
                flex={1}
                overflowY="auto"
                px={4}
                pt={4}
                pb={2}
                sx={{ WebkitOverflowScrolling: 'touch' }}
              >
                {/* Headline card */}
                <Box
                  bg="brand.card"
                  border="1px solid"
                  borderColor="brand.rule"
                  borderRadius="md"
                  overflow="hidden"
                  mb={4}
                >
                  {current.thumbnail_url && (
                    <Box
                      as="img"
                      src={current.thumbnail_url}
                      alt=""
                      w="100%"
                      h="130px"
                      objectFit="cover"
                      display="block"
                    />
                  )}
                  <Box px={4} py={3}>
                    <HStack spacing={1} mb={2} flexWrap="wrap">
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
                    <Text
                      fontSize="xl"
                      fontWeight="700"
                      color="brand.ink"
                      lineHeight="1.5"
                      fontFamily="'Noto Serif SC', 'Georgia', serif"
                    >
                      {current.title_zh}
                    </Text>
                  </Box>
                </Box>

                {/* Result section — shown after scoring */}
                {phase === 'result' && band && score !== null && (
                  <Box
                    bg="brand.card"
                    border="1px solid"
                    borderColor="brand.rule"
                    borderRadius="md"
                    p={4}
                    mb={2}
                  >
                    {/* Score header */}
                    <Flex align="center" justify="space-between" mb={3}>
                      <HStack spacing={2}>
                        <Text fontSize="xl">{band.emoji}</Text>
                        <Box>
                          <Text fontSize="sm" fontWeight="700" color={band.color} lineHeight="1.2">
                            {band.label}
                          </Text>
                          <Text fontSize="2xs" color="brand.muted" mt={0.5}>
                            {score}/100
                          </Text>
                        </Box>
                      </HStack>
                      <Box w="64px">
                        <Box h="5px" bg="brand.rule" borderRadius="full" overflow="hidden">
                          <Box
                            h="100%"
                            w={`${score}%`}
                            bg={band.color}
                            borderRadius="full"
                            transition="width 0.5s ease"
                          />
                        </Box>
                      </Box>
                    </Flex>

                    <Divider borderColor="brand.rule" mb={3} />

                    <VStack spacing={3} align="stretch">
                      <Box>
                        <Text
                          fontSize="2xs" fontWeight="700" color="brand.muted"
                          textTransform="uppercase" letterSpacing="wider" mb={1}
                        >
                          Your answer
                        </Text>
                        <Text fontSize="sm" color="brand.ink" lineHeight="1.6">
                          {userInput.trim()}
                        </Text>
                      </Box>
                      <Box>
                        <Text
                          fontSize="2xs" fontWeight="700" color="brand.red"
                          textTransform="uppercase" letterSpacing="wider" mb={1}
                        >
                          Original translation
                        </Text>
                        <Text fontSize="sm" color="brand.ink" lineHeight="1.6">
                          {current.title_en}
                        </Text>
                      </Box>
                    </VStack>
                  </Box>
                )}
              </Box>

              {/* ── Sticky bottom: input + action button ─────────────────── */}
              <Box
                px={4} pt={3} pb={4}
                borderTop="1px solid"
                borderColor="brand.rule"
                bg="brand.paper"
                flexShrink={0}
              >
                {(phase === 'input' || phase === 'scoring') && (
                  <>
                    <Textarea
                      ref={textareaRef}
                      value={userInput}
                      onChange={e => setUserInput(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="Type your English translation…"
                      size="sm"
                      rows={2}
                      resize="none"
                      isDisabled={phase === 'scoring'}
                      bg="brand.card"
                      borderColor="brand.rule"
                      color="brand.ink"
                      _placeholder={{ color: 'brand.muted' }}
                      _focus={{ borderColor: 'brand.red', boxShadow: 'none' }}
                      fontSize="sm"
                      fontFamily="inherit"
                      mb={2}
                    />
                    <Box
                      as="button"
                      onClick={handleSubmit}
                      w="100%"
                      py={2.5}
                      bg={userInput.trim() && phase === 'input' ? 'brand.red' : 'brand.rule'}
                      color={userInput.trim() && phase === 'input' ? 'white' : 'brand.muted'}
                      borderRadius="sm"
                      fontSize="xs"
                      fontWeight="700"
                      letterSpacing="wide"
                      textTransform="uppercase"
                      cursor={userInput.trim() && phase === 'input' ? 'pointer' : 'default'}
                      transition="all 0.15s"
                      textAlign="center"
                      _hover={userInput.trim() && phase === 'input' ? { opacity: 0.88 } : {}}
                    >
                      {phase === 'scoring' ? (
                        <HStack justify="center" spacing={2}>
                          <Spinner size="xs" color="brand.muted" />
                          <Text fontSize="xs" fontWeight="700" letterSpacing="wide">Scoring…</Text>
                        </HStack>
                      ) : 'Submit'}
                    </Box>
                  </>
                )}

                {phase === 'result' && (
                  <Box
                    as="button"
                    onClick={handleNext}
                    w="100%"
                    py={2.5}
                    bg="brand.red"
                    color="white"
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
                    Next headline →
                  </Box>
                )}
              </Box>
            </>
          ) : null}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}
