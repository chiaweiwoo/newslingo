import React from 'react';
import { Box, HStack, Image, Text, VStack, Badge, Link, Tooltip } from '@chakra-ui/react';

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
      boxShadow="xs"
      _hover={{ boxShadow: 'md', transform: 'translateY(-1px)' }}
      transition="all 0.15s ease"
    >
      <Link href={youtubeUrl} isExternal flexShrink={0} _hover={{ opacity: 0.9 }}>
        <Image
          src={headline.thumbnail_url}
          alt={headline.title_zh}
          borderRadius="md"
          w="96px"
          h="54px"
          objectFit="cover"
        />
      </Link>

      <VStack align="start" spacing={1} flex={1} overflow="hidden">
        <Tooltip label={headline.title_zh} placement="top" hasArrow openDelay={500}
          bg="gray.800" color="white" fontSize="xs" borderRadius="md" maxW="300px">
          <Link href={youtubeUrl} isExternal _hover={{ textDecoration: 'none' }}>
            <Text fontSize="xs" fontWeight="bold" lineHeight="1.4" color="gray.800"
              _hover={{ color: 'red.500' }} transition="color 0.1s" noOfLines={2}>
              {headline.title_zh}
            </Text>
          </Link>
        </Tooltip>

        <Tooltip label={headline.title_en} placement="bottom" hasArrow openDelay={500}
          bg="gray.800" color="white" fontSize="xs" borderRadius="md" maxW="300px">
          <Text fontSize="xs" color="gray.400" lineHeight="1.4" noOfLines={2} cursor="default">
            {headline.title_en}
          </Text>
        </Tooltip>

        <HStack spacing={2} pt={0.5}>
          <Badge colorScheme="red" variant="subtle" fontSize="2xs" borderRadius="full" px={1.5}>
            {headline.channel}
          </Badge>
          <Text fontSize="2xs" color="gray.300">{datetime}</Text>
        </HStack>
      </VStack>
    </HStack>
  );
}
