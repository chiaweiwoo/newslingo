import React from 'react';
import {
  Drawer, DrawerBody, DrawerHeader, DrawerOverlay, DrawerContent,
  DrawerCloseButton, Box, Text, VStack, HStack, Badge, Spinner,
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
      <DrawerContent maxH="72vh" borderTopRadius="2xl">
        <DrawerCloseButton color="gray.400" mt={1} />

        <DrawerHeader borderBottom="1px solid" borderColor="gray.100" pb={3} pt={4}>
          <HStack spacing={2.5} align="start">
            <Text fontSize="xl" lineHeight="1">🧠</Text>
            <Box>
              <Text fontSize="md" fontWeight="bold" color="gray.800" lineHeight="1.2">
                How AI is Improving
              </Text>
              <Text fontSize="xs" color="gray.400" fontWeight="normal" mt={0.5}>
                After each batch of runs, the AI reviews its own translation mistakes
                and writes rules to do better next time.
              </Text>
            </Box>
          </HStack>
        </DrawerHeader>

        <DrawerBody py={4} overflowY="auto">
          {isLoading ? (
            <Center py={10}>
              <Spinner color="red.500" size="md" />
            </Center>
          ) : !rules?.length ? (
            <Center py={10}>
              <VStack spacing={2}>
                <Text fontSize="2xl">🌱</Text>
                <Text fontSize="sm" color="gray.500" fontWeight="medium">Still learning…</Text>
                <Text fontSize="xs" color="gray.400" textAlign="center" maxW="220px">
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
                      <Badge
                        colorScheme="red" variant="subtle"
                        borderRadius="full" px={2} py={0.5} fontSize="xs"
                      >
                        {SOURCE_LABEL[rule.source] ?? rule.source}
                      </Badge>
                      <Text fontSize="2xs" color="gray.400">
                        Updated {timeAgo(rule.generated_at)} · run #{rule.run_count_at}
                      </Text>
                    </HStack>
                    <VStack align="stretch" spacing={2}>
                      {bullets.map((b, i) => (
                        <HStack key={i} align="start" spacing={2}>
                          <Text fontSize="xs" color="red.400" mt="2px" flexShrink={0}>•</Text>
                          <Text fontSize="xs" color="gray.700" lineHeight="1.6">{b}</Text>
                        </HStack>
                      ))}
                    </VStack>
                  </Box>
                );
              })}

              <Divider borderColor="gray.100" />
              <Text fontSize="2xs" color="gray.400" textAlign="center" pb={2} lineHeight="1.6">
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
