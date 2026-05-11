import React, { useEffect, useRef, useState } from 'react';
import {
  Box, Flex, Heading, Spinner, Text, VStack, Divider, HStack, Center,
  useDisclosure,
} from '@chakra-ui/react';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { createClient } from '@supabase/supabase-js';
import HeadlineCard from './components/HeadlineCard';
import AIInsightsDrawer from './components/AIInsightsDrawer';

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);

const PAGE_SIZE = 20;
type Category = 'International' | 'Malaysia' | 'Singapore';

const TABS: { label: string; value: Category; icon: string }[] = [
  { label: 'International', value: 'International', icon: '🌍' },
  { label: 'Malaysia',      value: 'Malaysia',      icon: '🇲🇾' },
  { label: 'Singapore',     value: 'Singapore',     icon: '🇸🇬' },
];

function toSlug(date: string) {
  return date.replace(/[^a-zA-Z0-9]/g, '-').toLowerCase();
}

function groupByDate(headlines: any[]) {
  const groups: Record<string, any[]> = {};
  for (const h of headlines) {
    const label = new Date(h.published_at).toLocaleDateString('en-MY', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    });
    if (!groups[label]) groups[label] = [];
    groups[label].push(h);
  }
  return groups;
}

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<Category>('International');
  const sentinelRef = useRef<HTMLDivElement>(null);
  const { isOpen: isInsightsOpen, onOpen: onInsightsOpen, onClose: onInsightsClose } = useDisclosure();

  // Visit tracking — fire once on mount
  useEffect(() => {
    const track = async () => {
      try {
        const { ip } = await fetch('https://api.ipify.org?format=json').then(r => r.json());
        const ua = navigator.userAgent;
        await supabase.from('visits').insert({
          ip,
          user_agent: ua,
          is_mobile: /Mobi|Android/i.test(ua),
        });
      } catch (_) {}
    };
    track();
  }, []);

  // Last job execution time for "Updated X ago"
  const { data: latestDate } = useQuery({
    queryKey: ['latest-date'],
    queryFn: async (): Promise<string | null> => {
      const { data } = await supabase
        .from('job_runs')
        .select('ran_at')
        .eq('status', 'success')
        .order('ran_at', { ascending: false })
        .limit(1)
        .maybeSingle();
      return (data as { ran_at: string } | null)?.ran_at ?? null;
    },
    staleTime: 0,
  });

  // Paginated headlines per tab
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
  } = useInfiniteQuery({
    queryKey: ['headlines', activeTab],
    queryFn: async ({ pageParam = 0 }) => {
      const { data } = await supabase
        .from('headlines')
        .select('*')
        .eq('category', activeTab)
        .order('published_at', { ascending: false })
        .range(pageParam, pageParam + PAGE_SIZE - 1);
      return data || [];
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) =>
      lastPage.length < PAGE_SIZE ? undefined : allPages.flat().length,
  });

  // Infinite scroll sentinel
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage();
        }
      },
      { rootMargin: '300px' }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const headlines = data?.pages.flat() || [];
  const grouped = groupByDate(headlines);

  return (
    <Box minH="100vh" bg="gray.50">

      {/* Sticky header */}
      <Box
        position="sticky" top={0} zIndex={100}
        bg="gray.900" borderBottom="3px solid" borderColor="red.500"
      >
        <Box maxW="600px" mx="auto" px={4}>

          {/* Title row */}
          <Flex align="center" justify="space-between" pt={3} pb={2}>
            <Heading
              size="md" color="white" fontWeight="black"
              letterSpacing="-0.5px" fontFamily="'Georgia', serif"
            >
              NewsLingo
            </Heading>
            <HStack spacing={3}>
              <Text
                fontSize="2xs" color="gray.500" cursor="pointer"
                onClick={onInsightsOpen}
                _hover={{ color: 'gray.300' }}
                transition="color 0.15s"
                title="How AI is improving"
              >
                🧠 AI
              </Text>
              {latestDate && (
                <Text fontSize="2xs" color="gray.500" letterSpacing="wide">
                  Updated {timeAgo(latestDate)}
                </Text>
              )}
            </HStack>
          </Flex>

          {/* Tab bar */}
          <Flex>
            {TABS.map(tab => {
              const active = activeTab === tab.value;
              return (
                <Box
                  key={tab.value}
                  flex={1}
                  py={2.5}
                  textAlign="center"
                  cursor="pointer"
                  onClick={() => setActiveTab(tab.value)}
                  borderBottom="2px solid"
                  borderColor={active ? 'red.400' : 'transparent'}
                  color={active ? 'white' : 'gray.500'}
                  fontSize="sm"
                  fontWeight={active ? 'bold' : 'normal'}
                  transition="all 0.15s"
                  userSelect="none"
                >
                  {tab.icon} {tab.label}
                </Box>
              );
            })}
          </Flex>
        </Box>
      </Box>

      {/* Feed */}
      <Box maxW="600px" mx="auto" px={4} pb={16} pt={6}>
        {isLoading ? (
          <Center py={20}>
            <VStack spacing={3}>
              <Spinner size="lg" color="red.500" thickness="3px" />
              <Text fontSize="sm" color="gray.400">Loading…</Text>
            </VStack>
          </Center>
        ) : headlines.length === 0 ? (
          <Center py={20}>
            <VStack spacing={2}>
              <Text fontSize="2xl">📭</Text>
              <Text fontSize="sm" color="gray.500">No headlines yet</Text>
            </VStack>
          </Center>
        ) : (
          <VStack spacing={8} align="stretch">
            {Object.entries(grouped).map(([date, items]) => (
              <Box key={date} id={toSlug(date)}>
                <Flex align="center" gap={3} mb={4}>
                  <Divider borderColor="gray.200" />
                  <Text
                    fontSize="2xs" fontWeight="bold" color="gray.400"
                    whiteSpace="nowrap" textTransform="uppercase" letterSpacing="widest"
                    flexShrink={0}
                  >
                    {date}
                  </Text>
                  <Divider borderColor="gray.200" />
                </Flex>
                <VStack spacing={3} align="stretch">
                  {items.map(h => <HeadlineCard key={h.id} headline={h} />)}
                </VStack>
              </Box>
            ))}
          </VStack>
        )}

        {/* Infinite scroll sentinel */}
        <Box ref={sentinelRef} pt={8}>
          {isFetchingNextPage && (
            <Center><Spinner size="sm" color="gray.300" /></Center>
          )}
          {!hasNextPage && headlines.length > 0 && (
            <Center>
              <HStack spacing={3} color="gray.300">
                <Divider w="50px" />
                <Text fontSize="xs">you're all caught up</Text>
                <Divider w="50px" />
              </HStack>
            </Center>
          )}
        </Box>
      </Box>
      <AIInsightsDrawer isOpen={isInsightsOpen} onClose={onInsightsClose} />
    </Box>
  );
}
