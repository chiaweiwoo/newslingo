import React, { useEffect, useMemo, useState } from 'react';
import {
  Box,
  Center,
  Divider,
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerHeader,
  DrawerOverlay,
  Flex,
  HStack,
  Spinner,
  Text,
  VStack,
} from '@chakra-ui/react';
import { useQuery } from '@tanstack/react-query';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);

interface Topic {
  title: string;
  title_zh?: string;
  summary: string;
  summary_zh?: string;
  region: 'International' | 'Malaysia' | 'Singapore';
  theme: string;
}

interface SummaryRow {
  payload: { topics: Topic[] };
}

type RadarKey = 'governance' | 'product' | 'infrastructure';

interface RadarItem {
  title: string;
  title_zh?: string;
  description: string;
  description_zh?: string;
}

interface RadarCategory {
  key: RadarKey;
  title: string;
  items: RadarItem[];
}

interface RadarRow {
  payload: { categories: RadarCategory[] };
}

type Lang = 'en' | 'zh';
type Section = 'news' | 'ai';
type Region = 'International' | 'Malaysia' | 'Singapore';

const NEWS_FILTERS: { key: Region; label: string; shortLabel: string }[] = [
  { key: 'International', label: 'International', shortLabel: 'World' },
  { key: 'Singapore', label: 'Singapore', shortLabel: 'Singapore' },
  { key: 'Malaysia', label: 'Malaysia', shortLabel: 'Malaysia' },
];

const AI_FILTERS: { key: RadarKey; label: string; shortLabel: string }[] = [
  { key: 'governance', label: 'Governance', shortLabel: 'Governance' },
  { key: 'product', label: 'Product', shortLabel: 'Product' },
  { key: 'infrastructure', label: 'Infrastructure', shortLabel: 'Infra' },
];

function getLang(): Lang {
  try { return (localStorage.getItem('topStories.lang') as Lang) || 'en'; }
  catch { return 'en'; }
}

function setLangStorage(l: Lang) {
  try { localStorage.setItem('topStories.lang', l); } catch {}
}

function DrawerCard({
  eyebrow,
  title,
  body,
}: {
  eyebrow?: string;
  title: string;
  body: string;
}) {
  return (
    <Box py={3}>
      {eyebrow ? (
        <Text
          fontSize="2xs"
          fontWeight="700"
          color="brand.muted"
          textTransform="uppercase"
          letterSpacing="wider"
          mb={1}
        >
          {eyebrow}
        </Text>
      ) : null}
      <Text
        fontSize="sm"
        fontWeight="700"
        color="brand.ink"
        lineHeight="1.4"
        mb={1}
        fontFamily="'Noto Serif SC', 'Georgia', serif"
      >
        {title}
      </Text>
      <Text fontSize="xs" color="brand.muted" lineHeight="1.6">
        {body}
      </Text>
    </Box>
  );
}

function FilterButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <Box
      as="button"
      onClick={onClick}
      px={3}
      py={1.5}
      borderRadius="sm"
      border="1px solid"
      borderColor={active ? 'brand.red' : 'brand.rule'}
      bg={active ? 'brand.red' : 'transparent'}
      color={active ? 'brand.paper' : 'brand.muted'}
      fontSize="2xs"
      fontWeight="700"
      letterSpacing="wide"
      lineHeight="1.4"
      transition="all 0.15s"
      _hover={{ color: active ? 'brand.paper' : 'brand.ink' }}
      flex="1 1 0"
      minW={0}
      textAlign="center"
      whiteSpace="nowrap"
    >
      {label}
    </Box>
  );
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export default function ThisWeekDrawer({ isOpen, onClose }: Props) {
  const [lang, setLang] = useState<Lang>(getLang);
  const [section, setSection] = useState<Section>('news');
  const [activeRegion, setActiveRegion] = useState<Region>('International');
  const [activeRadarKey, setActiveRadarKey] = useState<RadarKey>('governance');

  const handleLang = (nextLang: Lang) => {
    setLang(nextLang);
    setLangStorage(nextLang);
  };

  const { data, isLoading } = useQuery({
    queryKey: ['top-stories-combined'],
    queryFn: async (): Promise<{ summary: SummaryRow | null; radar: RadarRow | null }> => {
      const [summaryResult, radarResult] = await Promise.all([
        supabase
          .from('weekly_summary')
          .select('payload')
          .eq('active', true)
          .order('created_at', { ascending: false })
          .limit(1)
          .maybeSingle(),
        supabase
          .from('ai_radar')
          .select('payload')
          .eq('active', true)
          .order('created_at', { ascending: false })
          .limit(1)
          .maybeSingle(),
      ]);

      return {
        summary: (summaryResult.data as SummaryRow | null) ?? null,
        radar: (radarResult.data as RadarRow | null) ?? null,
      };
    },
    enabled: isOpen,
    staleTime: 0,
  });

  const allTopics = data?.summary?.payload?.topics ?? [];
  const categories = data?.radar?.payload?.categories ?? [];

  const newsCounts = useMemo(
    () =>
      Object.fromEntries(
        NEWS_FILTERS.map(({ key }) => [key, allTopics.filter((topic) => topic.region === key).length])
      ) as Record<Region, number>,
    [allTopics]
  );

  const radarCounts = useMemo(
    () =>
      Object.fromEntries(
        AI_FILTERS.map(({ key }) => [
          key,
          categories.find((category) => category.key === key)?.items?.length ?? 0,
        ])
      ) as Record<RadarKey, number>,
    [categories]
  );

  const newsItems = allTopics.filter((topic) => topic.region === activeRegion);
  const activeRadarCategory = categories.find((category) => category.key === activeRadarKey);
  const radarItems = activeRadarCategory?.items ?? [];
  const hasNews = allTopics.length > 0;
  const hasRadar = categories.some((category) => category.items?.length);
  const hasAnyContent = hasNews || hasRadar;

  useEffect(() => {
    if (!hasNews && hasRadar) setSection('ai');
    if (hasNews && !hasRadar) setSection('news');
  }, [hasNews, hasRadar]);

  useEffect(() => {
    if (newsCounts[activeRegion] > 0) return;
    const fallback = NEWS_FILTERS.find(({ key }) => newsCounts[key] > 0);
    if (fallback) setActiveRegion(fallback.key);
  }, [activeRegion, newsCounts]);

  useEffect(() => {
    if (radarCounts[activeRadarKey] > 0) return;
    const fallback = AI_FILTERS.find(({ key }) => radarCounts[key] > 0);
    if (fallback) setActiveRadarKey(fallback.key);
  }, [activeRadarKey, radarCounts]);

  const headerTitle = section === 'news' ? 'Top Stories' : 'AI Radar';
  const headerSubtitle =
    section === 'news'
      ? 'The most important stories from the past 7 days.'
      : 'The most important AI developments from the past 7 days.';

  const emptyLabel = section === 'news' ? 'No stories this period.' : 'No developments this period.';

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
          <Flex justify="space-between" align="flex-start" pr={6}>
            <Box>
              <Text
                fontSize="md"
                fontWeight="700"
                color="brand.ink"
                lineHeight="1.2"
                fontFamily="'Noto Serif SC', 'Georgia', serif"
              >
                {headerTitle}
              </Text>
              <Text fontSize="xs" color="brand.muted" fontWeight="400" mt={0.5}>
                {headerSubtitle}
              </Text>
            </Box>

            <HStack spacing={0} mt={0.5}>
              {(['en', 'zh'] as const).map((option, i) => (
                <Box
                  key={option}
                  as="button"
                  onClick={() => handleLang(option)}
                  px={2.5}
                  py={1}
                  fontSize="2xs"
                  fontWeight="700"
                  letterSpacing="wide"
                  color={lang === option ? 'brand.paper' : 'brand.muted'}
                  bg={lang === option ? 'brand.red' : 'transparent'}
                  border="1px solid"
                  borderColor={lang === option ? 'brand.red' : 'brand.rule'}
                  borderRadius={i === 0 ? '3px 0 0 3px' : '0 3px 3px 0'}
                  transition="all 0.15s"
                  _hover={{ color: lang === option ? 'brand.paper' : 'brand.ink' }}
                  lineHeight="1.4"
                >
                  {option === 'en' ? 'EN' : '中'}
                </Box>
              ))}
            </HStack>
          </Flex>

          <HStack spacing={2} mt={3}>
            <FilterButton
              active={section === 'news'}
              label="Top Stories"
              onClick={() => setSection('news')}
            />
            <FilterButton
              active={section === 'ai'}
              label="AI Radar"
              onClick={() => setSection('ai')}
            />
          </HStack>

          <HStack spacing={2} mt={2} pb={3}>
            {section === 'news'
              ? NEWS_FILTERS.map(({ key, shortLabel }) => (
                  <FilterButton
                    key={key}
                    active={activeRegion === key}
                    label={shortLabel}
                    onClick={() => setActiveRegion(key)}
                  />
                ))
              : AI_FILTERS.map(({ key, shortLabel }) => (
                  <FilterButton
                    key={key}
                    active={activeRadarKey === key}
                    label={shortLabel}
                    onClick={() => setActiveRadarKey(key)}
                  />
                ))}
          </HStack>
        </DrawerHeader>

        <DrawerBody py={4} overflowY="auto">
          {isLoading ? (
            <Center py={10}>
              <Spinner color="brand.red" size="md" />
            </Center>
          ) : !hasAnyContent ? (
            <Center py={10}>
              <VStack spacing={2}>
                <Text fontSize="2xl">📰</Text>
                <Text fontSize="sm" color="brand.ink" fontWeight="600">Coming soon...</Text>
                <Text fontSize="xs" color="brand.muted" textAlign="center" maxW="260px">
                  Summaries appear after the daily jobs run at 09:00 and 09:30 SGT.
                </Text>
              </VStack>
            </Center>
          ) : section === 'news' && !newsItems.length ? (
            <Center py={10}>
              <Text fontSize="xs" color="brand.muted">{emptyLabel}</Text>
            </Center>
          ) : section === 'ai' && !radarItems.length ? (
            <Center py={10}>
              <Text fontSize="xs" color="brand.muted">{emptyLabel}</Text>
            </Center>
          ) : (
            <VStack spacing={0} align="stretch">
              {section === 'news'
                ? newsItems.map((topic, i) => {
                    const title = lang === 'zh' && topic.title_zh ? topic.title_zh : topic.title;
                    const body = lang === 'zh' && topic.summary_zh ? topic.summary_zh : topic.summary;
                    return (
                      <Box key={`${topic.title}-${i}`}>
                        {i > 0 && <Divider borderColor="brand.rule" />}
                        <DrawerCard eyebrow={topic.theme} title={title} body={body} />
                      </Box>
                    );
                  })
                : radarItems.map((item, i) => {
                    const title = lang === 'zh' && item.title_zh ? item.title_zh : item.title;
                    const body = lang === 'zh' && item.description_zh ? item.description_zh : item.description;
                    return (
                      <Box key={`${item.title}-${i}`}>
                        {i > 0 && <Divider borderColor="brand.rule" />}
                        <DrawerCard title={title} body={body} />
                      </Box>
                    );
                  })}
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
