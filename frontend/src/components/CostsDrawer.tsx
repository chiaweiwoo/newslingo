/**
 * AI Costs drawer
 *
 * Fetches all historical token_usage rows and computes:
 *   - Daily / weekly / monthly cost estimates
 *   - This calendar month so far
 *   - All-time total
 *   - Per-task breakdown (last 30 days)
 */

import React from 'react';
import {
  Box, Center, Divider, Drawer, DrawerBody, DrawerCloseButton,
  DrawerContent, DrawerHeader, DrawerOverlay,
  HStack, Spinner, Text, VStack,
} from '@chakra-ui/react';
import { useQuery } from '@tanstack/react-query';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);

// ── Types ─────────────────────────────────────────────────────────────────────

interface UsageRow {
  task:        string;
  cost_usd:    number;
  recorded_at: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtCost(usd: number): string {
  if (usd < 0.001) return '<$0.001';
  if (usd < 1)     return `$${usd.toFixed(3)}`;
  if (usd < 10)    return `$${usd.toFixed(2)}`;
  return `$${usd.toFixed(1)}`;
}

function fmtCostFull(usd: number): string {
  if (usd < 0.01) return '<$0.01';
  return `$${usd.toFixed(2)}`;
}

const TASK_META: Record<string, { label: string; color: string }> = {
  translation: { label: 'Translation', color: '#1565c0' },
  feedback:    { label: 'Assessment',  color: '#6a1b9a' },
  insights:    { label: 'Summaries',   color: '#2e7d32' },
};
const TASK_ORDER = ['translation', 'feedback', 'insights'];

// ── Component ─────────────────────────────────────────────────────────────────

interface Props { isOpen: boolean; onClose: () => void; }

export default function CostsDrawer({ isOpen, onClose }: Props) {
  const { data: rows = [], isLoading } = useQuery({
    queryKey: ['costs-all'],
    queryFn: async (): Promise<UsageRow[]> => {
      const { data } = await supabase
        .from('token_usage')
        .select('task, cost_usd, recorded_at')
        .order('recorded_at', { ascending: true });
      return (data ?? []) as UsageRow[];
    },
    enabled: isOpen,
    staleTime: 5 * 60 * 1000,
  });

  // ── Derived metrics ────────────────────────────────────────────────────────

  const now     = new Date();
  const todayKey = now.toISOString().slice(0, 10); // YYYY-MM-DD

  // Group all rows by calendar date
  const byDate: Record<string, number> = {};
  for (const r of rows) {
    const day = r.recorded_at.slice(0, 10);
    byDate[day] = (byDate[day] ?? 0) + r.cost_usd;
  }

  // Complete days only (exclude today — it's still accumulating)
  // Take the most recent 30 complete days for the estimate
  const completeDays = Object.entries(byDate)
    .filter(([d]) => d < todayKey)
    .sort(([a], [b]) => b.localeCompare(a)) // newest first
    .slice(0, 30)
    .map(([, cost]) => cost);

  // Median daily cost — robust to outlier test days
  function median(vals: number[]): number {
    if (!vals.length) return 0;
    const sorted = [...vals].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 === 0
      ? (sorted[mid - 1] + sorted[mid]) / 2
      : sorted[mid];
  }

  const dailyMedian = median(completeDays);
  const weeklyEst   = dailyMedian * 7;
  const monthlyEst  = dailyMedian * 30;

  const allTime       = rows.reduce((s, r) => s + r.cost_usd, 0);
  const monthStart    = new Date(now.getFullYear(), now.getMonth(), 1).toISOString();
  const thisMonth     = rows
    .filter(r => r.recorded_at >= monthStart)
    .reduce((s, r) => s + r.cost_usd, 0);
  const daysIntoMonth = now.getDate();

  // Last 30 days per task
  const since30     = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
  const recentRows  = rows.filter(r => r.recorded_at >= since30);
  const recentTotal = recentRows.reduce((s, r) => s + r.cost_usd, 0);

  const byTask: Record<string, { cost: number; runs: number }> = {};
  for (const r of recentRows) {
    if (!byTask[r.task]) byTask[r.task] = { cost: 0, runs: 0 };
    byTask[r.task].cost += r.cost_usd;
    byTask[r.task].runs += 1;
  }

  const nDays = completeDays.length;
  const daysLabel = nDays === 0
    ? 'today only'
    : nDays === 1
    ? '1 complete day'
    : `${nDays} complete days`;

  return (
    <Drawer isOpen={isOpen} placement="bottom" onClose={onClose}>
      <DrawerOverlay />
      <DrawerContent
        maxH="88dvh"
        style={{ maxWidth: '600px', marginLeft: 'auto', marginRight: 'auto' }}
        borderTopRadius="xl"
        bg="brand.paper"
      >
        <DrawerCloseButton color="brand.muted" top={3} right={4} />

        <DrawerHeader px={4} pt={4} pb={3} borderBottom="1px solid" borderColor="brand.rule">
          <Text
            fontSize="md" fontWeight="700" color="brand.ink" pr={8}
            fontFamily="'Noto Serif SC', 'Georgia', serif"
          >
            AI Costs
          </Text>
          <Text fontSize="xs" color="brand.muted" fontWeight="400" mt={0.5}>
            Median daily spend across {daysLabel}
          </Text>
        </DrawerHeader>

        <DrawerBody px={4} py={4} overflowY="auto">
          {isLoading ? (
            <Center py={10}><Spinner color="brand.red" size="md" /></Center>
          ) : !rows.length ? (
            <Center py={10}>
              <VStack spacing={2}>
                <Text fontSize="2xl">📊</Text>
                <Text fontSize="sm" color="brand.ink" fontWeight="600">No data yet</Text>
                <Text fontSize="xs" color="brand.muted" textAlign="center" maxW="220px">
                  Costs appear after the next job run.
                </Text>
              </VStack>
            </Center>
          ) : (
            <VStack spacing={4} align="stretch">

              {/* ── Projection card ───────────────────────────────────── */}
              <Box
                bg="brand.card" border="1px solid" borderColor="brand.rule"
                borderRadius="md" px={4} py={3}
              >
                <Text
                  fontSize="2xs" fontWeight="700" color="brand.muted"
                  textTransform="uppercase" letterSpacing="wider" mb={3}
                >
                  Estimated spend
                </Text>

                {/* Monthly — hero number */}
                <HStack justify="space-between" align="baseline" mb={3}>
                  <Text fontSize="sm" color="brand.muted">Per month</Text>
                  <Text fontSize="2xl" fontWeight="700" color="brand.red" lineHeight="1">
                    {fmtCostFull(monthlyEst)}
                  </Text>
                </HStack>

                <Divider borderColor="brand.rule" mb={3} />

                <VStack spacing={2} align="stretch">
                  <HStack justify="space-between">
                    <Text fontSize="xs" color="brand.muted">Per week</Text>
                    <Text fontSize="xs" fontWeight="600" color="brand.ink">{fmtCostFull(weeklyEst)}</Text>
                  </HStack>
                  <HStack justify="space-between">
                    <Text fontSize="xs" color="brand.muted">Per day (median)</Text>
                    <Text fontSize="xs" fontWeight="600" color="brand.ink">{fmtCost(dailyMedian)}</Text>
                  </HStack>
                  <HStack justify="space-between">
                    <Text fontSize="xs" color="brand.muted">Per hour</Text>
                    <Text fontSize="xs" fontWeight="600" color="brand.ink">{fmtCost(dailyMedian / 24)}</Text>
                  </HStack>
                </VStack>
              </Box>

              {/* ── Actuals ───────────────────────────────────────────── */}
              <Box
                bg="brand.card" border="1px solid" borderColor="brand.rule"
                borderRadius="md" px={4} py={3}
              >
                <Text
                  fontSize="2xs" fontWeight="700" color="brand.muted"
                  textTransform="uppercase" letterSpacing="wider" mb={3}
                >
                  Actuals
                </Text>
                <VStack spacing={2} align="stretch">
                  <HStack justify="space-between">
                    <Box>
                      <Text fontSize="xs" color="brand.muted" display="inline">
                        {now.toLocaleString('en-MY', { month: 'long' })} so far
                      </Text>
                      <Text fontSize="2xs" color="brand.muted" display="inline"> · {daysIntoMonth}d in</Text>
                    </Box>
                    <Text fontSize="xs" fontWeight="600" color="brand.ink">{fmtCostFull(thisMonth)}</Text>
                  </HStack>
                  <HStack justify="space-between">
                    <Text fontSize="xs" color="brand.muted">All time</Text>
                    <Text fontSize="xs" fontWeight="600" color="brand.ink">{fmtCostFull(allTime)}</Text>
                  </HStack>
                </VStack>
              </Box>

              {/* ── By task ───────────────────────────────────────────── */}
              {TASK_ORDER.some(t => byTask[t]) && (
                <Box
                  bg="brand.card" border="1px solid" borderColor="brand.rule"
                  borderRadius="md" px={4} py={3}
                >
                  <Text
                    fontSize="2xs" fontWeight="700" color="brand.muted"
                    textTransform="uppercase" letterSpacing="wider" mb={3}
                  >
                    By task · last 30 days
                  </Text>
                  <VStack spacing={3} align="stretch">
                    {TASK_ORDER.filter(t => byTask[t]).map((t, i) => {
                      const meta  = TASK_META[t] ?? { label: t, color: 'brand.muted' };
                      const entry = byTask[t];
                      const pct   = recentTotal > 0 ? (entry.cost / recentTotal) * 100 : 0;
                      return (
                        <Box key={t}>
                          {i > 0 && <Divider borderColor="brand.rule" mb={3} />}
                          <HStack justify="space-between" mb={1.5}>
                            <Text fontSize="xs" fontWeight="600" color={meta.color}>{meta.label}</Text>
                            <Text fontSize="xs" fontWeight="600" color="brand.ink">{fmtCostFull(entry.cost)}</Text>
                          </HStack>
                          <Box h="3px" bg="brand.rule" borderRadius="full" overflow="hidden" mb={1.5}>
                            <Box h="100%" w={`${pct}%`} bg={meta.color} borderRadius="full" transition="width 0.4s ease" />
                          </Box>
                          <Text fontSize="2xs" color="brand.muted">
                            {entry.runs} runs · avg {fmtCost(entry.cost / entry.runs)} / run · {Math.round(pct)}% of spend
                          </Text>
                        </Box>
                      );
                    })}
                  </VStack>
                </Box>
              )}

              <Text fontSize="2xs" color="brand.muted" textAlign="center" lineHeight="1.6">
                Estimates use median daily spend to filter out test runs · USD
              </Text>

            </VStack>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}
