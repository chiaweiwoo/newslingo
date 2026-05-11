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

interface TrafficData {
  total:       number;
  mobileCount: number;
  daily:       { label: string; isoDate: string; count: number }[];
  countries:   { country: string; count: number }[];
  hasCountry:  boolean;
}

async function fetchTraffic(): Promise<TrafficData> {
  const since = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();

  const { data: rows } = await supabase
    .from('visits')
    .select('visited_at, is_mobile, country')
    .gte('visited_at', since)
    .order('visited_at', { ascending: false });

  const visits = rows || [];

  // Daily counts (last 14 days)
  const dayMap: Record<string, { count: number; iso: string }> = {};
  for (const r of visits) {
    const label = new Date(r.visited_at).toLocaleDateString('en-MY', {
      day: 'numeric', month: 'short', weekday: 'short',
    });
    if (!dayMap[label]) dayMap[label] = { count: 0, iso: r.visited_at };
    dayMap[label].count += 1;
  }
  const daily = Object.entries(dayMap)
    .map(([label, { count, iso }]) => ({ label, isoDate: iso, count }))
    .sort((a, b) => b.isoDate.localeCompare(a.isoDate))
    .slice(0, 14);

  // Mobile vs desktop
  const mobileCount = visits.filter(r => r.is_mobile).length;

  // Visits per country
  const countryMap: Record<string, number> = {};
  let hasCountry = false;
  for (const r of visits) {
    if (r.country) {
      hasCountry = true;
      countryMap[r.country] = (countryMap[r.country] || 0) + 1;
    }
  }
  const countries = Object.entries(countryMap)
    .map(([country, count]) => ({ country, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 10);

  return { total: visits.length, mobileCount, daily, countries, hasCountry };
}

interface Props {
  isOpen:  boolean;
  onClose: () => void;
}

export default function TrafficDrawer({ isOpen, onClose }: Props) {
  const { data: traffic, isLoading } = useQuery({
    queryKey: ['traffic'],
    queryFn: fetchTraffic,
    enabled: isOpen,
    staleTime: 0,
  });

  const maxDaily = traffic ? Math.max(...traffic.daily.map(d => d.count), 1) : 1;
  const mobilePercent = traffic && traffic.total > 0
    ? Math.round((traffic.mobileCount / traffic.total) * 100)
    : 0;

  return (
    <Drawer isOpen={isOpen} placement="bottom" onClose={onClose}>
      <DrawerOverlay />
      <DrawerContent maxH="80vh" style={{ maxWidth: "600px", marginLeft: "auto", marginRight: "auto" }} borderTopRadius="lg" bg="brand.paper">
        <DrawerCloseButton color="brand.muted" mt={1} />

        <DrawerHeader borderBottom="1px solid" borderColor="brand.rule" pb={3} pt={4}>
          <Text fontSize="md" fontWeight="700" color="brand.ink" lineHeight="1.2"
            fontFamily="'Noto Serif SC', 'Georgia', serif">
            Web Traffic
          </Text>
          <Text fontSize="xs" color="brand.muted" fontWeight="400" mt={0.5}>
            Visits in the last 30 days.
          </Text>
        </DrawerHeader>

        <DrawerBody py={4} overflowY="auto">
          {isLoading ? (
            <Center py={10}><Spinner color="brand.red" size="md" /></Center>
          ) : !traffic ? (
            <Center py={10}><Text fontSize="sm" color="brand.muted">No data yet.</Text></Center>
          ) : (
            <VStack spacing={5} align="stretch">

              {/* ── Overview ──────────────────────────────────────────────── */}
              <Box>
                <Text fontSize="xs" fontWeight="700" color="brand.red"
                  textTransform="uppercase" letterSpacing="wider" mb={3}>
                  Last 30 Days
                </Text>
                <HStack justify="space-between" mb={1.5}>
                  <Text fontSize="xs" color="brand.muted">Total visits</Text>
                  <Text fontSize="xs" fontWeight="700" color="brand.ink">
                    {traffic.total.toLocaleString()}
                  </Text>
                </HStack>
                <HStack justify="space-between" mb={1.5}>
                  <Text fontSize="xs" color="brand.muted">Mobile</Text>
                  <Text fontSize="xs" color="brand.ink">
                    {traffic.mobileCount} <Text as="span" color="brand.muted">({mobilePercent}%)</Text>
                  </Text>
                </HStack>
                <HStack justify="space-between">
                  <Text fontSize="xs" color="brand.muted">Desktop</Text>
                  <Text fontSize="xs" color="brand.ink">
                    {traffic.total - traffic.mobileCount}{' '}
                    <Text as="span" color="brand.muted">({100 - mobilePercent}%)</Text>
                  </Text>
                </HStack>
              </Box>

              <Divider borderColor="brand.rule" />

              {/* ── Daily movement ────────────────────────────────────────── */}
              <Box>
                <Text fontSize="xs" fontWeight="700" color="brand.red"
                  textTransform="uppercase" letterSpacing="wider" mb={3}>
                  Daily · Last 14 Days
                </Text>
                {traffic.daily.length === 0 ? (
                  <Text fontSize="xs" color="brand.muted">No visits yet.</Text>
                ) : (
                  <VStack spacing={2} align="stretch">
                    {traffic.daily.map(d => (
                      <HStack key={d.isoDate} spacing={3} align="center">
                        <Text fontSize="2xs" color="brand.muted" flexShrink={0} w="80px">
                          {d.label}
                        </Text>
                        <Box flex={1} h="6px" bg="brand.rule" borderRadius="full" overflow="hidden">
                          <Box
                            h="100%"
                            bg="brand.red"
                            borderRadius="full"
                            w={`${Math.round((d.count / maxDaily) * 100)}%`}
                            transition="width 0.3s ease"
                          />
                        </Box>
                        <Text fontSize="2xs" color="brand.ink" flexShrink={0} w="28px" textAlign="right">
                          {d.count}
                        </Text>
                      </HStack>
                    ))}
                  </VStack>
                )}
              </Box>

              <Divider borderColor="brand.rule" />

              {/* ── Countries ─────────────────────────────────────────────── */}
              <Box>
                <Text fontSize="xs" fontWeight="700" color="brand.red"
                  textTransform="uppercase" letterSpacing="wider" mb={3}>
                  Countries
                </Text>
                {!traffic.hasCountry ? (
                  <Text fontSize="xs" color="brand.muted" lineHeight="1.6">
                    Country data will appear after your next visit —
                    older rows were recorded before geo-tracking was added.
                  </Text>
                ) : traffic.countries.length === 0 ? (
                  <Text fontSize="xs" color="brand.muted">No country data yet.</Text>
                ) : (
                  <VStack spacing={1.5} align="stretch">
                    {/* Column headers */}
                    <HStack justify="space-between" mb={0.5}>
                      <Text fontSize="2xs" fontWeight="700" color="brand.muted"
                        textTransform="uppercase" letterSpacing="wider">
                        Country
                      </Text>
                      <Text fontSize="2xs" fontWeight="700" color="brand.muted"
                        textTransform="uppercase" letterSpacing="wider">
                        Visits
                      </Text>
                    </HStack>
                    <Divider borderColor="brand.rule" />
                    {traffic.countries.map(c => (
                      <HStack key={c.country} justify="space-between">
                        <Text fontSize="xs" color="brand.muted">{c.country}</Text>
                        <Text fontSize="xs" color="brand.ink">{c.count}</Text>
                      </HStack>
                    ))}
                  </VStack>
                )}
              </Box>

              <Divider borderColor="brand.rule" />
              <Text fontSize="2xs" color="brand.muted" textAlign="center" pb={2} lineHeight="1.6">
                Each page load counts as one visit.
              </Text>

            </VStack>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}
