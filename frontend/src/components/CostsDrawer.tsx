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

// ── Types ─────────────────────────────────────────────────────────────────────

interface UsageRow {
  task:          string;
  model:         string;
  input_tokens:  number;
  output_tokens: number;
  cost_usd:      number;
  recorded_at:   string;
}

interface TaskSummary {
  task:         string;
  model:        string;
  totalInput:   number;
  totalOutput:  number;
  totalCost:    number;
  runs:         number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const TASK_META: Record<string, { label: string; description: string; icon: string }> = {
  translation: { label: 'Translation',  description: 'Chinese → English headlines', icon: '🔤' },
  feedback:    { label: 'Feedback',      description: 'Quality scoring & rule improvement', icon: '🔄' },
  insights:    { label: 'Insights',      description: 'Inside AI digest & This Week summary', icon: '💡' },
};

const TASK_ORDER = ['translation', 'feedback', 'insights'];

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function fmtCost(usd: number): string {
  if (usd < 0.001) return '<$0.001';
  if (usd < 1)     return `$${usd.toFixed(3)}`;
  return `$${usd.toFixed(2)}`;
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  isOpen:  boolean;
  onClose: () => void;
}

export default function CostsDrawer({ isOpen, onClose }: Props) {
  const { data: rows, isLoading } = useQuery({
    queryKey: ['token-usage'],
    queryFn: async (): Promise<UsageRow[]> => {
      const since = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
      const { data } = await supabase
        .from('token_usage')
        .select('task, model, input_tokens, output_tokens, cost_usd, recorded_at')
        .gte('recorded_at', since)
        .order('recorded_at', { ascending: false });
      return (data ?? []) as UsageRow[];
    },
    enabled: isOpen,
    staleTime: 5 * 60 * 1000,
  });

  // Group by task
  const byTask: Record<string, TaskSummary> = {};
  for (const row of rows ?? []) {
    if (!byTask[row.task]) {
      byTask[row.task] = {
        task: row.task, model: row.model,
        totalInput: 0, totalOutput: 0, totalCost: 0, runs: 0,
      };
    }
    byTask[row.task].totalInput  += row.input_tokens;
    byTask[row.task].totalOutput += row.output_tokens;
    byTask[row.task].totalCost   += row.cost_usd;
    byTask[row.task].runs        += 1;
  }

  const tasks = TASK_ORDER.map(t => byTask[t]).filter(Boolean);
  const grandTotal = tasks.reduce((s, t) => s + t.totalCost, 0);
  const grandTokens = tasks.reduce((s, t) => s + t.totalInput + t.totalOutput, 0);

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
            Costs
          </Text>
          <Text fontSize="xs" color="brand.muted" fontWeight="400" mt={0.5}>
            AI token usage over the past 30 days.
          </Text>
        </DrawerHeader>

        <DrawerBody py={4} overflowY="auto">
          {isLoading ? (
            <Center py={10}><Spinner color="brand.red" size="md" /></Center>
          ) : !tasks.length ? (
            <Center py={10}>
              <VStack spacing={2}>
                <Text fontSize="2xl">📊</Text>
                <Text fontSize="sm" color="brand.ink" fontWeight="600">No data yet</Text>
                <Text fontSize="xs" color="brand.muted" textAlign="center" maxW="240px">
                  Usage will appear after the next job run.
                </Text>
              </VStack>
            </Center>
          ) : (
            <VStack spacing={0} align="stretch">

              {/* ── Per-task rows ───────────────────────────────────────── */}
              {tasks.map((t, i) => {
                const meta  = TASK_META[t.task] ?? { label: t.task, description: '', icon: '⚙️' };
                const total = t.totalInput + t.totalOutput;
                const avgCost = t.runs > 0 ? t.totalCost / t.runs : 0;
                return (
                  <Box key={t.task}>
                    {i > 0 && <Divider borderColor="brand.rule" />}
                    <Box py={3}>
                      <HStack justify="space-between" align="flex-start" mb={1.5}>
                        <HStack spacing={2}>
                          <Text fontSize="sm">{meta.icon}</Text>
                          <Box>
                            <Text fontSize="sm" fontWeight="700" color="brand.ink">
                              {meta.label}
                            </Text>
                            <Text fontSize="2xs" color="brand.muted">{meta.description}</Text>
                          </Box>
                        </HStack>
                        <Text fontSize="sm" fontWeight="700" color="brand.ink">
                          {fmtCost(t.totalCost)}
                        </Text>
                      </HStack>

                      <HStack spacing={4} pl="26px">
                        <Box>
                          <Text fontSize="2xs" color="brand.muted" textTransform="uppercase" letterSpacing="wider">
                            Tokens
                          </Text>
                          <Text fontSize="xs" color="brand.ink">{fmtTokens(total)}</Text>
                        </Box>
                        <Box>
                          <Text fontSize="2xs" color="brand.muted" textTransform="uppercase" letterSpacing="wider">
                            Avg / run
                          </Text>
                          <Text fontSize="xs" color="brand.ink">{fmtCost(avgCost)}</Text>
                        </Box>
                        <Box>
                          <Text fontSize="2xs" color="brand.muted" textTransform="uppercase" letterSpacing="wider">
                            Runs
                          </Text>
                          <Text fontSize="xs" color="brand.ink">{t.runs}</Text>
                        </Box>
                      </HStack>
                    </Box>
                  </Box>
                );
              })}

              <Divider borderColor="brand.rule" />

              {/* ── Grand total ─────────────────────────────────────────── */}
              <Box py={3}>
                <HStack justify="space-between">
                  <Text fontSize="xs" fontWeight="700" color="brand.ink">Total (30 days)</Text>
                  <Text fontSize="xs" fontWeight="700" color="brand.red">{fmtCost(grandTotal)}</Text>
                </HStack>
                <Text fontSize="2xs" color="brand.muted" mt={0.5}>
                  {fmtTokens(grandTokens)} tokens across all jobs
                </Text>
              </Box>

              <Divider borderColor="brand.rule" />
              <Text fontSize="2xs" color="brand.muted" textAlign="center" pb={2} pt={1} lineHeight="1.6">
                Prices per Anthropic's published rates · updated on each job run
              </Text>

            </VStack>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}
