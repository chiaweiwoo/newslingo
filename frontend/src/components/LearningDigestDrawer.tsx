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

interface RegionDigest {
  summary: string;
  examples: Array<{ zh: string; wrong: string; correct: string }>;
}

interface DigestPayload {
  international: RegionDigest;
  malaysia:      RegionDigest;
  singapore:     RegionDigest;
}

interface DigestRow {
  created_at: string;
  digest_at:  string;
  payload:    DigestPayload;
}

const REGIONS: { key: keyof DigestPayload; label: string }[] = [
  { key: 'international', label: 'International' },
  { key: 'malaysia',      label: 'Malaysia' },
  { key: 'singapore',     label: 'Singapore' },
];

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const m = Math.floor(seconds / 60); if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60); if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24); return `${d}d ago`;
}

interface Props {
  isOpen:  boolean;
  onClose: () => void;
}

export default function LearningDigestDrawer({ isOpen, onClose }: Props) {
  const { data: digest, isLoading } = useQuery({
    queryKey: ['learning-digest'],
    queryFn: async (): Promise<DigestRow | null> => {
      const { data } = await supabase
        .from('learning_digest')
        .select('created_at, digest_at, payload')
        .eq('active', true)
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle();
      return (data as DigestRow | null);
    },
    enabled: isOpen,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <Drawer isOpen={isOpen} placement="bottom" onClose={onClose}>
      <DrawerOverlay />
      <DrawerContent maxH="80vh" borderTopRadius="lg" bg="brand.paper">
        <DrawerCloseButton color="brand.muted" mt={1} />

        <DrawerHeader borderBottom="1px solid" borderColor="brand.rule" pb={3} pt={4}>
          <HStack spacing={2.5} align="start">
            <Box
              px={1.5} py="2px" mt="3px"
              border="1px solid" borderColor="brand.red"
              borderRadius="sm" flexShrink={0}
            >
              <Text fontSize="2xs" fontWeight="700" letterSpacing="widest"
                color="brand.red" textTransform="uppercase">
                AI
              </Text>
            </Box>
            <Box>
              <Text fontSize="md" fontWeight="700" color="brand.ink" lineHeight="1.2"
                fontFamily="'Noto Serif SC', 'Georgia', serif">
                Learning Digest
              </Text>
              <Text fontSize="xs" color="brand.muted" fontWeight="400" mt={0.5}>
                A daily summary of what the AI has been learning from its translation mistakes.
              </Text>
            </Box>
          </HStack>
        </DrawerHeader>

        <DrawerBody py={4} overflowY="auto">
          {isLoading ? (
            <Center py={10}>
              <Spinner color="brand.red" size="md" />
            </Center>
          ) : !digest ? (
            <Center py={10}>
              <VStack spacing={2}>
                <Text fontSize="2xl">🌱</Text>
                <Text fontSize="sm" color="brand.ink" fontWeight="600">Still learning…</Text>
                <Text fontSize="xs" color="brand.muted" textAlign="center" maxW="240px">
                  The first digest will appear after the daily job runs at 08:00 SGT.
                </Text>
              </VStack>
            </Center>
          ) : (
            <VStack spacing={6} align="stretch">
              {REGIONS.map(({ key, label }) => {
                const region = digest.payload[key];
                if (!region) return null;
                return (
                  <Box key={key}>
                    {/* Region kicker */}
                    <Text
                      fontSize="xs" fontWeight="700" color="brand.red"
                      textTransform="uppercase" letterSpacing="wider" mb={2}
                    >
                      {label}
                    </Text>

                    {/* Summary narrative */}
                    <Text fontSize="xs" color="brand.ink" lineHeight="1.7" mb={region.examples?.length ? 3 : 0}>
                      {region.summary}
                    </Text>

                    {/* Wrong → Correct examples */}
                    {region.examples?.length > 0 && (
                      <VStack align="stretch" spacing={3}>
                        {region.examples.map((ex, i) => (
                          <Box
                            key={i}
                            pl={3}
                            borderLeft="2px solid"
                            borderColor="brand.rule"
                          >
                            <Text fontSize="xs" color="brand.muted" mb={1} lineHeight="1.5">
                              {ex.zh}
                            </Text>
                            <HStack spacing={1.5} align="start" flexWrap="wrap">
                              <Text fontSize="2xs" color="#c0392b" fontWeight="600"
                                textDecoration="line-through" lineHeight="1.6">
                                {ex.wrong}
                              </Text>
                              <Text fontSize="2xs" color="brand.muted" lineHeight="1.6">→</Text>
                              <Text fontSize="2xs" color="#27ae60" fontWeight="600" lineHeight="1.6">
                                {ex.correct}
                              </Text>
                            </HStack>
                          </Box>
                        ))}
                      </VStack>
                    )}
                  </Box>
                );
              })}

              <Divider borderColor="brand.rule" />
              <Text fontSize="2xs" color="brand.muted" textAlign="center" pb={2} lineHeight="1.6">
                Updated {timeAgo(digest.created_at)} · covers all runs up to {timeAgo(digest.digest_at)}
              </Text>
            </VStack>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}
