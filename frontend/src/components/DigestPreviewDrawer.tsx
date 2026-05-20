import React, { useMemo, useState } from 'react';
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

type Region = 'International' | 'Malaysia' | 'Singapore';
type RadarKey = 'governance' | 'product' | 'infrastructure';
type DigestLang = 'en' | 'zh' | 'bi';

interface Topic {
  title: string;
  title_zh?: string;
  summary: string;
  summary_zh?: string;
  region: Region;
  theme: string;
}

interface SummaryRow {
  created_at: string;
  payload: { topics: Topic[] };
}

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
  created_at: string;
  payload: { categories: RadarCategory[] };
}

const NEWS_SECTIONS: { key: Region; label: string }[] = [
  { key: 'International', label: 'World' },
  { key: 'Singapore', label: 'Singapore' },
  { key: 'Malaysia', label: 'Malaysia' },
];

const AI_SECTIONS: { key: RadarKey; label: string }[] = [
  { key: 'governance', label: 'Governance' },
  { key: 'product', label: 'Product' },
  { key: 'infrastructure', label: 'Infra' },
];

function formatDigestDate(summaryDate?: string, radarDate?: string): string | null {
  const candidate = summaryDate ?? radarDate;
  if (!candidate) return null;
  const date = new Date(candidate);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat('en-SG', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'Asia/Singapore',
  }).format(date);
}

function formatRender(mode: DigestLang, en?: string, zh?: string) {
  if (mode === 'zh') return zh || en || '';
  if (mode === 'en') return en || zh || '';
  return { en: en || '', zh: zh || '' };
}

function ModeButton({
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

function EmailLine({
  value,
  mode,
  isTitle = false,
}: {
  value: ReturnType<typeof formatRender>;
  mode: DigestLang;
  isTitle?: boolean;
}) {
  const titleProps = isTitle
    ? {
        fontSize: 'sm',
        fontWeight: '700',
        color: 'brand.ink',
        lineHeight: '1.45',
        fontFamily: "'Noto Serif SC', 'Georgia', serif",
      }
    : {
        fontSize: 'xs',
        color: 'brand.muted',
        lineHeight: '1.7',
      };

  if (mode === 'bi' && typeof value !== 'string') {
    return (
      <VStack spacing={0.5} align="stretch">
        <Text {...titleProps}>{value.en}</Text>
        <Text {...titleProps} color={isTitle ? 'brand.red' : 'brand.ink'}>
          {value.zh}
        </Text>
      </VStack>
    );
  }

  return <Text {...titleProps}>{typeof value === 'string' ? value : value.en || value.zh}</Text>;
}

function DigestItem({
  mode,
  titleEn,
  titleZh,
  bodyEn,
  bodyZh,
  eyebrow,
}: {
  mode: DigestLang;
  titleEn: string;
  titleZh?: string;
  bodyEn: string;
  bodyZh?: string;
  eyebrow?: string;
}) {
  const title = formatRender(mode, titleEn, titleZh);
  const body = formatRender(mode, bodyEn, bodyZh);

  return (
    <Box py={3}>
      {eyebrow ? (
        <Text
          fontSize="2xs"
          fontWeight="700"
          color="brand.muted"
          textTransform="uppercase"
          letterSpacing="wider"
          mb={1.5}
        >
          {eyebrow}
        </Text>
      ) : null}
      <EmailLine value={title} mode={mode} isTitle />
      <Box mt={1.5}>
        <EmailLine value={body} mode={mode} />
      </Box>
    </Box>
  );
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export default function DigestPreviewDrawer({ isOpen, onClose }: Props) {
  const [mode, setMode] = useState<DigestLang>('bi');

  const { data, isLoading } = useQuery({
    queryKey: ['digest-preview'],
    queryFn: async (): Promise<{ summary: SummaryRow | null; radar: RadarRow | null }> => {
      const [summaryResult, radarResult] = await Promise.all([
        supabase
          .from('weekly_summary')
          .select('created_at, payload')
          .eq('active', true)
          .order('created_at', { ascending: false })
          .limit(1)
          .maybeSingle(),
        supabase
          .from('ai_radar')
          .select('created_at, payload')
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

  const topics = data?.summary?.payload?.topics ?? [];
  const categories = data?.radar?.payload?.categories ?? [];

  const topicsByRegion = useMemo(
    () =>
      Object.fromEntries(
        NEWS_SECTIONS.map(({ key }) => [key, topics.filter((topic) => topic.region === key)])
      ) as Record<Region, Topic[]>,
    [topics]
  );

  const radarByKey = useMemo(
    () =>
      Object.fromEntries(
        AI_SECTIONS.map(({ key }) => [
          key,
          categories.find((category) => category.key === key)?.items ?? [],
        ])
      ) as Record<RadarKey, RadarItem[]>,
    [categories]
  );

  const digestDate = formatDigestDate(data?.summary?.created_at, data?.radar?.created_at);
  const hasAnyContent = topics.length > 0 || categories.some((category) => category.items?.length);

  return (
    <Drawer isOpen={isOpen} placement="bottom" onClose={onClose}>
      <DrawerOverlay />
      <DrawerContent
        maxH="86vh"
        style={{ maxWidth: '600px', marginLeft: 'auto', marginRight: 'auto' }}
        borderTopRadius="lg"
        bg="brand.paper"
      >
        <DrawerCloseButton color="brand.muted" mt={1} />

        <DrawerHeader borderBottom="1px solid" borderColor="brand.rule" pb={3} pt={4}>
          <Text
            fontSize="md"
            fontWeight="700"
            color="brand.ink"
            lineHeight="1.2"
            fontFamily="'Noto Serif SC', 'Georgia', serif"
          >
            Email Preview
          </Text>
          <Text fontSize="xs" color="brand.muted" fontWeight="400" mt={0.5}>
            Compact daily brief for Gmail on mobile and desktop.
          </Text>

          <HStack spacing={2} mt={3}>
            <ModeButton active={mode === 'en'} label="EN" onClick={() => setMode('en')} />
            <ModeButton active={mode === 'zh'} label="中" onClick={() => setMode('zh')} />
            <ModeButton active={mode === 'bi'} label="EN + 中" onClick={() => setMode('bi')} />
          </HStack>
        </DrawerHeader>

        <DrawerBody py={4} overflowY="auto">
          {isLoading ? (
            <Center py={10}>
              <Spinner color="brand.red" size="md" />
            </Center>
          ) : !hasAnyContent ? (
            <Center py={10}>
              <Text fontSize="xs" color="brand.muted">No digest data available yet.</Text>
            </Center>
          ) : (
            <Box
              bg="brand.card"
              border="1px solid"
              borderColor="brand.rule"
              borderRadius="sm"
              px={4}
              py={4}
            >
              <VStack spacing={0} align="stretch">
                <Box pb={4}>
                  <Text
                    fontSize="lg"
                    fontWeight="700"
                    color="brand.ink"
                    lineHeight="1.2"
                    fontFamily="'Noto Serif SC', 'Georgia', serif"
                  >
                    NewsLingo Daily Brief
                  </Text>
                  <Text fontSize="2xs" color="brand.muted" mt={1}>
                    {digestDate || 'Latest available summary'}
                  </Text>
                </Box>

                <Divider borderColor="brand.rule" />

                <Box pt={4}>
                  <Text
                    fontSize="2xs"
                    fontWeight="700"
                    color="brand.red"
                    textTransform="uppercase"
                    letterSpacing="wider"
                    mb={2}
                  >
                    Top Stories
                  </Text>
                  <VStack spacing={0} align="stretch">
                    {NEWS_SECTIONS.map(({ key, label }) => {
                      const items = topicsByRegion[key];
                      return (
                        <Box key={key} pt={1} pb={2}>
                          <Text
                            fontSize="2xs"
                            fontWeight="700"
                            color="brand.muted"
                            textTransform="uppercase"
                            letterSpacing="wider"
                            mb={1}
                          >
                            {label}
                          </Text>
                          {items.length ? (
                            items.map((topic, index) => (
                              <Box key={`${topic.title}-${index}`}>
                                {index > 0 && <Divider borderColor="brand.rule" />}
                                <DigestItem
                                  mode={mode}
                                  titleEn={topic.title}
                                  titleZh={topic.title_zh}
                                  bodyEn={topic.summary}
                                  bodyZh={topic.summary_zh}
                                  eyebrow={topic.theme}
                                />
                              </Box>
                            ))
                          ) : (
                            <Text fontSize="xs" color="brand.muted" py={3}>
                              No stories available today.
                            </Text>
                          )}
                        </Box>
                      );
                    })}
                  </VStack>
                </Box>

                <Divider borderColor="brand.rule" />

                <Box pt={4}>
                  <Text
                    fontSize="2xs"
                    fontWeight="700"
                    color="brand.red"
                    textTransform="uppercase"
                    letterSpacing="wider"
                    mb={2}
                  >
                    AI
                  </Text>
                  <VStack spacing={0} align="stretch">
                    {AI_SECTIONS.map(({ key, label }) => {
                      const items = radarByKey[key];
                      return (
                        <Box key={key} pt={1} pb={2}>
                          <Text
                            fontSize="2xs"
                            fontWeight="700"
                            color="brand.muted"
                            textTransform="uppercase"
                            letterSpacing="wider"
                            mb={1}
                          >
                            {label}
                          </Text>
                          {items.length ? (
                            items.map((item, index) => (
                              <Box key={`${item.title}-${index}`}>
                                {index > 0 && <Divider borderColor="brand.rule" />}
                                <DigestItem
                                  mode={mode}
                                  titleEn={item.title}
                                  titleZh={item.title_zh}
                                  bodyEn={item.description}
                                  bodyZh={item.description_zh}
                                />
                              </Box>
                            ))
                          ) : (
                            <Text fontSize="xs" color="brand.muted" py={3}>
                              No AI updates available today.
                            </Text>
                          )}
                        </Box>
                      );
                    })}
                  </VStack>
                </Box>
              </VStack>
            </Box>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}
