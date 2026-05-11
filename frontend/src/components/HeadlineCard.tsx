import React from 'react';
import { Box, HStack, Image, Text, Badge, Link } from '@chakra-ui/react';

export default function HeadlineCard({ headline }: { headline: any }) {
  const articleUrl = headline.source_url || `https://www.youtube.com/watch?v=${headline.id}`;
  const dateStr = new Date(headline.published_at).toLocaleDateString('en-MY', {
    day: 'numeric', month: 'short',
  });
  const timeStr = new Date(headline.published_at).toLocaleTimeString('en-MY', {
    hour: '2-digit', minute: '2-digit', hour12: true,
  });

  return (
    <HStack
      align="start"
      spacing={2}
      p={2}
      bg="white"
      borderRadius="xl"
      boxShadow="xs"
      _hover={{ boxShadow: 'sm' }}
      transition="box-shadow 0.15s"
    >
      {/* Left column: thumbnail + channel + timestamp */}
      <Box flexShrink={0} w="68px" textAlign="center">
        <Link href={articleUrl} isExternal>
          <Image
            src={headline.thumbnail_url}
            alt={headline.title_zh}
            borderRadius="md"
            w="68px"
            h="38px"
            objectFit="cover"
          />
        </Link>
        <Badge
          colorScheme="red" variant="subtle" fontSize="2xs"
          borderRadius="full" px={1.5} mt={1}
          display="block" isTruncated
        >
          {headline.channel}
        </Badge>
        <Text fontSize="2xs" color="gray.300" mt={0.5} lineHeight="1.3">
          {dateStr}
        </Text>
        <Text fontSize="2xs" color="gray.300" lineHeight="1.3">
          {timeStr}
        </Text>
      </Box>

      {/* Right column: titles only */}
      <Box flex={1} minW={0}>
        <Link href={articleUrl} isExternal _hover={{ textDecoration: 'none' }}>
          <Text fontSize="sm" fontWeight="bold" lineHeight="1.35" color="gray.800"
            _hover={{ color: 'red.500' }} transition="color 0.1s">
            {headline.title_zh}
          </Text>
        </Link>
        <Text fontSize="xs" color="gray.500" lineHeight="1.4" mt={0.5}>
          {headline.title_en}
        </Text>
      </Box>
    </HStack>
  );
}
