import React from 'react';
import { Box, HStack, Image, Text, Badge, Link } from '@chakra-ui/react';

export default function HeadlineCard({ headline }: { headline: any }) {
  const youtubeUrl = `https://www.youtube.com/watch?v=${headline.id}`;
  const datetime = new Date(headline.published_at).toLocaleString('en-MY', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: true,
  });

  return (
    <HStack
      align="start"
      spacing={3}
      p={3}
      bg="white"
      borderRadius="xl"
      boxShadow="xs"
      _hover={{ boxShadow: 'sm' }}
      transition="box-shadow 0.15s"
    >
      <Link href={youtubeUrl} isExternal flexShrink={0}>
        <Image
          src={headline.thumbnail_url}
          alt={headline.title_zh}
          borderRadius="md"
          w="96px"
          h="54px"
          objectFit="cover"
        />
      </Link>

      <Box flex={1} minW={0}>
        <Link href={youtubeUrl} isExternal _hover={{ textDecoration: 'none' }}>
          <Text fontSize="sm" fontWeight="bold" lineHeight="1.4" color="gray.800"
            _hover={{ color: 'red.500' }} transition="color 0.1s">
            {headline.title_zh}
          </Text>
        </Link>
        <Text fontSize="xs" color="gray.500" lineHeight="1.5" mt={0.5}>
          {headline.title_en}
        </Text>
        <HStack spacing={2} mt={1.5}>
          <Badge colorScheme="red" variant="subtle" fontSize="2xs" borderRadius="full" px={1.5}>
            {headline.channel}
          </Badge>
          <Text fontSize="2xs" color="gray.300" ml="auto">{datetime}</Text>
        </HStack>
      </Box>
    </HStack>
  );
}
