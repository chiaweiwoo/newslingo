import React from 'react';
import { Box, Image, Text, HStack, Badge, Link, Tooltip } from '@chakra-ui/react';

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
    <Box
      bg="white"
      borderRadius="xl"
      overflow="hidden"
      boxShadow="sm"
      _hover={{ boxShadow: 'lg', transform: 'translateY(-2px)' }}
      transition="all 0.2s ease"
    >
      <Link href={youtubeUrl} isExternal display="block" _hover={{ textDecoration: 'none' }}>
        <Image
          src={headline.thumbnail_url}
          alt={headline.title_zh}
          w="100%"
          objectFit="cover"
          aspectRatio="16/9"
        />
      </Link>

      <Box p={3}>
        <Tooltip label={headline.title_zh} placement="top" hasArrow openDelay={400}
          bg="gray.800" color="white" fontSize="xs" borderRadius="md" maxW="300px">
          <Link href={youtubeUrl} isExternal _hover={{ textDecoration: 'none' }}>
            <Text
              fontSize="sm" fontWeight="bold" lineHeight="1.45" color="gray.800"
              _hover={{ color: 'red.500' }} transition="color 0.15s" noOfLines={2} mb={1}
            >
              {headline.title_zh}
            </Text>
          </Link>
        </Tooltip>

        <Tooltip label={headline.title_en} placement="bottom" hasArrow openDelay={400}
          bg="gray.800" color="white" fontSize="xs" borderRadius="md" maxW="300px">
          <Text
            fontSize="xs" color="gray.500" lineHeight="1.5" noOfLines={2}
            cursor="default" mb={3}
          >
            {headline.title_en}
          </Text>
        </Tooltip>

        <HStack spacing={2} borderTopWidth="1px" borderColor="gray.50" pt={2}>
          <Badge colorScheme="red" variant="subtle" fontSize="2xs" borderRadius="full" px={2}>
            {headline.channel}
          </Badge>
          <Text fontSize="2xs" color="gray.400" ml="auto">{datetime}</Text>
        </HStack>
      </Box>
    </Box>
  );
}
