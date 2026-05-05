import React, { useEffect, useState } from 'react';
import {
  Box, Container, Flex, Heading, SimpleGrid, Spinner,
  Text, Button, Center, VStack, Divider, Link
} from '@chakra-ui/react';
import { createClient } from '@supabase/supabase-js';
import HeadlineCard from './components/HeadlineCard';

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);

const PAGE_SIZE = 20;

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
      <Box bg="white" borderBottomWidth="1px" borderColor="gray.200" py={5}>
        <Container maxW="container.xl">
          <Heading size="lg" color="gray.800">🗞 Malaysian News</Heading>
          <Text color="gray.500" fontSize="sm" mt={1}>
            Latest from Astro 本地圈 — Chinese headlines with English translations
          </Text>
        </Container>
      </Box>

      <Container maxW="container.xl" pb={12} pt={6}>
        {loading ? (
          <Center py={20}>
            <Spinner size="xl" color="red.500" />
          </Center>
        ) : headlines.length === 0 ? (
          <Center py={20}>
            <VStack spacing={3}>
              <Text fontSize="xl">😶 No headlines yet</Text>
              <Text color="gray.500" fontSize="sm">Run the job to fetch the latest news</Text>
            </VStack>
          </Center>
        ) : (
          <Flex gap={8} align="start">

            {/* Left timeline panel */}
            <Box
              w="160px"
              minW="160px"
              position="sticky"
              top="24px"
              maxH="calc(100vh - 48px)"
              overflowY="auto"
            >
              <Text fontSize="xs" fontWeight="bold" color="gray.400"
                textTransform="uppercase" letterSpacing="wider" mb={3}>
                Dates
              </Text>
              <VStack align="start" spacing={0}>
                {dates.map((date, i) => {
                  const isActive = activeDate === date;
                  const shortDate = new Date(grouped[date][0].published_at)
                    .toLocaleDateString('en-MY', { day: 'numeric', month: 'short', year: 'numeric' });
                  return (
                    <Box key={date} w="100%">
                      <Flex align="center" gap={2} py={2}>
                        <Box
                          w="2px"
                          h="100%"
                          minH="16px"
                          bg={isActive ? 'red.400' : 'gray.200'}
                          borderRadius="full"
                          flexShrink={0}
                        />
                        <Link
                          onClick={() => scrollToDate(date)}
                          fontSize="xs"
                          color={isActive ? 'red.500' : 'gray.500'}
                          fontWeight={isActive ? 'bold' : 'normal'}
                          cursor="pointer"
                          _hover={{ color: 'red.400', textDecoration: 'none' }}
                          lineHeight="1.3"
                        >
                          {shortDate}
                        </Link>
                      </Flex>
                    </Box>
                  );
                })}
              </VStack>
            </Box>

            {/* Main content */}
            <Box flex={1} minW={0}>
              <VStack spacing={10} align="stretch">
                {Object.entries(grouped).map(([date, items]) => (
                  <Box key={date} id={toSlug(date)}>
                    <Text fontSize="xs" fontWeight="bold" color="gray.400"
                      textTransform="uppercase" letterSpacing="wider" mb={3}>
                      {date}
                    </Text>
                    <Divider mb={4} />
                    <SimpleGrid columns={{ base: 1, md: 2, lg: 3 }} spacing={4}>
                      {items.map(h => (
                        <HeadlineCard key={h.id} headline={h} />
                      ))}
                    </SimpleGrid>
                  </Box>
                ))}
              </VStack>

              {hasMore && (
                <Center mt={10}>
                  <Button
                    onClick={() => fetchHeadlines(headlines.length)}
                    isLoading={loadingMore}
                    loadingText="Loading..."
                    colorScheme="red"
                    variant="outline"
                    size="md"
                  >
                    Load more
                  </Button>
                </Center>
              )}

              {!hasMore && headlines.length > 0 && (
                <Center mt={10}>
                  <Text color="gray.400" fontSize="sm">You've reached the end</Text>
                </Center>
              )}
            </Box>

          </Flex>
        )}
      </Container>
    </Box>
  );
}
