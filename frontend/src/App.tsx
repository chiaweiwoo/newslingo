import React, { useEffect, useRef, useState } from 'react';
import {
  Box, Flex, Heading, SimpleGrid, Spinner,
  Text, Button, Center, VStack, Divider, Link, HStack, Badge
} from '@chakra-ui/react';
import { createClient } from '@supabase/supabase-js';
import HeadlineCard from './components/HeadlineCard';

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);

const PAGE_SIZE = 100;

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

export default function App() {
  const [headlines, setHeadlines] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [activeDate, setActiveDate] = useState<string>('');
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchHeadlines(0, true);
  }, []);

  async function fetchHeadlines(offset: number, initial = false) {
    initial ? setLoading(true) : setLoadingMore(true);
    const { data } = await supabase
      .from('headlines')
      .select('*')
      .order('published_at', { ascending: false })
      .range(offset, offset + PAGE_SIZE - 1);
    const rows = data || [];
    setHeadlines(prev => initial ? rows : [...prev, ...rows]);
    setHasMore(rows.length === PAGE_SIZE);
    initial ? setLoading(false) : setLoadingMore(false);
  }

  const grouped = groupByDate(headlines);
  const dates = Object.keys(grouped);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container || dates.length === 0) return;

    const onScroll = () => {
      const containerTop = container.getBoundingClientRect().top;
      for (let i = dates.length - 1; i >= 0; i--) {
        const el = document.getElementById(toSlug(dates[i]));
        if (el && el.getBoundingClientRect().top - containerTop <= 24) {
          setActiveDate(dates[i]);
          return;
        }
      }
      setActiveDate(dates[0]);
    };

    container.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => container.removeEventListener('scroll', onScroll);
  }, [dates.join(',')]);

  function scrollToDate(date: string) {
    const section = document.getElementById(toSlug(date));
    const container = scrollRef.current;
    if (section && container) {
      const top = section.getBoundingClientRect().top
        - container.getBoundingClientRect().top
        + container.scrollTop - 24;
      container.scrollTo({ top, behavior: 'smooth' });
    }
  }

  return (
    <Flex direction="column" h={{ base: 'auto', md: '100vh' }} minH="100vh" bg="gray.50">

      {/* Header — static, no sticky needed */}
      <Box bg="gray.900" borderBottom="3px solid" borderColor="red.500" flexShrink={0}>
        <Box maxW="1280px" mx="auto" px={6} py={4}>
          <Heading
            size="lg" color="white" fontWeight="black"
            letterSpacing="-0.5px" fontFamily="'Georgia', serif"
          >
            NewsLingo
          </Heading>
          <Text color="gray.400" fontSize="xs" mt={0.5} letterSpacing="wide">
            中英双语时事 · Malaysian news in Chinese & English
          </Text>
        </Box>
      </Box>

      {/* Body */}
      <Flex flex={1} overflow={{ base: 'visible', md: 'hidden' }} maxW="1280px" mx="auto" w="100%" px={{ base: 4, md: 6 }}>

        {/* Sidebar — hidden on mobile */}
        <Box
          display={{ base: 'none', md: 'block' }}
          w="150px"
          minW="150px"
          py={8}
          pr={6}
          flexShrink={0}
          overflowY="auto"
          sx={{ '&::-webkit-scrollbar': { display: 'none' } }}
        >
          {!loading && dates.length > 0 && (
            <>
              <Text fontSize="2xs" fontWeight="bold" color="gray.400"
                textTransform="uppercase" letterSpacing="widest" mb={4}>
                Timeline
              </Text>
              <Box position="relative">
                <Box
                  position="absolute" left="5px" top="8px" bottom="8px"
                  w="2px" bg="gray.100" borderRadius="full"
                />
                <VStack align="start" spacing={0} position="relative">
                  {dates.map((date) => {
                    const isActive = activeDate === date;
                    const d = new Date(grouped[date][0].published_at);
                    const shortDate = d.toLocaleDateString('en-MY', { day: 'numeric', month: 'short' });
                    const year = d.getFullYear().toString();
                    return (
                      <Flex key={date} align="center" gap={3} py={2}
                        cursor="pointer" w="100%" onClick={() => scrollToDate(date)} role="button">
                        <Box
                          w="12px" h="12px" borderRadius="full" flexShrink={0}
                          bg={isActive ? 'red.500' : 'white'}
                          borderWidth="2px"
                          borderColor={isActive ? 'red.500' : 'gray.300'}
                          transition="all 0.15s"
                          zIndex={1}
                        />
                        <Box>
                          <Text
                            fontSize="xs"
                            color={isActive ? 'red.600' : 'gray.500'}
                            fontWeight={isActive ? 'bold' : 'normal'}
                            lineHeight="1.2"
                            _hover={{ color: 'red.500' }}
                            transition="color 0.1s"
                          >
                            {shortDate}
                          </Text>
                          <Text fontSize="2xs" color="gray.400" lineHeight="1">{year}</Text>
                        </Box>
                      </Flex>
                    );
                  })}
                </VStack>
              </Box>
            </>
          )}
        </Box>

        {/* Main content */}
        <Box flex={1} overflowY={{ base: 'visible', md: 'auto' }} ref={scrollRef} minW={0}
          sx={{ '&::-webkit-scrollbar': { width: '6px' }, '&::-webkit-scrollbar-thumb': { bg: 'gray.200', borderRadius: 'full' } }}>

          {loading ? (
            <Center py={24}>
              <VStack spacing={4}>
                <Spinner size="xl" color="red.500" thickness="3px" />
                <Text color="gray.400" fontSize="sm">Loading headlines…</Text>
              </VStack>
            </Center>
          ) : headlines.length === 0 ? (
            <Center py={24}>
              <VStack spacing={3}>
                <Text fontSize="2xl">📭</Text>
                <Text fontWeight="semibold" color="gray.600">No headlines yet</Text>
                <Text color="gray.400" fontSize="sm">Run the job to fetch the latest news</Text>
              </VStack>
            </Center>
          ) : (
            <Box py={8} pr={2}>
              <VStack spacing={12} align="stretch">
                {Object.entries(grouped).map(([date, items]) => {
                  const malaysia = items.filter(h => h.category === 'Malaysia');
                  const international = items.filter(h => h.category === 'International');
                  return (
                    <Box key={date} id={toSlug(date)}>
                      <Flex align="center" gap={4} mb={6}>
                        <Divider borderColor="gray.200" />
                        <Text
                          fontSize="xs" fontWeight="bold" color="gray.500"
                          whiteSpace="nowrap" textTransform="uppercase" letterSpacing="widest"
                          flexShrink={0}
                        >
                          {date}
                        </Text>
                        <Divider borderColor="gray.200" />
                      </Flex>

                      <SimpleGrid columns={{ base: 1, md: 2 }} spacing={8}>
                        <Box>
                          <Flex align="center" justify="space-between"
                            mb={4} pb={3} borderBottomWidth="2px" borderColor="red.200">
                            <HStack spacing={2}>
                              <Text>🇲🇾</Text>
                              <Text fontSize="sm" fontWeight="bold" color="red.600" letterSpacing="wide">
                                Malaysia
                              </Text>
                            </HStack>
                            <Badge colorScheme="red" variant="subtle" borderRadius="full" fontSize="xs" px={2}>
                              {malaysia.length}
                            </Badge>
                          </Flex>
                          <VStack spacing={4} align="stretch">
                            {malaysia.map(h => <HeadlineCard key={h.id} headline={h} />)}
                            {malaysia.length === 0 && (
                              <Text fontSize="xs" color="gray.300" fontStyle="italic" py={4} textAlign="center">
                                No local news this day
                              </Text>
                            )}
                          </VStack>
                        </Box>

                        <Box>
                          <Flex align="center" justify="space-between"
                            mb={4} pb={3} borderBottomWidth="2px" borderColor="blue.200">
                            <HStack spacing={2}>
                              <Text>🌍</Text>
                              <Text fontSize="sm" fontWeight="bold" color="blue.600" letterSpacing="wide">
                                International
                              </Text>
                            </HStack>
                            <Badge colorScheme="blue" variant="subtle" borderRadius="full" fontSize="xs" px={2}>
                              {international.length}
                            </Badge>
                          </Flex>
                          <VStack spacing={4} align="stretch">
                            {international.map(h => <HeadlineCard key={h.id} headline={h} />)}
                            {international.length === 0 && (
                              <Text fontSize="xs" color="gray.300" fontStyle="italic" py={4} textAlign="center">
                                No international news this day
                              </Text>
                            )}
                          </VStack>
                        </Box>
                      </SimpleGrid>
                    </Box>
                  );
                })}
              </VStack>

              {hasMore && (
                <Center mt={12}>
                  <Button
                    onClick={() => fetchHeadlines(headlines.length)}
                    isLoading={loadingMore}
                    loadingText="Loading…"
                    colorScheme="red"
                    variant="outline"
                    size="md"
                    borderRadius="full"
                    px={8}
                  >
                    Load more
                  </Button>
                </Center>
              )}

              {!hasMore && headlines.length > 0 && (
                <Center mt={12}>
                  <HStack spacing={3} color="gray.300">
                    <Divider w="60px" />
                    <Text fontSize="xs">you've caught up</Text>
                    <Divider w="60px" />
                  </HStack>
                </Center>
              )}
            </Box>
          )}
        </Box>
      </Flex>
    </Flex>
  );
}
