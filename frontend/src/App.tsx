import React, { useEffect, useState } from 'react';
import {
  Box, Container, Flex, Heading, SimpleGrid, Spinner,
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

  function scrollToDate(date: string) {
    const el = document.getElementById(toSlug(date));
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setActiveDate(date);
    }
  }

  return (
    <Box minH="100vh" bg="gray.50">

      {/* Header */}
      <Box bg="gray.900" borderBottom="3px solid" borderColor="red.500">
        <Container maxW="container.xl" py={5}>
          <Flex align="center" justify="space-between">
            <Box>
              <Heading
                size="lg" color="white" fontWeight="black"
                letterSpacing="-0.5px" fontFamily="'Georgia', serif"
              >
                NewsLingo
              </Heading>
              <Text color="gray.400" fontSize="xs" mt={1} letterSpacing="wide">
                中英双语时事 · Malaysian news in Chinese & English
              </Text>
            </Box>
            <Text color="gray.600" fontSize="xs" display={{ base: 'none', md: 'block' }}>
              Source: Astro 本地圈
            </Text>
          </Flex>
        </Container>
      </Box>

      <Container maxW="container.xl" pb={16} pt={8}>
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
          <Flex gap={10} align="start">

            {/* Timeline sidebar */}
            <Box
              w="140px"
              minW="140px"
              position="sticky"
              top="24px"
              maxH="calc(100vh - 48px)"
              overflowY="auto"
              sx={{ '&::-webkit-scrollbar': { display: 'none' } }}
            >
              <Text fontSize="2xs" fontWeight="bold" color="gray.400"
                textTransform="uppercase" letterSpacing="widest" mb={4}>
                Timeline
              </Text>

              <Box position="relative">
                {/* Continuous vertical rail */}
                <Box
                  position="absolute"
                  left="5px"
                  top="8px"
                  bottom="8px"
                  w="2px"
                  bg="gray.100"
                  borderRadius="full"
                />

                <VStack align="start" spacing={0} position="relative">
                  {dates.map((date) => {
                    const isActive = activeDate === date;
                    const shortDate = new Date(grouped[date][0].published_at)
                      .toLocaleDateString('en-MY', { day: 'numeric', month: 'short' });
                    const year = new Date(grouped[date][0].published_at)
                      .getFullYear().toString();
                    return (
                      <Flex
                        key={date}
                        align="center"
                        gap={3}
                        py={2}
                        cursor="pointer"
                        w="100%"
                        onClick={() => scrollToDate(date)}
                        role="button"
                      >
                        <Box
                          w="12px"
                          h="12px"
                          borderRadius="full"
                          flexShrink={0}
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
            </Box>

            {/* Main content */}
            <Box flex={1} minW={0}>
              <VStack spacing={12} align="stretch">
                {Object.entries(grouped).map(([date, items]) => {
                  const malaysia = items.filter(h => h.category === 'Malaysia');
                  const international = items.filter(h => h.category === 'International');
                  return (
                    <Box key={date} id={toSlug(date)}>

                      {/* Date divider */}
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

                        {/* Malaysia column */}
                        <Box>
                          <Flex align="center" justify="space-between"
                            mb={4} pb={3} borderBottomWidth="2px" borderColor="red.200">
                            <HStack spacing={2}>
                              <Text fontSize="base">🇲🇾</Text>
                              <Text fontSize="sm" fontWeight="bold" color="red.600"
                                letterSpacing="wide">
                                Malaysia
                              </Text>
                            </HStack>
                            <Badge colorScheme="red" variant="subtle" borderRadius="full"
                              fontSize="xs" px={2}>
                              {malaysia.length}
                            </Badge>
                          </Flex>
                          <VStack spacing={4} align="stretch">
                            {malaysia.map(h => <HeadlineCard key={h.id} headline={h} />)}
                            {malaysia.length === 0 && (
                              <Text fontSize="xs" color="gray.300" fontStyle="italic" py={4}
                                textAlign="center">
                                No local news this day
                              </Text>
                            )}
                          </VStack>
                        </Box>

                        {/* International column */}
                        <Box>
                          <Flex align="center" justify="space-between"
                            mb={4} pb={3} borderBottomWidth="2px" borderColor="blue.200">
                            <HStack spacing={2}>
                              <Text fontSize="base">🌍</Text>
                              <Text fontSize="sm" fontWeight="bold" color="blue.600"
                                letterSpacing="wide">
                                International
                              </Text>
                            </HStack>
                            <Badge colorScheme="blue" variant="subtle" borderRadius="full"
                              fontSize="xs" px={2}>
                              {international.length}
                            </Badge>
                          </Flex>
                          <VStack spacing={4} align="stretch">
                            {international.map(h => <HeadlineCard key={h.id} headline={h} />)}
                            {international.length === 0 && (
                              <Text fontSize="xs" color="gray.300" fontStyle="italic" py={4}
                                textAlign="center">
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

          </Flex>
        )}
      </Container>
    </Box>
  );
}
