import React from 'react';
import {
  Drawer, DrawerBody, DrawerHeader, DrawerOverlay, DrawerContent,
  DrawerCloseButton, Box, Text, VStack, Spinner, Center, Divider,
} from '@chakra-ui/react';
import { useQuery } from '@tanstack/react-query';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);

interface Topic {
  title:   string;
  summary: string;
  region:  'International' | 'Malaysia' | 'Singapore';
}

interface SummaryPayload {
  topics: Topic[];
}

interface SummaryRow {
  week_start: string;
  week_end:   string;
  payload:    SummaryPayload;
}

const REGIONS: { key: 'International' | 'Malaysia' | 'Singapore'; label: string; icon: string }[] = [
  { key: 'International', label: 'International', icon: '🌍' },
  { key: 'Singapore',     label: 'Singapore',     icon: '🇸🇬' },
  { key: 'Malaysia',      label: 'Malaysia',       icon: '🇲🇾' },
];

interface Props {
  isOpen:  boolean;
  onClose: () => void;
}

export default function ThisWeekDrawer({ isOpen, onClose }: Props) {
  const { data: summary, isLoading } = useQuery({
    queryKey: ['this-week'],
    queryFn: async (): Promise<SummaryRow | null> => {
      const { data } = await supabase
        .from('weekly_summary')
        .select('week_start, week_end, payload')
        .eq('active', true)
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle();
      return (data as SummaryRow | null);
    },
    enabled: isOpen,
    staleTime: 0,
  });

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

        <DrawerHeader borderBottom="1px solid" borderColor="brand.rule" pb={3} pt={4}>
          <Text
            fontSize="md" fontWeight="700" color="brand.ink" lineHeight="1.2"
            fontFamily="'Noto Serif SC', 'Georgia', serif"
          >
            This Week
          </Text>
          <Text fontSize="xs" color="brand.muted" fontWeight="400" mt={0.5}>
            The most important stories from the past 7 days.
          </Text>
        </DrawerHeader>

        <DrawerBody py={4} overflowY="auto">
          {isLoading ? (
            <Center py={10}>
              <Spinner color="brand.red" size="md" />
            </Center>
          ) : !summary?.payload?.topics?.length ? (
            <Center py={10}>
              <VStack spacing={2}>
                <Text fontSize="2xl">📰</Text>
                <Text fontSize="sm" color="brand.ink" fontWeight="600">Coming soon…</Text>
                <Text fontSize="xs" color="brand.muted" textAlign="center" maxW="240px">
                  The first weekly summary appears after the Monday job runs at 08:00 SGT.
                </Text>
              </VStack>
            </Center>
          ) : (
            <VStack spacing={5} align="stretch">
              {REGIONS.map(({ key, label, icon }) => {
                const topics = summary.payload.topics.filter(t => t.region === key);
                if (!topics.length) return null;
                return (
                  <Box key={key}>
                    {/* Region header */}
                    <Text
                      fontSize="xs" fontWeight="700" color="brand.red"
                      textTransform="uppercase" letterSpacing="wider" mb={2.5}
                    >
                      {icon} {label}
                    </Text>
                    {/* Topics in this region */}
                    <VStack spacing={0} align="stretch">
                      {topics.map((topic, i) => (
                        <Box key={i}>
                          {i > 0 && <Divider borderColor="brand.rule" />}
                          <Box py={2.5}>
                            <Text
                              fontSize="sm" fontWeight="700" color="brand.ink"
                              lineHeight="1.4" mb={1}
                              fontFamily="'Noto Serif SC', 'Georgia', serif"
                            >
                              {topic.title}
                            </Text>
                            <Text fontSize="xs" color="brand.muted" lineHeight="1.6">
                              {topic.summary}
                            </Text>
                          </Box>
                        </Box>
                      ))}
                    </VStack>
                  </Box>
                );
              })}

              <Divider borderColor="brand.rule" />
              <Text fontSize="2xs" color="brand.muted" textAlign="center" pb={2} lineHeight="1.6">
                Updated daily · past 7 days
              </Text>
            </VStack>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}
