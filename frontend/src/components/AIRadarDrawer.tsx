import React, { useEffect, useState } from 'react';
import {
  Box, Center, Divider, Drawer, DrawerBody, DrawerCloseButton,
  DrawerContent, DrawerHeader, DrawerOverlay, Flex, HStack,
  Spinner, Text, VStack,
} from '@chakra-ui/react';
import { useQuery } from '@tanstack/react-query';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);

type RadarKey = 'governance' | 'product' | 'infrastructure';
type Lang = 'en' | 'zh';

interface SourceLink {
  title: string;
  url: string;
}

interface RadarItem {
  title: string;
  title_zh?: string;
  description: string;
  description_zh?: string;
  sources: SourceLink[];
}

interface RadarCategory {
  key: RadarKey;
  title: string;
  items: RadarItem[];
}

interface RadarRow {
  payload: { categories: RadarCategory[] };
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

const TABS: { key: RadarKey; label: string }[] = [
  { key: 'governance', label: 'Governance' },
  { key: 'product', label: 'Product' },
  { key: 'infrastructure', label: 'Infrastructure' },
];

function getLang(): Lang {
  try { return (localStorage.getItem('aiRadar.lang') as Lang) || 'en'; }
  catch { return 'en'; }
}

function setLangStorage(l: Lang) {
  try { localStorage.setItem('aiRadar.lang', l); } catch {}
}

function RadarCard({ item, lang }: { item: RadarItem; lang: Lang }) {
  const title = lang === 'zh' && item.title_zh ? item.title_zh : item.title;
  const description = lang === 'zh' && item.description_zh ? item.description_zh : item.description;

  return (
    <Box py={3}>
      <Text
        fontSize="sm"
        fontWeight="700"
        color="brand.ink"
        lineHeight="1.4"
        mb={1.5}
        fontFamily="'Noto Serif SC', 'Georgia', serif"
      >
        {title}
      </Text>
      <Text fontSize="xs" color="brand.muted" lineHeight="1.6">
        {description}
      </Text>
    </Box>
  );
}

export default function AIRadarDrawer({ isOpen, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<RadarKey>('governance');
  const [lang, setLang] = useState<Lang>(getLang);

  const handleLang = (l: Lang) => {
    setLang(l);
    setLangStorage(l);
  };

  const { data: radar, isLoading } = useQuery({
    queryKey: ['ai-radar'],
    queryFn: async (): Promise<RadarRow | null> => {
      const { data } = await supabase
        .from('ai_radar')
        .select('payload')
        .eq('active', true)
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle();
      return (data as RadarRow | null);
    },
    enabled: isOpen,
    staleTime: 0,
  });

  const categories = radar?.payload?.categories ?? [];
  const firstNonEmpty = categories.find((category) => category.items?.length);

  useEffect(() => {
    if (!categories.length) return;
    const current = categories.find((category) => category.key === activeTab);
    if (current?.items?.length) return;
    if (firstNonEmpty) setActiveTab(firstNonEmpty.key);
  }, [activeTab, categories, firstNonEmpty]);

  const activeCategory = categories.find((category) => category.key === activeTab);
  const activeItems = activeCategory?.items ?? [];

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
                AI Radar
              </Text>
              <Text fontSize="xs" color="brand.muted" fontWeight="400" mt={0.5}>
                The most important AI developments from the past 7 days.
              </Text>
            </Box>

            <HStack spacing={0} mt={0.5}>
              {(['en', 'zh'] as const).map((l, i) => (
                <Box
                  key={l}
                  as="button"
                  onClick={() => handleLang(l)}
                  px={2.5}
                  py={1}
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

          <Flex mt={3}>
            {TABS.map(({ key, label }) => {
              const active = activeTab === key;
              const count = categories.find((category) => category.key === key)?.items?.length ?? 0;
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
                  onClick={() => setActiveTab(key)}
                >
                  {label}
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
          ) : !categories.length ? (
            <Center py={10}>
              <VStack spacing={2}>
                <Text fontSize="sm" color="brand.ink" fontWeight="600">Coming soon...</Text>
                <Text fontSize="xs" color="brand.muted" textAlign="center" maxW="240px">
                  The first radar appears after the daily job runs at 09:30 SGT.
                </Text>
              </VStack>
            </Center>
          ) : !activeItems.length ? (
            <Center py={10}>
              <Text fontSize="xs" color="brand.muted">No developments this period.</Text>
            </Center>
          ) : (
            <VStack spacing={0} align="stretch">
              {activeItems.map((item, i) => (
                <Box key={`${item.title}-${i}`}>
                  {i > 0 && <Divider borderColor="brand.rule" />}
                  <RadarCard item={item} lang={lang} />
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
