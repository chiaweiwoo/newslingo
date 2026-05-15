import React, { useState } from 'react';
import {
  Drawer, DrawerBody, DrawerHeader, DrawerOverlay, DrawerContent,
  DrawerCloseButton, Box, Text, VStack, Flex, Spinner, Center, Divider, HStack,
} from '@chakra-ui/react';
import { useQuery } from '@tanstack/react-query';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);

// ── Types ─────────────────────────────────────────────────────────────────────

interface Topic {
  title:      string;
  title_zh?:  string;
  summary:    string;
  summary_zh?: string;
  region:     'International' | 'Malaysia' | 'Singapore';
  theme?:     string;
  so_what?:   string;
  lesson?:    string[];
}

interface SummaryRow {
  payload: { topics: Topic[] };
}

type Lang   = 'en' | 'zh';
type Region = 'International' | 'Malaysia' | 'Singapore';

const REGIONS: { key: Region; label: string; icon: string }[] = [
  { key: 'International', label: 'International', icon: '🌍' },
  { key: 'Singapore',     label: 'Singapore',     icon: '🇸🇬' },
  { key: 'Malaysia',      label: 'Malaysia',      icon: '🇲🇾' },
];

function getLang(): Lang {
  try { return (localStorage.getItem('topStories.lang') as Lang) || 'en'; }
  catch { return 'en'; }
}

function setLangStorage(l: Lang) {
  try { localStorage.setItem('topStories.lang', l); } catch {}
}

// ── Topic card ────────────────────────────────────────────────────────────────

function TopicCard({ topic, lang }: { topic: Topic; lang: Lang }) {
  const title   = lang === 'zh' && topic.title_zh   ? topic.title_zh   : topic.title;
  const summary = lang === 'zh' && topic.summary_zh ? topic.summary_zh : topic.summary;

  return (
    <Box py={3}>
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
        {title}
      </Text>
      <Text fontSize="xs" color="brand.muted" lineHeight="1.6">
        {summary}
      </Text>
    </Box>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  isOpen:  boolean;
  onClose: () => void;
}

export default function ThisWeekDrawer({ isOpen, onClose }: Props) {
  const [lang, setLang]             = useState<Lang>(getLang);
  const [activeRegion, setActiveRegion] = useState<Region>('International');

  const handleLang = (l: Lang) => {
    setLang(l);
    setLangStorage(l);
  };

  const { data: summary, isLoading } = useQuery({
    queryKey: ['top-stories'],
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

  const allTopics   = summary?.payload?.topics ?? [];
  const tabTopics = allTopics.filter(t => t.region === activeRegion);

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

        <DrawerHeader borderBottom="1px solid" borderColor="brand.rule" pb={0} pt={4}>
          {/* Title row + language toggle */}
          <Flex justify="space-between" align="flex-start" pr={6}>
            <Box>
              <Text
                fontSize="md" fontWeight="700" color="brand.ink" lineHeight="1.2"
                fontFamily="'Noto Serif SC', 'Georgia', serif"
              >
                Top Stories
              </Text>
              <Text fontSize="xs" color="brand.muted" fontWeight="400" mt={0.5}>
                The most important stories from the past 7 days.
              </Text>
            </Box>

            {/* EN / 中 toggle — always visible; falls back to EN when title_zh not yet generated */}
            <HStack spacing={0} mt={0.5}>
              {(['en', 'zh'] as const).map((l, i) => (
                <Box
                  key={l}
                  as="button"
                  onClick={() => handleLang(l)}
                  px={2.5} py={1}
                  fontSize="2xs"
                  fontWeight="700"
                  letterSpacing="wide"
                  color={lang === l ? 'brand.paper' : 'brand.muted'}
                  bg={lang === l ? 'brand.red' : 'transparent'}
                  border="1px solid"
                  borderColor={lang === l ? 'brand.red' : 'brand.rule'}
                  borderRadius={i === 0 ? '3px 0 0 3px' : '0 3px 3px 0'}
                  transition="all 0.15s"
                  _hover={{ color: lang === l ? 'brand.paper' : 'brand.ink' }}
                  lineHeight="1.4"
                >
                  {l === 'en' ? 'EN' : '中'}
                </Box>
              ))}
            </HStack>
          </Flex>

          {/* Region tabs */}
          <Flex mt={3} borderBottom="none">
            {REGIONS.map(({ key, label, icon }) => {
              const active  = activeRegion === key;
              const count   = allTopics.filter(t => t.region === key).length;
              if (!isLoading && count === 0) return null;
              return (
                <Box
                  key={key}
                  as="button"
                  flex={1}
                  py={2}
                  fontSize="xs"
                  fontWeight={active ? '700' : '500'}
                  color={active ? 'brand.red' : 'brand.muted'}
                  borderBottom="2px solid"
                  borderColor={active ? 'brand.red' : 'transparent'}
                  transition="all 0.15s"
                  _hover={{ color: active ? 'brand.red' : 'brand.ink' }}
                  onClick={() => setActiveRegion(key)}
                >
                  {icon} {label}
                </Box>
              );
            })}
          </Flex>
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
          ) : !tabTopics.length ? (
            <Center py={10}>
              <Text fontSize="xs" color="brand.muted">No stories this period.</Text>
            </Center>
          ) : (
            <VStack spacing={0} align="stretch">
              {tabTopics.map((topic, i) => (
                <Box key={i}>
                  {i > 0 && <Divider borderColor="brand.rule" />}
                  <TopicCard topic={topic} lang={lang} />
                </Box>
              ))}
              <Divider borderColor="brand.rule" />
              <Text fontSize="2xs" color="brand.muted" textAlign="center" pt={3} pb={2} lineHeight="1.6">
                Updated daily · past 7 days
              </Text>
            </VStack>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}
