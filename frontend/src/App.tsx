import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  Box, Flex, Heading, Link, Spinner, Text, VStack, Divider, HStack, Center,
  useDisclosure, useColorMode,
  Menu, MenuButton, MenuDivider, MenuGroup, MenuList, MenuItem,
} from '@chakra-ui/react';
import { useFontSize } from './contexts/FontSizeContext';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { createClient } from '@supabase/supabase-js';
import AboutDrawer from './components/AboutDrawer';
import CostsDrawer from './components/CostsDrawer';
import HeadlineCard from './components/HeadlineCard';
import QuizDrawer from './components/QuizDrawer';
import SearchBar from './components/SearchBar';
import StatsDrawer from './components/StatsDrawer';
import ThisWeekDrawer from './components/ThisWeekDrawer';

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);

const PAGE_SIZE = 20;
type Category = 'International' | 'Malaysia' | 'Singapore';

const TABS: { label: string; value: Category; icon: string }[] = [
  { label: 'International', value: 'International', icon: '🌍' },
  { label: 'Singapore',     value: 'Singapore',     icon: '🇸🇬' },
  { label: 'Malaysia',      value: 'Malaysia',      icon: '🇲🇾' },
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
  const { colorMode, toggleColorMode }   = useColorMode();
  const { fontSize, increase, decrease } = useFontSize();
  const [activeTab, setActiveTab]        = useState<Category>('International');
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const headerRef   = useRef<HTMLDivElement>(null);
  const { isOpen: isAboutOpen,     onOpen: onAboutOpen,     onClose: onAboutClose     } = useDisclosure();
  const { isOpen: isThisWeekOpen,  onOpen: onThisWeekOpen,  onClose: onThisWeekClose  } = useDisclosure();
  const { isOpen: isQuizOpen,      onOpen: onQuizOpen,      onClose: onQuizClose      } = useDisclosure();
  const { isOpen: isStatsOpen,     onOpen: onStatsOpen,     onClose: onStatsClose     } = useDisclosure();
  const { isOpen: isCostsOpen,     onOpen: onCostsOpen,     onClose: onCostsClose     } = useDisclosure();

  // Visit tracking — fire once on mount
  useEffect(() => {
    const track = async () => {
      try {
        // ipapi.co returns ip + country in one call
        const geo = await fetch('https://ipapi.co/json/').then(r => r.json());
        const ua = navigator.userAgent;
        await supabase.from('visits').insert({
          ip:         geo.ip,
          country:    geo.country_name ?? null,
          user_agent: ua,
          is_mobile:  /Mobi|Android/i.test(ua),
        });
      } catch (_) {}
    };
    track();
  }, []);

  // Last job execution time
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
      let q = supabase
        .from('headlines')
        .select('*')
        .eq('category', activeTab)
        .lte('published_at', new Date().toISOString())   // never show future-dated articles
        .order('published_at', { ascending: false });
      // Exclude Zaobao China + SEA sections — out of scope (scraper also skips them; this covers existing DB rows)
      if (activeTab === 'International') {
        q = q
          .not('source_url', 'like', '%/news/china/%')
          .not('source_url', 'like', '%/news/sea/%');
      }
      const { data } = await q.range(pageParam, pageParam + PAGE_SIZE - 1);
      return data || [];
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) =>
      lastPage.length < PAGE_SIZE ? undefined : allPages.flat().length,
  });

  // Write the navbar height directly into a CSS variable — no React state, no
  // re-render cycle. The sticky date labels read `--header-h` so the correct
  // offset is applied from the very first browser paint.
  useLayoutEffect(() => {
    const el = headerRef.current;
    if (!el) return;
    const update = () =>
      document.documentElement.style.setProperty('--header-h', `${el.offsetHeight}px`);
    update();                          // synchronous — fires before browser paints
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Debounced search
  useEffect(() => {
    const q = searchQuery.trim();
    if (!q) { setSearchResults([]); return; }
    setSearchLoading(true);
    const timer = setTimeout(async () => {
      const { data } = await supabase
        .from('headlines')
        .select('*')
        .or(`title_zh.ilike.%${q}%,title_en.ilike.%${q}%`)
        .order('published_at', { ascending: false })
        .limit(50);
      setSearchResults(data || []);
      setSearchLoading(false);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const handleSearchClose = () => {
    setSearchOpen(false);
    setSearchQuery('');
    setSearchResults([]);
  };

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
    <Box minH="100vh" bg="brand.paper">

      {/* Sticky header */}
      <Box
        ref={headerRef}
        position="sticky" top={0} zIndex={100}
        bg="#111111" borderBottom="3px solid" borderColor="brand.red"
      >
        <Box maxW="600px" mx="auto" px={4}>

          {/* Title row — or search bar when active */}
          {searchOpen ? (
            <SearchBar
              query={searchQuery}
              onChange={setSearchQuery}
              onClose={handleSearchClose}
              results={searchResults}
              isLoading={searchLoading}
            />
          ) : (
          <Flex align="center" justify="space-between" pt={3} pb={2}>
            <Heading
              size="md" color="white" fontWeight="700"
              letterSpacing="-0.3px"
              fontFamily="'Noto Serif SC', 'Georgia', serif"
            >
              NewsLingo
            </Heading>
            <HStack spacing={3} align="center">
              {/* Search icon */}
              <Box
                as="button"
                onClick={() => setSearchOpen(true)}
                color="gray.500"
                _hover={{ color: 'white' }}
                transition="color 0.15s"
                lineHeight="1"
                aria-label="Search"
              >
                <svg width="15" height="15" viewBox="0 0 15 15" fill="none"
                  stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                  <circle cx="6.5" cy="6.5" r="4.5" />
                  <line x1="10" y1="10" x2="14" y2="14" />
                </svg>
              </Box>
              {/* Top Stories icon — 4-pointed sparkle (8-point polygon) */}
              <Box
                as="button"
                onClick={onThisWeekOpen}
                color="gray.500"
                _hover={{ color: 'white' }}
                transition="color 0.15s"
                lineHeight="1"
                aria-label="Top Stories"
              >
                <svg width="15" height="15" viewBox="0 0 15 15" fill="currentColor">
                  <path d="M7.5,1 L8.6,6.4 L14,7.5 L8.6,8.6 L7.5,14 L6.4,8.6 L1,7.5 L6.4,6.4 Z" />
                </svg>
              </Box>
              {/* Translation Quiz icon — pencil on paper */}
              <Box
                as="button"
                onClick={onQuizOpen}
                color="gray.500"
                _hover={{ color: 'white' }}
                transition="color 0.15s"
                lineHeight="1"
                aria-label="Translation Quiz"
              >
                <svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="1.5" width="9" height="12" rx="1" />
                  <line x1="4.5" y1="5" x2="8.5" y2="5" />
                  <line x1="4.5" y1="7.5" x2="8.5" y2="7.5" />
                  <line x1="4.5" y1="10" x2="6.5" y2="10" />
                  <path d="M10 9.5 L13 6.5 L13 9.5 L10 12.5 L10 9.5 Z" fill="currentColor" stroke="none" />
                </svg>
              </Box>
              {/* Overflow menu */}
              <Menu placement="bottom-end">
                <MenuButton
                  as={Box}
                  cursor="pointer"
                  color="gray.500"
                  _hover={{ color: 'white' }}
                  transition="color 0.15s"
                  fontSize="lg"
                  lineHeight="1"
                  letterSpacing="0.1em"
                  pb="2px"
                  userSelect="none"
                >
                  ···
                </MenuButton>
                <MenuList
                  bg="brand.card"
                  border="1px solid"
                  borderColor="brand.rule"
                  borderRadius="sm"
                  boxShadow="sm"
                  minW="200px"
                  py={1}
                  zIndex={200}
                >
                  {/* About */}
                  <MenuItem
                    onClick={onAboutOpen}
                    fontSize="xs"
                    color="brand.ink"
                    bg="brand.card"
                    _hover={{ bg: 'brand.paper' }}
                    _focus={{ bg: 'brand.paper' }}
                    px={4} py={2.5}
                  >
                    About
                  </MenuItem>

                  <MenuDivider borderColor="brand.rule" my={1} />

                  {/* Preferences group — font size + dark mode */}
                  <MenuGroup
                    title="Preferences"
                    ml={4} mt={1} mb={0}
                    fontSize="2xs"
                    fontWeight="700"
                    color="brand.muted"
                    textTransform="uppercase"
                    letterSpacing="widest"
                  >
                    {/* Font size row — Box buttons don't close the menu */}
                    <Box px={4} py={2.5}>
                      <HStack justify="space-between" align="center">
                        <Text fontSize="xs" color="brand.muted">Font size</Text>
                        <HStack spacing={2} align="center">
                          <Box
                            as="button"
                            fontSize="xs" fontWeight="700" lineHeight="1"
                            color={fontSize === 'sm' ? 'brand.muted' : 'brand.ink'}
                            _hover={{ color: 'brand.red' }}
                            transition="color 0.15s"
                            onClick={decrease}
                            aria-label="Decrease font size"
                          >
                            A–
                          </Box>
                          {/* Current level indicator — 3 dots */}
                          <HStack spacing="3px">
                            {(['sm', 'md', 'lg'] as const).map(s => (
                              <Box key={s} w="5px" h="5px" borderRadius="full"
                                bg={fontSize === s ? 'brand.red' : 'brand.rule'}
                                transition="background 0.15s"
                              />
                            ))}
                          </HStack>
                          <Box
                            as="button"
                            fontSize="xs" fontWeight="700" lineHeight="1"
                            color={fontSize === 'lg' ? 'brand.muted' : 'brand.ink'}
                            _hover={{ color: 'brand.red' }}
                            transition="color 0.15s"
                            onClick={increase}
                            aria-label="Increase font size"
                          >
                            A+
                          </Box>
                        </HStack>
                      </HStack>
                    </Box>
                    {/* Dark mode row */}
                    <Box px={4} py={2.5}>
                      <HStack justify="space-between" align="center">
                        <Text fontSize="xs" color="brand.muted">Dark mode</Text>
                        <Box
                          as="button"
                          onClick={toggleColorMode}
                          color="brand.muted"
                          _hover={{ color: 'brand.ink' }}
                          transition="color 0.15s"
                          lineHeight="1"
                          aria-label="Toggle dark mode"
                        >
                          {colorMode === 'light' ? (
                            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"
                              stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                              <path d="M11.5 8A5.5 5.5 0 0 1 6 2.5a5.5 5.5 0 1 0 5.5 5.5z" />
                            </svg>
                          ) : (
                            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"
                              stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                              <circle cx="7" cy="7" r="2.5" />
                              <path d="M7 1v1.5M7 11.5V13M1 7h1.5M11.5 7H13M2.9 2.9l1.1 1.1M10 10l1.1 1.1M2.9 11.1l1.1-1.1M10 4l1.1-1.1" />
                            </svg>
                          )}
                        </Box>
                      </HStack>
                    </Box>
                  </MenuGroup>

                  <MenuDivider borderColor="brand.rule" my={1} />

                  <MenuDivider borderColor="brand.rule" my={1} />

                  {/* Data group */}
                  <MenuGroup
                    title="Data"
                    ml={4} mt={1} mb={0}
                    fontSize="2xs"
                    fontWeight="700"
                    color="brand.muted"
                    textTransform="uppercase"
                    letterSpacing="widest"
                  >
                    <MenuItem
                      onClick={onStatsOpen}
                      fontSize="xs"
                      color="brand.ink"
                      bg="brand.card"
                      _hover={{ bg: 'brand.paper' }}
                      _focus={{ bg: 'brand.paper' }}
                      px={4} py={2.5}
                    >
                      Statistics
                    </MenuItem>
                    <MenuItem
                      onClick={onCostsOpen}
                      fontSize="xs"
                      color="brand.ink"
                      bg="brand.card"
                      _hover={{ bg: 'brand.paper' }}
                      _focus={{ bg: 'brand.paper' }}
                      px={4} py={2.5}
                    >
                      AI Costs
                    </MenuItem>
                  </MenuGroup>

                  {/* Footnotes — last updated + author */}
                  <MenuDivider borderColor="brand.rule" my={1} />
                  <Box px={4} py={2}>
                    <VStack spacing={1} align="stretch">
                      {latestDate && (
                        <Text fontSize="2xs" color="brand.muted">
                          Updated {timeAgo(latestDate)}
                        </Text>
                      )}
                      <HStack spacing={1.5}>
                        <Text fontSize="2xs" color="brand.muted">Built by Woo Chia Wei</Text>
                        <Link
                          href="https://github.com/chiaweiwoo"
                          isExternal
                          fontSize="2xs"
                          color="brand.muted"
                          _hover={{ color: 'brand.ink' }}
                          transition="color 0.15s"
                        >
                          GitHub ↗
                        </Link>
                      </HStack>
                    </VStack>
                  </Box>
                </MenuList>
              </Menu>
            </HStack>
          </Flex>

          )}

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
                  onClick={() => { setActiveTab(tab.value); if (searchOpen) handleSearchClose(); }}
                  borderBottom="2px solid"
                  borderColor={active ? 'brand.red' : 'transparent'}
                  color={active ? 'white' : 'gray.500'}
                  fontSize="xs"
                  fontWeight={active ? '700' : '400'}
                  letterSpacing="0.02em"
                  transition="all 0.15s"
                  userSelect="none"
                >
                  <Text as="span" mr={1}>{tab.icon}</Text>
                  {tab.label}
                </Box>
              );
            })}
          </Flex>
        </Box>
      </Box>

      {/* Feed */}
      <Box maxW="600px" mx="auto" px={3} pb={16} pt={4}>
        {isLoading ? (
          <Center py={20}>
            <VStack spacing={3}>
              <Spinner size="lg" color="brand.red" thickness="3px" />
              <Text fontSize="sm" color="brand.muted">Loading…</Text>
            </VStack>
          </Center>
        ) : headlines.length === 0 ? (
          <Center py={20}>
            <VStack spacing={2}>
              <Text fontSize="2xl">📭</Text>
              <Text fontSize="sm" color="brand.muted">No headlines yet</Text>
            </VStack>
          </Center>
        ) : (
          <VStack spacing={6} align="stretch">
            {Object.entries(grouped).map(([date, items]) => (
              <Box key={date} id={toSlug(date)}>
                {/* Date separator — sticky, sits flush below navbar while scrolling */}
                <Flex
                  position="sticky"
                  style={{ top: 'var(--header-h, 80px)' }}
                  zIndex={50}
                  bg="brand.paper"
                  align="center"
                  gap={3}
                  pt={2} pb={2}
                  mb={1}
                >
                  <Divider borderColor="brand.rule" />
                  <Text
                    fontSize="2xs" fontWeight="700" color="brand.muted"
                    whiteSpace="nowrap" textTransform="uppercase" letterSpacing="widest"
                    flexShrink={0}
                  >
                    {date}
                  </Text>
                  <Divider borderColor="brand.rule" />
                </Flex>
                <VStack spacing={2} align="stretch">
                  {items.map(h => <HeadlineCard key={h.id} headline={h} />)}
                </VStack>
              </Box>
            ))}
          </VStack>
        )}

        {/* Infinite scroll sentinel */}
        <Box ref={sentinelRef} pt={8}>
          {isFetchingNextPage && (
            <Center><Spinner size="sm" color="brand.muted" /></Center>
          )}
          {!hasNextPage && headlines.length > 0 && (
            <Center>
              <HStack spacing={3} color="brand.rule">
                <Divider w="50px" />
                <Text fontSize="xs" color="brand.muted">you're all caught up</Text>
                <Divider w="50px" />
              </HStack>
            </Center>
          )}
        </Box>
      </Box>

      <AboutDrawer     isOpen={isAboutOpen}    onClose={onAboutClose} />
      <ThisWeekDrawer  isOpen={isThisWeekOpen} onClose={onThisWeekClose} />
      <QuizDrawer      isOpen={isQuizOpen}     onClose={onQuizClose} />
      <StatsDrawer     isOpen={isStatsOpen}    onClose={onStatsClose} />
      <CostsDrawer     isOpen={isCostsOpen}    onClose={onCostsClose} />
    </Box>
  );
}
