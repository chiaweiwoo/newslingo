import React from 'react';
import { Box, HStack, Image, Text, VStack, Badge, Link } from '@chakra-ui/react';

export default function HeadlineCard({ headline }: { headline: any }) {
  const youtubeUrl = `https://www.youtube.com/watch?v=${headline.id}`;
  const datetime = new Date(headline.published_at).toLocaleString('en-MY', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  });

  return (
    <HStack
      align="start"
      spacing={3}
      p={3}
      bg="white"
      borderRadius="lg"
      borderWidth="1px"
      borderColor="gray.100"
      boxShadow="sm"
      _hover={{ boxShadow: 'md', borderColor: 'gray.200' }}
      transition="all 0.15s ease"
    >
      <Image
        src={headline.thumbnail_url}
        alt={headline.title_zh}
        borderRadius="md"
        w="120px"
        minW="120px"
        objectFit="cover"
        aspectRatio="16/9"
      />
      <VStack align="start" spacing={1} flex={1} overflow="hidden">
        <Link href={youtubeUrl} isExternal _hover={{ textDecoration: 'none' }}>
          <Text fontSize="sm" fontWeight="bold" lineHeight="1.4" color="gray.800"
            _hover={{ color: 'red.500' }} transition="color 0.1s" noOfLines={3}>
            {headline.title_zh}
          </Text>
        </Link>
        <Text fontSize="xs" color="gray.500" lineHeight="1.4" noOfLines={3}>
          {headline.title_en}
        </Text>
        <HStack spacing={2} pt={1}>
          <Badge colorScheme="red" fontSize="2xs">{headline.channel}</Badge>
          <Text fontSize="2xs" color="gray.400">{datetime}</Text>
        </HStack>
      </VStack>
    </HStack>
  );
}
