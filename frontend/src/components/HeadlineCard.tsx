import React from 'react';
import { Box, HStack, Text, Link } from '@chakra-ui/react';

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

interface Props {
  headline: any;
  isLast?: boolean;
}

export default function HeadlineCard({ headline, isLast = false }: Props) {
  const articleUrl = headline.source_url || `https://www.youtube.com/watch?v=${headline.id}`;

  return (
    <Link
      href={articleUrl} isExternal
      _hover={{ textDecoration: 'none' }}
      display="block"
    >
      <Box
        py={2.5} px={3}
        borderBottom={isLast ? 'none' : '1px solid'}
        borderColor="gray.100"
        _hover={{ bg: 'gray.50' }}
        transition="background 0.1s"
      >
        <Text fontSize="md" fontWeight="bold" color="gray.900" lineHeight="1.3">
          {headline.title_zh}
        </Text>
        <Text fontSize="xs" color="gray.600" lineHeight="1.4" mt={1}>
          {headline.title_en}
        </Text>
        <HStack mt={1.5} spacing={1.5} fontSize="2xs">
          <Text color="red.500" fontWeight="semibold">{headline.channel}</Text>
          <Text color="gray.300">·</Text>
          <Text color="gray.400">{timeAgo(headline.published_at)}</Text>
        </HStack>
      </Box>
    </Link>
  );
}
