import React from 'react';
import {
  Drawer, DrawerBody, DrawerHeader, DrawerOverlay, DrawerContent,
  DrawerCloseButton, Box, Text, VStack, HStack, Spinner,
  Center, Divider,
} from '@chakra-ui/react';
import { useQuery } from '@tanstack/react-query';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);

const CATEGORY_ICONS: Record<string, string> = {
  International: '🌍',
  Malaysia:      '🇲🇾',
  Singapore:     '🇸🇬',
};

interface StatsData {
  totalAllTime: number;
  bySource:     { channel: string; count: number }[];
  byCategory:   { category: string; count: number }[];
  daily:        { label: string; isoDate: string; count: number }[];
}

async function fetchStats(): Promise<StatsData> {
  // ── All-time total ───────────────────────────────────────────────────────────
  const { count: totalAllTime } = await supabase
    .from('headlines')
    .select('*', { count: 'exact', head: true });

  // ── Last 30 days — lightweight fetch for all breakdowns ──────────────────────
  const since = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
  const { data: recent } = await supabase
    .from('headlines')
    .select('published_at, channel, category')
    .gte('published_at', since)
    .lte('published_at', new Date().toISOString())
    .order('published_at', { ascending: false });

  const rows = recent || [];

  // Group by source
  const sourceMap: Record<string, number> = {};
  for (const r of rows) {
    sourceMap[r.channel] = (sourceMap[r.channel] || 0) + 1;
  }
  const bySource = Object.entries(sourceMap)
    .map(([channel, count]) => ({ channel, count }))
    .sort((a, b) => b.count - a.count);

  // Group by category (only the three visible ones)
  const catOrder = ['International', 'Malaysia', 'Singapore'];
  const catMap: Record<string, number> = {};
  for (const r of rows) {
    if (catOrder.includes(r.category)) {
      catMap[r.category] = (catMap[r.category] || 0) + 1;
    }
  }
  const byCategory = catOrder
    .filter(c => catMap[c] !== undefined)
    .map(c => ({ category: c, count: catMap[c] }));

  // Group by day — last 14 days with data
  const dayMap: Record<string, number> = {};
  for (const r of rows) {
    const key = new Date(r.published_at).toLocaleDateString('en-MY', {
      day: 'numeric', month: 'short', weekday: 'short',
    });
    dayMap[key] = (dayMap[key] || 0) + 1;
  }
  // Produce sorted daily entries (newest first), cap at 14
  const daily = Object.entries(dayMap)
    .map(([label, count]) => {
      // Recover ISO date for stable sort from the original rows
      const sample = rows.find(r =>
        new Date(r.published_at).toLocaleDateString('en-MY', {
          day: 'numeric', month: 'short', weekday: 'short',
        }) === label
      );
      return { label, isoDate: sample?.published_at ?? '', count };
    })
    .sort((a, b) => b.isoDate.localeCompare(a.isoDate))
    .slice(0, 14);

  return {
    totalAllTime: totalAllTime ?? 0,
    bySource,
    byCategory,
    daily,
  };
}

interface Props {
  isOpen:  boolean;
  onClose: () => void;
}

export default function StatsDrawer({ isOpen, onClose }: Props) {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: fetchStats,
    enabled: isOpen,
    staleTime: 0,
  });

  const maxDaily = stats ? Math.max(...stats.daily.map(d => d.count), 1) : 1;

  return (
    <Drawer isOpen={isOpen} placement="bottom" onClose={onClose}>
      <DrawerOverlay />
      <DrawerContent maxH="80vh" style={{ maxWidth: "600px", marginLeft: "auto", marginRight: "auto" }} borderTopRadius="lg" bg="brand.paper">
        <DrawerCloseButton color="brand.muted" mt={1} />

        <DrawerHeader borderBottom="1px solid" borderColor="brand.rule" pb={3} pt={4}>
          <Text fontSize="md" fontWeight="700" color="brand.ink" lineHeight="1.2"
            fontFamily="'Noto Serif SC', 'Georgia', serif">
            Statistics
          </Text>
          <Text fontSize="xs" color="brand.muted" fontWeight="400" mt={0.5}>
            Articles scraped and stored across all runs.
          </Text>
        </DrawerHeader>

        <DrawerBody py={4} overflowY="auto">
          {isLoading ? (
            <Center py={10}><Spinner color="brand.red" size="md" /></Center>
          ) : !stats ? (
            <Center py={10}><Text fontSize="sm" color="brand.muted">No data yet.</Text></Center>
          ) : (
            <VStack spacing={5} align="stretch">

              {/* ── Overview ──────────────────────────────────────────────── */}
              <Box>
                <Text fontSize="xs" fontWeight="700" color="brand.red"
                  textTransform="uppercase" letterSpacing="wider" mb={3}>
                  All Time
                </Text>
                <HStack justify="space-between" mb={2}>
                  <Text fontSize="xs" color="brand.muted">Total scraped</Text>
                  <Text fontSize="xs" fontWeight="700" color="brand.ink">
                    {stats.totalAllTime.toLocaleString()}
                  </Text>
                </HStack>
                <Divider borderColor="brand.rule" mb={2} />
                {stats.bySource.map(s => (
                  <HStack key={s.channel} justify="space-between" mb={1.5}>
                    <Text fontSize="xs" color="brand.muted">{s.channel}</Text>
                    <Text fontSize="xs" color="brand.ink">{s.count.toLocaleString()}</Text>
                  </HStack>
                ))}
              </Box>

              <Divider borderColor="brand.rule" />

              {/* ── Last 30 days by category ───────────────────────────────── */}
              <Box>
                <Text fontSize="xs" fontWeight="700" color="brand.red"
                  textTransform="uppercase" letterSpacing="wider" mb={3}>
                  Last 30 Days · By Category
                </Text>
                {stats.byCategory.map(c => (
                  <HStack key={c.category} justify="space-between" mb={1.5}>
                    <HStack spacing={1.5}>
                      <Text fontSize="xs">{CATEGORY_ICONS[c.category]}</Text>
                      <Text fontSize="xs" color="brand.muted">{c.category}</Text>
                    </HStack>
                    <Text fontSize="xs" color="brand.ink">{c.count.toLocaleString()}</Text>
                  </HStack>
                ))}
              </Box>

              <Divider borderColor="brand.rule" />

              {/* ── Daily breakdown ────────────────────────────────────────── */}
              <Box>
                <Text fontSize="xs" fontWeight="700" color="brand.red"
                  textTransform="uppercase" letterSpacing="wider" mb={3}>
                  Daily · Last 14 Days
                </Text>
                <VStack spacing={2} align="stretch">
                  {stats.daily.map(d => (
                    <HStack key={d.isoDate} spacing={3} align="center">
                      {/* Date label — fixed width */}
                      <Text fontSize="2xs" color="brand.muted" flexShrink={0} w="80px">
                        {d.label}
                      </Text>
                      {/* Bar */}
                      <Box flex={1} h="6px" bg="brand.rule" borderRadius="full" overflow="hidden">
                        <Box
                          h="100%"
                          bg="brand.red"
                          borderRadius="full"
                          w={`${Math.round((d.count / maxDaily) * 100)}%`}
                          transition="width 0.3s ease"
                        />
                      </Box>
                      {/* Count */}
                      <Text fontSize="2xs" color="brand.ink" flexShrink={0} w="28px" textAlign="right">
                        {d.count}
                      </Text>
                    </HStack>
                  ))}
                </VStack>
              </Box>

              <Divider borderColor="brand.rule" />
              <Text fontSize="2xs" color="brand.muted" textAlign="center" pb={2} lineHeight="1.6">
                Category and daily counts reflect last 30 days only.
              </Text>

            </VStack>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}
