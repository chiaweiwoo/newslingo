import React, { useMemo, useState } from 'react';
import {
  Badge,
  Box,
  Center,
  Divider,
  Flex,
  Grid,
  HStack,
  Spinner,
  Stack,
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
type FrameMode = 'desktop' | 'mobile';

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

function ToggleButton({
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
      borderRadius="999px"
      border="1px solid"
      borderColor={active ? '#111827' : '#d4dbe6'}
      bg={active ? '#111827' : '#ffffff'}
      color={active ? '#ffffff' : '#5b6470'}
      fontSize="11px"
      fontWeight="700"
      letterSpacing="0.08em"
      lineHeight="1.4"
      transition="all 0.15s"
      _hover={{ color: active ? '#ffffff' : '#111827', borderColor: '#b8c0cc' }}
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
  const baseProps = isTitle
    ? {
        fontSize: 'sm',
        fontWeight: '700',
        color: '#111827',
        lineHeight: '1.45',
        fontFamily: "'Noto Serif SC', 'Georgia', serif",
      }
    : {
        fontSize: 'xs',
        color: '#46505c',
        lineHeight: '1.75',
      };

  if (mode === 'bi' && typeof value !== 'string') {
    return (
      <VStack spacing={0.5} align="stretch">
        <Text {...baseProps}>{value.en}</Text>
        <Text {...baseProps} color={isTitle ? '#9f1239' : '#111827'}>
          {value.zh}
        </Text>
      </VStack>
    );
  }

  return <Text {...baseProps}>{typeof value === 'string' ? value : value.en || value.zh}</Text>;
}

function DigestStoryCard({
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
  return (
    <Box
      bg="#ffffff"
      border="1px solid"
      borderColor="#e5e9f0"
      borderRadius="16px"
      px={3.5}
      py={3.5}
      boxShadow="0 10px 30px rgba(15, 23, 42, 0.05)"
    >
      {eyebrow ? (
        <Badge
          bg="#f3f4f6"
          color="#5b6470"
          borderRadius="999px"
          px={2}
          py={0.5}
          fontSize="10px"
          fontWeight="700"
          letterSpacing="0.08em"
          textTransform="uppercase"
          mb={2}
        >
          {eyebrow}
        </Badge>
      ) : null}
      <EmailLine value={formatRender(mode, titleEn, titleZh)} mode={mode} isTitle />
      <Box mt={2}>
        <EmailLine value={formatRender(mode, bodyEn, bodyZh)} mode={mode} />
      </Box>
    </Box>
  );
}

function SectionColumn({
  title,
  accent,
  emptyLabel,
  children,
}: {
  title: string;
  accent: string;
  emptyLabel: string;
  children: React.ReactNode;
}) {
  const childCount = React.Children.count(children);

  return (
    <Box
      bg="#f8fafc"
      border="1px solid"
      borderColor="#e2e8f0"
      borderRadius="20px"
      px={3.5}
      py={3.5}
    >
      <HStack justify="space-between" align="center" mb={3}>
        <Text
          fontSize="11px"
          fontWeight="700"
          color="#475569"
          textTransform="uppercase"
          letterSpacing="0.1em"
        >
          {title}
        </Text>
        <Box w="10px" h="10px" borderRadius="full" bg={accent} />
      </HStack>

      {childCount ? (
        <VStack spacing={3} align="stretch">
          {children}
        </VStack>
      ) : (
        <Box
          border="1px dashed"
          borderColor="#d4dbe6"
          borderRadius="14px"
          px={3}
          py={4}
          bg="#ffffff"
        >
          <Text fontSize="xs" color="#6b7280" lineHeight="1.7">
            {emptyLabel}
          </Text>
        </Box>
      )}
    </Box>
  );
}

export default function DigestPreviewPage() {
  const [mode, setMode] = useState<DigestLang>('bi');
  const [frameMode, setFrameMode] = useState<FrameMode>('desktop');

  const { data, isLoading } = useQuery({
    queryKey: ['digest-preview-page'],
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
  const totalAiItems = categories.reduce((sum, category) => sum + (category.items?.length ?? 0), 0);
  const frameWidth = frameMode === 'mobile' ? '390px' : 'min(100%, 880px)';

  return (
    <Box
      minH="100vh"
      bg="linear-gradient(180deg, #edf2f7 0%, #e7edf6 42%, #f6f8fb 100%)"
      px={{ base: 3, md: 6 }}
      py={{ base: 4, md: 8 }}
    >
      <Box maxW="1240px" mx="auto">
        <Grid templateColumns={{ base: '1fr', xl: '280px minmax(0, 1fr)' }} gap={6}>
          <Box>
            <Box
              bg="#ffffff"
              border="1px solid"
              borderColor="#dce3ec"
              borderRadius="24px"
              px={4}
              py={4}
              boxShadow="0 18px 40px rgba(15, 23, 42, 0.06)"
              position={{ xl: 'sticky' }}
              top={{ xl: '24px' }}
            >
              <Text
                fontSize="lg"
                fontWeight="700"
                color="#111827"
                lineHeight="1.15"
                fontFamily="'Noto Serif SC', 'Georgia', serif"
              >
                Email Preview
              </Text>
              <Text fontSize="xs" color="#5b6470" lineHeight="1.7" mt={1.5}>
                Standalone preview page for the daily digest, shown as if the email is opened in a mail client.
              </Text>

              <Divider my={4} borderColor="#e5e9f0" />

              <Text fontSize="11px" fontWeight="700" color="#475569" textTransform="uppercase" letterSpacing="0.1em" mb={2}>
                Language
              </Text>
              <HStack spacing={2} flexWrap="wrap">
                <ToggleButton active={mode === 'en'} label="EN" onClick={() => setMode('en')} />
                <ToggleButton active={mode === 'zh'} label="中" onClick={() => setMode('zh')} />
                <ToggleButton active={mode === 'bi'} label="EN + 中" onClick={() => setMode('bi')} />
              </HStack>

              <Text fontSize="11px" fontWeight="700" color="#475569" textTransform="uppercase" letterSpacing="0.1em" mt={5} mb={2}>
                View
              </Text>
              <HStack spacing={2} flexWrap="wrap">
                <ToggleButton active={frameMode === 'desktop'} label="Desktop" onClick={() => setFrameMode('desktop')} />
                <ToggleButton active={frameMode === 'mobile'} label="Mobile" onClick={() => setFrameMode('mobile')} />
              </HStack>

              <Divider my={4} borderColor="#e5e9f0" />

              <VStack align="stretch" spacing={2}>
                <HStack justify="space-between">
                  <Text fontSize="xs" color="#5b6470">Top Stories</Text>
                  <Text fontSize="xs" color="#111827" fontWeight="700">{topics.length}</Text>
                </HStack>
                <HStack justify="space-between">
                  <Text fontSize="xs" color="#5b6470">AI items</Text>
                  <Text fontSize="xs" color="#111827" fontWeight="700">{totalAiItems}</Text>
                </HStack>
                <HStack justify="space-between">
                  <Text fontSize="xs" color="#5b6470">Date</Text>
                  <Text fontSize="xs" color="#111827" fontWeight="700">{digestDate || '-'}</Text>
                </HStack>
              </VStack>
            </Box>
          </Box>

          <Center alignItems="flex-start">
            {isLoading ? (
              <Center py={20}>
                <Spinner color="#c8102e" size="lg" />
              </Center>
            ) : (
              <Box w={frameWidth} transition="width 0.2s ease">
                <Box
                  bg="#dfe6ef"
                  border="1px solid"
                  borderColor="#d2d9e4"
                  borderRadius={frameMode === 'mobile' ? '36px' : '24px'}
                  p={frameMode === 'mobile' ? 3 : 4}
                  boxShadow="0 30px 60px rgba(15, 23, 42, 0.14)"
                >
                  <Box
                    bg="#f7f9fc"
                    border="1px solid"
                    borderColor="#d8e0ea"
                    borderRadius={frameMode === 'mobile' ? '30px' : '20px'}
                    overflow="hidden"
                  >
                    {frameMode === 'mobile' ? (
                      <Center py={2}>
                        <Box w="72px" h="6px" borderRadius="999px" bg="#c7d0dc" />
                      </Center>
                    ) : null}

                    <Box px={{ base: 3.5, md: 4 }} py={3} borderBottom="1px solid" borderColor="#e4eaf1" bg="#eef3f8">
                      <HStack justify="space-between" align="center">
                        <Text fontSize="11px" color="#475569" fontWeight="700" textTransform="uppercase" letterSpacing="0.12em">
                          Gmail preview
                        </Text>
                        <Text fontSize="11px" color="#7b8491">
                          Opened message
                        </Text>
                      </HStack>
                    </Box>

                    <Box px={{ base: 3.5, md: 5 }} py={{ base: 4, md: 5 }} bg="#ffffff">
                      <Box
                        borderRadius="24px"
                        px={{ base: 4, md: 5 }}
                        py={{ base: 4, md: 5 }}
                        bg="linear-gradient(135deg, #0f172a 0%, #162033 52%, #1f2a44 100%)"
                        color="#ffffff"
                      >
                        <HStack justify="space-between" align="flex-start" spacing={4}>
                          <Box minW={0}>
                            <Text
                              fontSize={{ base: '2xl', md: '3xl' }}
                              fontWeight="700"
                              lineHeight="1.05"
                              fontFamily="'Noto Serif SC', 'Georgia', serif"
                            >
                              NewsLingo Daily Brief
                            </Text>
                            <Text fontSize="sm" color="rgba(255,255,255,0.76)" mt={2} maxW="520px" lineHeight="1.7">
                              A compact bilingual scan of the most important general and AI developments from the past 7 days.
                            </Text>
                          </Box>
                          <Badge
                            alignSelf="flex-start"
                            bg="rgba(255,255,255,0.12)"
                            color="#f8fafc"
                            borderRadius="999px"
                            px={3}
                            py={1.5}
                            fontSize="10px"
                            fontWeight="700"
                            letterSpacing="0.08em"
                            textTransform="uppercase"
                            whiteSpace="nowrap"
                          >
                            {digestDate || 'Latest'}
                          </Badge>
                        </HStack>

                        <HStack spacing={2} mt={4} flexWrap="wrap">
                          <Badge bg="#ffffff" color="#111827" borderRadius="999px" px={2.5} py={1} fontSize="10px">
                            {topics.length} Top Stories
                          </Badge>
                          <Badge bg="#fde8ef" color="#9f1239" borderRadius="999px" px={2.5} py={1} fontSize="10px">
                            {totalAiItems} AI Updates
                          </Badge>
                        </HStack>
                      </Box>

                      <Stack spacing={6} mt={6}>
                        <Box>
                          <HStack justify="space-between" align="baseline" mb={3}>
                            <Text fontSize="sm" fontWeight="700" color="#111827" textTransform="uppercase" letterSpacing="0.08em">
                              Top Stories
                            </Text>
                            <Text fontSize="xs" color="#6b7280">
                              World, Singapore, Malaysia
                            </Text>
                          </HStack>

                          <Grid templateColumns={{ base: '1fr', md: 'repeat(3, minmax(0, 1fr))' }} gap={3}>
                            {NEWS_SECTIONS.map(({ key, label }) => (
                              <SectionColumn
                                key={key}
                                title={label}
                                accent={key === 'International' ? '#2563eb' : key === 'Singapore' ? '#c8102e' : '#0f766e'}
                                emptyLabel="No stories available today."
                              >
                                {topicsByRegion[key].map((topic, index) => (
                                  <DigestStoryCard
                                    key={`${topic.title}-${index}`}
                                    mode={mode}
                                    titleEn={topic.title}
                                    titleZh={topic.title_zh}
                                    bodyEn={topic.summary}
                                    bodyZh={topic.summary_zh}
                                    eyebrow={topic.theme}
                                  />
                                ))}
                              </SectionColumn>
                            ))}
                          </Grid>
                        </Box>

                        <Box>
                          <HStack justify="space-between" align="baseline" mb={3}>
                            <Text fontSize="sm" fontWeight="700" color="#111827" textTransform="uppercase" letterSpacing="0.08em">
                              AI
                            </Text>
                            <Text fontSize="xs" color="#6b7280">
                              Governance, Product, Infrastructure
                            </Text>
                          </HStack>

                          <Grid templateColumns={{ base: '1fr', md: 'repeat(3, minmax(0, 1fr))' }} gap={3}>
                            {AI_SECTIONS.map(({ key, label }) => (
                              <SectionColumn
                                key={key}
                                title={label}
                                accent={key === 'governance' ? '#7c3aed' : key === 'product' ? '#ea580c' : '#0284c7'}
                                emptyLabel="No AI updates available today."
                              >
                                {radarByKey[key].map((item, index) => (
                                  <DigestStoryCard
                                    key={`${item.title}-${index}`}
                                    mode={mode}
                                    titleEn={item.title}
                                    titleZh={item.title_zh}
                                    bodyEn={item.description}
                                    bodyZh={item.description_zh}
                                  />
                                ))}
                              </SectionColumn>
                            ))}
                          </Grid>
                        </Box>
                      </Stack>
                    </Box>
                  </Box>
                </Box>
              </Box>
            )}
          </Center>
        </Grid>
      </Box>
    </Box>
  );
}
