import React from 'react';
import { Box, HStack, Image, Text, Link } from '@chakra-ui/react';

export default function HeadlineCard({ headline }: { headline: any }) {
  const articleUrl = headline.source_url || `https://www.youtube.com/watch?v=${headline.id}`;
  const d = new Date(headline.published_at);
  const stamp =
    d.toLocaleDateString('en-MY', { day: 'numeric', month: 'short' }) +
    ' · ' +
    d.toLocaleTimeString('en-MY', { hour: 'numeric', minute: '2-digit', hour12: true });

  return (
    <HStack
      align="start"
      spacing={2}
      px={2}
      py={1.5}
      bg="white"
      borderRadius="md"
      boxShadow="xs"
      _hover={{ boxShadow: 'sm' }}
      transition="box-shadow 0.15s"
    >
      {/* Left column: thumbnail + channel + timestamp */}
      <Box flexShrink={0} w="56px" textAlign="center">
        <Link href={articleUrl} isExternal>
          <Image
            src={headline.thumbnail_url}
            alt={headline.title_zh}
            borderRadius="sm"
            w="56px"
            h="32px"
            objectFit="cover"
          />
        </Link>
        <Text
          fontSize="2xs" color="red.500" fontWeight="semibold"
          mt={1} lineHeight="1.2" isTruncated
        >
          {headline.channel}
        </Text>
        <Text fontSize="2xs" color="gray.400" lineHeight="1.2" mt={0.5}>
          {stamp}
        </Text>
      </Box>

      {/* Right column: titles only */}
      <Box flex={1} minW={0}>
        <Link href={articleUrl} isExternal _hover={{ textDecoration: 'none' }}>
          <Text fontSize="sm" fontWeight="bold" lineHeight="1.3" color="gray.800"
            _hover={{ color: 'red.500' }} transition="color 0.1s">
            {headline.title_zh}
          </Text>
        </Link>
        <Text fontSize="xs" color="gray.500" lineHeight="1.35" mt={0.5}>
          {headline.title_en}
        </Text>
      </Box>
    </HStack>
  );
}
