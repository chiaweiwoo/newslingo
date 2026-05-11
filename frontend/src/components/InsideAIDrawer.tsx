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
  points: string[];
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

export default function InsideAIDrawer({ isOpen, onClose }: Props) {
  const { data: digest, isLoading } = useQuery({
    queryKey: ['inside-ai'],
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
    staleTime: 0,
  });

  return (
    <Drawer isOpen={isOpen} placement="bottom" onClose={onClose}>
      <DrawerOverlay />
      <DrawerContent maxH="80vh" style={{ maxWidth: "600px", marginLeft: "auto", marginRight: "auto" }} borderTopRadius="lg" bg="brand.paper">
        <DrawerCloseButton color="brand.muted" mt={1} />

        <DrawerHeader borderBottom="1px solid" borderColor="brand.rule" pb={3} pt={4}>
          <Text fontSize="md" fontWeight="700" color="brand.ink" lineHeight="1.2"
            fontFamily="'Noto Serif SC', 'Georgia', serif">
            Inside AI
          </Text>
          <Text fontSize="xs" color="brand.muted" fontWeight="400" mt={0.5}>
            How the AI reviews its own translations — what it gets right, wrong, and improves.
          </Text>
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
            <VStack spacing={5} align="stretch">
              {REGIONS.map(({ key, label }) => {
                const region = digest.payload[key];
                if (!region?.points?.length) return null;
                return (
                  <Box key={key}>
                    <Text
                      fontSize="xs" fontWeight="700" color="brand.red"
                      textTransform="uppercase" letterSpacing="wider" mb={2.5}
                    >
                      {label}
                    </Text>
                    <VStack spacing={1.5} align="stretch">
                      {region.points.map((point, i) => (
                        <HStack key={i} spacing={2} align="flex-start">
                          <Text fontSize="xs" color="brand.red" flexShrink={0} mt="1px">–</Text>
                          <Text fontSize="xs" color="brand.ink" lineHeight="1.6">{point}</Text>
                        </HStack>
                      ))}
                    </VStack>
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
