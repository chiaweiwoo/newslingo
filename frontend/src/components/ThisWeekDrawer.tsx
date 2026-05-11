import React, { useEffect, useState } from 'react';
import {
  Drawer, DrawerBody, DrawerHeader, DrawerOverlay, DrawerContent,
  DrawerCloseButton, Box, Text, VStack, Flex, Spinner, Center, Divider,
} from '@chakra-ui/react';
import { useQuery } from '@tanstack/react-query';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);

// ── Types ─────────────────────────────────────────────────────────────────────

const THEMES = ['Politics', 'Economy', 'Society', 'Security', 'Technology', 'Environment'] as const;
type Theme = typeof THEMES[number];

interface Topic {
  title:   string;
  summary: string;
  region:  'International' | 'Malaysia' | 'Singapore';
  theme?:  Theme;   // optional — older rows may not have it
}

interface SummaryPayload {
  topics: Topic[];
}

interface SummaryRow {
  payload: SummaryPayload;
}

const REGIONS: { key: 'International' | 'Malaysia' | 'Singapore'; label: string; icon: string }[] = [
  { key: 'International', label: 'International', icon: '🌍' },
  { key: 'Singapore',     label: 'Singapore',     icon: '🇸🇬' },
  { key: 'Malaysia',      label: 'Malaysia',      icon: '🇲🇾' },
];

const LS_KEY = 'nl-thisweek-themes';

// ── Helpers ───────────────────────────────────────────────────────────────────

function loadStoredThemes(): Theme[] {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) {
      const parsed: unknown = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed as Theme[];
    }
  } catch {}
  return [...THEMES];
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  isOpen:  boolean;
  onClose: () => void;
}

export default function ThisWeekDrawer({ isOpen, onClose }: Props) {
  const [selected, setSelected] = useState<Theme[]>(loadStoredThemes);

  useEffect(() => {
    localStorage.setItem(LS_KEY, JSON.stringify(selected));
  }, [selected]);

  const toggle = (theme: Theme) => {
    setSelected(prev =>
      prev.includes(theme)
        ? prev.length > 1 ? prev.filter(t => t !== theme) : prev  // keep at least one
        : [...prev, theme]
    );
  };

  const { data: summary, isLoading } = useQuery({
    queryKey: ['this-week'],
    queryFn: async (): Promise<SummaryRow | null> => {
      const { data } = await supabase
        .from('weekly_summary')
        .select('payload')
        .eq('active', true)
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle();
      return (data as SummaryRow | null);
    },
    enabled: isOpen,
    staleTime: 0,
  });

  // Filter by selected themes — topics without a theme pass through (legacy data)
  const allTopics = summary?.payload?.topics ?? [];
  const filtered  = allTopics.filter(t => !t.theme || selected.includes(t.theme));

  return (
    <Drawer isOpen={isOpen} placement="bottom" onClose={onClose}>
      <DrawerOverlay />
      <DrawerContent
        maxH="80vh"
        style={{ maxWidth: '600px', marginLeft: 'auto', marginRight: 'auto' }}
        borderTopRadius="lg"
        bg="brand.paper"
      >
        <DrawerCloseButton color="brand.muted" mt={1} />

        <DrawerHeader borderBottom="1px solid" borderColor="brand.rule" pb={3} pt={4}>
          <Text
            fontSize="md" fontWeight="700" color="brand.ink" lineHeight="1.2"
            fontFamily="'Noto Serif SC', 'Georgia', serif"
          >
            This Week
          </Text>
          <Text fontSize="xs" color="brand.muted" fontWeight="400" mt={0.5}>
            The most important stories from the past 7 days.
          </Text>
        </DrawerHeader>

        <DrawerBody py={4} overflowY="auto">
          {isLoading ? (
            <Center py={10}>
              <Spinner color="brand.red" size="md" />
            </Center>
          ) : !allTopics.length ? (
            <Center py={10}>
              <VStack spacing={2}>
                <Text fontSize="2xl">📰</Text>
                <Text fontSize="sm" color="brand.ink" fontWeight="600">Coming soon…</Text>
                <Text fontSize="xs" color="brand.muted" textAlign="center" maxW="240px">
                  The summary appears after the daily job runs at 09:00 SGT.
                </Text>
              </VStack>
            </Center>
          ) : (
            <VStack spacing={5} align="stretch">

              {/* ── Theme filter chips ──────────────────────────────────── */}
              <Flex wrap="wrap" gap={2}>
                {THEMES.map(theme => {
                  const active = selected.includes(theme);
                  return (
                    <Box
                      key={theme}
                      as="button"
                      onClick={() => toggle(theme)}
                      px={2.5} py="3px"
                      border="1px solid"
                      borderColor={active ? 'brand.red' : 'brand.rule'}
                      borderRadius="full"
                      fontSize="2xs"
                      fontWeight={active ? '700' : '400'}
                      color={active ? 'brand.red' : 'brand.muted'}
                      bg="transparent"
                      transition="all 0.15s"
                      cursor="pointer"
                      userSelect="none"
                      _hover={{ borderColor: 'brand.red', color: 'brand.red' }}
                    >
                      {theme}
                    </Box>
                  );
                })}
              </Flex>

              <Divider borderColor="brand.rule" />

              {/* ── Topics grouped by region ────────────────────────────── */}
              {filtered.length === 0 ? (
                <Center py={6}>
                  <Text fontSize="xs" color="brand.muted">
                    No stories match your selected themes this week.
                  </Text>
                </Center>
              ) : (
                <VStack spacing={5} align="stretch">
                  {REGIONS.map(({ key, label, icon }) => {
                    const topics = filtered.filter(t => t.region === key);
                    if (!topics.length) return null;
                    return (
                      <Box key={key}>
                        <Text
                          fontSize="xs" fontWeight="700" color="brand.red"
                          textTransform="uppercase" letterSpacing="wider" mb={2.5}
                        >
                          {icon} {label}
                        </Text>
                        <VStack spacing={0} align="stretch">
                          {topics.map((topic, i) => (
                            <Box key={i}>
                              {i > 0 && <Divider borderColor="brand.rule" />}
                              <Box py={2.5}>
                                {topic.theme && (
                                  <Text
                                    fontSize="2xs" fontWeight="700" color="brand.muted"
                                    textTransform="uppercase" letterSpacing="wider" mb={1}
                                  >
                                    {topic.theme}
                                  </Text>
                                )}
                                <Text
                                  fontSize="sm" fontWeight="700" color="brand.ink"
                                  lineHeight="1.4" mb={1}
                                  fontFamily="'Noto Serif SC', 'Georgia', serif"
                                >
                                  {topic.title}
                                </Text>
                                <Text fontSize="xs" color="brand.muted" lineHeight="1.6">
                                  {topic.summary}
                                </Text>
                              </Box>
                            </Box>
                          ))}
                        </VStack>
                      </Box>
                    );
                  })}
                </VStack>
              )}

              <Divider borderColor="brand.rule" />
              <Text fontSize="2xs" color="brand.muted" textAlign="center" pb={2} lineHeight="1.6">
                Updated daily · past 7 days
              </Text>

            </VStack>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}
