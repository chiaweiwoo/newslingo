import React from 'react';
import { Box, HStack, Image, Text, Link } from '@chakra-ui/react';

// Noto Serif SC for Chinese editorial headlines — Bilingual Editorial Asia design
const ZH_SERIF = `'Noto Serif SC', 'Songti SC', 'STSong', 'SimSun', Georgia, serif`;

export default function HeadlineCard({ headline }: { headline: any }) {
  const articleUrl = headline.source_url || `https://www.youtube.com/watch?v=${headline.id}`;
  const d = new Date(headline.published_at);
  const dateStr = d.toLocaleDateString('en-MY', { day: 'numeric', month: 'short' });
  const timeStr = d.toLocaleTimeString('en-MY', { hour: 'numeric', minute: '2-digit', hour12: true });

  return (
    <HStack
      align="start"
      spacing={3}
      p={3}
      bg="white"
      borderRadius="sm"
      boxShadow="xs"
      _hover={{ boxShadow: 'sm' }}
      transition="box-shadow 0.15s"
    >
      {/* Thumbnail */}
      <Link href={articleUrl} isExternal flexShrink={0}>
        <Image
          src={headline.thumbnail_url}
          alt={headline.title_zh}
          borderRadius="sm"
          w="90px"
          h="51px"
          objectFit="cover"
          bg="brand.rule"
        />
      </Link>

      {/* Text block */}
      <Box flex={1} minW={0}>

        {/* Chinese headline — serif, dominant */}
        <Link href={articleUrl} isExternal _hover={{ textDecoration: 'none' }}>
          <Text
            fontFamily={ZH_SERIF}
            fontSize="sm"
            fontWeight="700"
            lineHeight="1.4"
            color="brand.ink"
            _hover={{ color: 'brand.red' }}
            transition="color 0.1s"
          >
            {headline.title_zh}
          </Text>
        </Link>

        {/* English translation — sans, secondary */}
        <Text
          fontFamily="'Inter', sans-serif"
          fontSize="xs"
          fontWeight="400"
          color="#666666"
          lineHeight="1.5"
          mt={1}
        >
          {headline.title_en}
        </Text>

        {/* Meta line — source · date · time */}
        <HStack mt={1.5} spacing={1} fontSize="2xs" color="brand.muted" letterSpacing="0.02em">
          <Text fontWeight="600" color="brand.red">{headline.channel}</Text>
          <Text color="brand.rule">·</Text>
          <Text>{dateStr}</Text>
          <Text color="brand.rule">·</Text>
          <Text>{timeStr}</Text>
        </HStack>
      </Box>
    </HStack>
  );
}
