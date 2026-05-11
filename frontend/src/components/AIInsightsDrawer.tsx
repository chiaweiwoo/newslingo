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

interface Rule {
  source: string;
  rules: string;
  run_count_at: number;
  generated_at: string;
}

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const m = Math.floor(seconds / 60); if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60); if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24); return `${d}d ago`;
}

const SOURCE_LABEL: Record<string, string> = {
  zaobao: '联合早报',
  astro: 'Astro 本地圈',
};

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export default function AIInsightsDrawer({ isOpen, onClose }: Props) {
  const { data: rules, isLoading } = useQuery({
    queryKey: ['prompt-rules'],
    queryFn: async (): Promise<Rule[]> => {
      const { data } = await supabase
        .from('prompt_rules')
        .select('source, rules, run_count_at, generated_at')
        .eq('active', true)
        .order('generated_at', { ascending: false });
      return (data as Rule[]) || [];
    },
    enabled: isOpen,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <Drawer isOpen={isOpen} placement="bottom" onClose={onClose}>
      <DrawerOverlay />
      <DrawerContent maxH="72vh" borderTopRadius="lg" bg="brand.paper">
        <DrawerCloseButton color="brand.muted" mt={1} />

        <DrawerHeader borderBottom="1px solid" borderColor="brand.rule" pb={3} pt={4}>
          <HStack spacing={2.5} align="start">
            {/* Editorial AI badge */}
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
                How AI is Improving
              </Text>
              <Text fontSize="xs" color="brand.muted" fontWeight="400" mt={0.5}>
                After each run, the AI reviews its own translation mistakes
                and writes new rules to do better next time.
              </Text>
            </Box>
          </HStack>
        </DrawerHeader>

        <DrawerBody py={4} overflowY="auto">
          {isLoading ? (
            <Center py={10}>
              <Spinner color="brand.red" size="md" />
            </Center>
          ) : !rules?.length ? (
            <Center py={10}>
              <VStack spacing={2}>
                <Text fontSize="2xl">🌱</Text>
                <Text fontSize="sm" color="brand.ink" fontWeight="600">Still learning…</Text>
                <Text fontSize="xs" color="brand.muted" textAlign="center" maxW="220px">
                  Rules will appear after the next job run completes.
                </Text>
              </VStack>
            </Center>
          ) : (
            <VStack spacing={5} align="stretch">
              {rules.map(rule => {
                const bullets = rule.rules
                  .split('\n')
                  .map(l => l.replace(/^[-•]\s*/, '').trim())
                  .filter(Boolean);
                return (
                  <Box key={rule.source}>
                    <HStack mb={2.5} justify="space-between" align="center">
                      {/* Source — styled as editorial kicker, not pill badge */}
                      <Text
                        fontSize="xs" fontWeight="700" color="brand.red"
                        textTransform="uppercase" letterSpacing="wider"
                      >
                        {SOURCE_LABEL[rule.source] ?? rule.source}
                      </Text>
                      <Text fontSize="2xs" color="brand.muted">
                        {timeAgo(rule.generated_at)} · run #{rule.run_count_at}
                      </Text>
                    </HStack>
                    <VStack align="stretch" spacing={2}>
                      {bullets.map((b, i) => (
                        <HStack key={i} align="start" spacing={2}>
                          <Text fontSize="xs" color="brand.red" mt="2px" flexShrink={0}>•</Text>
                          <Text fontSize="xs" color="brand.ink" lineHeight="1.6">{b}</Text>
                        </HStack>
                      ))}
                    </VStack>
                  </Box>
                );
              })}

              <Divider borderColor="brand.rule" />
              <Text fontSize="2xs" color="brand.muted" textAlign="center" pb={2} lineHeight="1.6">
                These rules are automatically injected into the AI's prompt on every run,
                so translations keep improving over time.
              </Text>
            </VStack>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}
