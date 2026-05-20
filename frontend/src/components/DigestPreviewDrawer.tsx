import React, { useMemo, useState } from 'react';
import { Badge, Box, Center, Divider, Grid, HStack, Spinner, Stack, Text, VStack } from '@chakra-ui/react';
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

function ControlGroup({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <Stack direction={{ base: 'column', md: 'row' }} spacing={3} align={{ base: 'stretch', md: 'center' }}>
      <Text
        fontSize="11px"
        fontWeight="700"
        color="#475569"
        textTransform="uppercase"
        letterSpacing="0.1em"
        minW={{ md: '88px' }}
      >
        {label}
      </Text>
      <HStack spacing={2} flexWrap="wrap">
        {children}
      </HStack>
    </Stack>
  );
}

function ChromeDot({ color }: { color: string }) {
  return <Box w="10px" h="10px" borderRadius="full" bg={color} />;
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
  const desktopEmailWidth = '640px';
  const mobileEmailWidth = '100%';

  return (
    <Box
      minH="100vh"
      bg="linear-gradient(180deg, #eef2f7 0%, #e7ecf4 40%, #f8fafc 100%)"
      px={{ base: 3, md: 6 }}
      py={{ base: 4, md: 8 }}
    >
      <Box maxW="1440px" mx="auto">
        <Box
          bg="rgba(255,255,255,0.82)"
          border="1px solid"
          borderColor="#d9e1eb"
          borderRadius="24px"
          px={{ base: 4, md: 5 }}
          py={{ base: 4, md: 4.5 }}
          boxShadow="0 18px 40px rgba(15, 23, 42, 0.06)"
          mb={5}
        >
          <Stack direction={{ base: 'column', lg: 'row' }} justify="space-between" spacing={4}>
            <Box maxW="520px">
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
                A more realistic Gmail-style reading view with a narrower message column and separate language samples.
              </Text>
            </Box>

            <Stack spacing={3} align={{ base: 'stretch', lg: 'flex-end' }}>
              <ControlGroup label="Language">
                <ToggleButton active={mode === 'en'} label="EN" onClick={() => setMode('en')} />
                <ToggleButton active={mode === 'zh'} label="中" onClick={() => setMode('zh')} />
                <ToggleButton active={mode === 'bi'} label="EN + 中" onClick={() => setMode('bi')} />
              </ControlGroup>

              <ControlGroup label="Viewport">
                <ToggleButton active={frameMode === 'desktop'} label="Desktop" onClick={() => setFrameMode('desktop')} />
                <ToggleButton active={frameMode === 'mobile'} label="Mobile" onClick={() => setFrameMode('mobile')} />
              </ControlGroup>
            </Stack>
          </Stack>
        </Box>

        <Center alignItems="flex-start">
          {isLoading ? (
            <Center py={20}>
              <Spinner color="#c8102e" size="lg" />
            </Center>
          ) : frameMode === 'desktop' ? (
            <Box
              w="100%"
              maxW="1380px"
              borderRadius="28px"
              overflow="hidden"
              border="1px solid"
              borderColor="#d6dde7"
              boxShadow="0 34px 80px rgba(15, 23, 42, 0.15)"
              bg="#f3f6fa"
            >
              <Box bg="#ffffff" px={4} py={3} borderBottom="1px solid" borderColor="#e5eaf1">
                <HStack spacing={3}>
                  <HStack spacing={1.5}>
                    <ChromeDot color="#fb7185" />
                    <ChromeDot color="#fbbf24" />
                    <ChromeDot color="#34d399" />
                  </HStack>
                  <Box
                    flex="1"
                    maxW="720px"
                    mx="auto"
                    px={4}
                    py={2}
                    borderRadius="999px"
                    bg="#eef2f6"
                    border="1px solid"
                    borderColor="#e2e8f0"
                  >
                    <Text fontSize="sm" color="#4b5563">
                      mail.google.com
                    </Text>
                  </Box>
                  <HStack spacing={2}>
                    <Box w="10px" h="10px" borderRadius="full" bg="#cbd5e1" />
                    <Box w="10px" h="10px" borderRadius="full" bg="#cbd5e1" />
                    <Box w="10px" h="10px" borderRadius="full" bg="#cbd5e1" />
                  </HStack>
                </HStack>
              </Box>

              <Grid templateColumns="72px minmax(0, 1fr)" minH="880px">
                <Box bg="#edf2f7" borderRight="1px solid" borderColor="#e2e8f0" px={2} py={4}>
                  <VStack spacing={4}>
                    <Box w="44px" h="44px" borderRadius="16px" bg="#ffffff" border="1px solid" borderColor="#dbe2ea" />
                    {Array.from({ length: 7 }).map((_, index) => (
                      <Box key={index} w="20px" h="20px" borderRadius="6px" bg={index === 1 ? '#cbd5e1' : '#dde4ec'} />
                    ))}
                  </VStack>
                </Box>

                <Box bg="#f8fafc">
                  <Box px={4} py={3} borderBottom="1px solid" borderColor="#e2e8f0" bg="#ffffff">
                    <HStack justify="space-between">
                      <HStack spacing={3}>
                        {Array.from({ length: 5 }).map((_, index) => (
                          <Box key={index} w="18px" h="18px" borderRadius="5px" bg="#dbe3ed" />
                        ))}
                      </HStack>
                      <Text fontSize="xs" color="#6b7280">
                        1 of 1
                      </Text>
                    </HStack>
                  </Box>

                  <Box px={{ base: 4, lg: 7 }} py={5}>
                    <Box bg="#ffffff" borderRadius="26px" border="1px solid" borderColor="#e5e9f0" overflow="hidden">
                      <Box px={{ base: 4, md: 6 }} py={4} borderBottom="1px solid" borderColor="#edf1f5">
                        <HStack justify="space-between" align="flex-start" spacing={4}>
                          <Box minW={0}>
                            <Text
                              fontSize={{ base: '2xl', md: '3xl' }}
                              fontWeight="700"
                              color="#111827"
                              lineHeight="1.1"
                              fontFamily="'Noto Serif SC', 'Georgia', serif"
                            >
                              NewsLingo Daily Brief
                            </Text>
                            <HStack spacing={2} mt={2} flexWrap="wrap">
                              <Text fontSize="sm" color="#5b6470">digest@newslingo.daily</Text>
                              <Badge bg="#f1f5f9" color="#475569" borderRadius="999px" px={2.5} py={1} fontSize="10px">
                                Inbox
                              </Badge>
                            </HStack>
                          </Box>
                          <Text fontSize="xs" color="#6b7280" whiteSpace="nowrap" pt={1}>
                            {digestDate || 'Latest available summary'}
                          </Text>
                        </HStack>
                      </Box>

                      <Box px={{ base: 4, md: 6 }} py={{ base: 5, md: 6 }} bg="#f9fbfd">
                        <Center>
                          <Box w="100%" maxW={desktopEmailWidth}>
                            <Box
                              borderRadius="28px"
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

                                <Grid templateColumns={{ base: '1fr', md: 'repeat(2, minmax(0, 1fr))' }} gap={3}>
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

                                <Grid templateColumns={{ base: '1fr', md: 'repeat(2, minmax(0, 1fr))' }} gap={3}>
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
                        </Center>
                      </Box>
                    </Box>
                  </Box>
                </Box>
              </Grid>
            </Box>
          ) : (
            <Box
              w="100%"
              maxW="430px"
              borderRadius="42px"
              overflow="hidden"
              border="1px solid"
              borderColor="#cdd5df"
              boxShadow="0 30px 70px rgba(15, 23, 42, 0.18)"
              bg="#111827"
              p="10px"
            >
              <Box bg="#f8fafc" borderRadius="34px" overflow="hidden">
                <Center py={2.5}>
                  <Box w="76px" h="6px" borderRadius="999px" bg="#cad3de" />
                </Center>

                <Box px={3.5} py={3} borderBottom="1px solid" borderColor="#e5eaf1" bg="#ffffff">
                  <Text fontSize="sm" color="#111827" fontWeight="700">
                    Gmail
                  </Text>
                </Box>

                <Box px={3.5} py={4} bg="#f3f6fa">
                  <Box bg="#ffffff" borderRadius="22px" border="1px solid" borderColor="#e5e9f0" overflow="hidden">
                    <Box px={4} py={3.5} borderBottom="1px solid" borderColor="#edf1f5">
                      <Text fontSize="xl" fontWeight="700" color="#111827" lineHeight="1.2" fontFamily="'Noto Serif SC', 'Georgia', serif">
                        NewsLingo Daily Brief
                      </Text>
                      <Text fontSize="xs" color="#6b7280" mt={1}>
                        {digestDate || 'Latest available summary'}
                      </Text>
                    </Box>

                    <Box px={4} py={4} bg="#f9fbfd">
                      <Box w={mobileEmailWidth}>
                        <Box
                          borderRadius="22px"
                          px={4}
                          py={4}
                          bg="linear-gradient(135deg, #0f172a 0%, #162033 52%, #1f2a44 100%)"
                          color="#ffffff"
                        >
                          <Text fontSize="2xl" fontWeight="700" lineHeight="1.08" fontFamily="'Noto Serif SC', 'Georgia', serif">
                            NewsLingo Daily Brief
                          </Text>
                          <Text fontSize="xs" color="rgba(255,255,255,0.78)" mt={2} lineHeight="1.7">
                            A compact bilingual scan of the most important general and AI developments from the past 7 days.
                          </Text>
                        </Box>

                        <Stack spacing={4} mt={4}>
                          <SectionColumn title="Top Stories" accent="#c8102e" emptyLabel="No stories available today.">
                            {topics.map((topic, index) => (
                              <DigestStoryCard
                                key={`${topic.title}-${index}`}
                                mode={mode}
                                titleEn={topic.title}
                                titleZh={topic.title_zh}
                                bodyEn={topic.summary}
                                bodyZh={topic.summary_zh}
                                eyebrow={`${topic.region} · ${topic.theme}`}
                              />
                            ))}
                          </SectionColumn>

                          <SectionColumn title="AI" accent="#7c3aed" emptyLabel="No AI updates available today.">
                            {categories.flatMap((category) =>
                              category.items.map((item, index) => (
                                <DigestStoryCard
                                  key={`${category.key}-${item.title}-${index}`}
                                  mode={mode}
                                  titleEn={item.title}
                                  titleZh={item.title_zh}
                                  bodyEn={item.description}
                                  bodyZh={item.description_zh}
                                  eyebrow={category.title}
                                />
                              ))
                            )}
                          </SectionColumn>
                        </Stack>
                      </Box>
                    </Box>
                  </Box>
                </Box>
              </Box>
            </Box>
          )}
        </Center>
      </Box>
    </Box>
  );
}
