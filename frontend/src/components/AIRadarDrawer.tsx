import React, { useEffect, useState } from 'react';
import {
  Box, Center, Divider, Drawer, DrawerBody, DrawerCloseButton,
  DrawerContent, DrawerHeader, DrawerOverlay, Flex, HStack, Link,
  Spinner, Text, VStack,
} from '@chakra-ui/react';
import { useQuery } from '@tanstack/react-query';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);

type RadarKey = 'governance' | 'product' | 'infrastructure';

interface SourceLink {
  title: string;
  url: string;
}

interface RadarItem {
  title: string;
  description: string;
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

function RadarCard({ item }: { item: RadarItem }) {
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
        {item.title}
      </Text>
      <Text fontSize="xs" color="brand.muted" lineHeight="1.6">
        {item.description}
      </Text>

      {!!item.sources?.length && (
        <HStack spacing={2} flexWrap="wrap" pt={2}>
          {item.sources.slice(0, 3).map((source, i) => (
            <Link
              key={`${source.url}-${i}`}
              href={source.url}
              isExternal
              fontSize="2xs"
              color="brand.red"
              lineHeight="1.5"
              _hover={{ textDecoration: 'underline' }}
            >
              {source.title}
            </Link>
          ))}
        </HStack>
      )}
    </Box>
  );
}

export default function AIRadarDrawer({ isOpen, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<RadarKey>('governance');

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
          <Box pr={6}>
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
                  <RadarCard item={item} />
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
